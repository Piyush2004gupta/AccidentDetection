const output = document.getElementById("output");
const incidentMeta = document.getElementById("incidentMeta");
const cameraPreview = document.getElementById("cameraPreview");
const detectionOverlay = document.getElementById("detectionOverlay");
const resultsSection = document.getElementById("resultsSection");
const detectionSection = document.querySelector(".detection-section");
const settingsPanel = document.getElementById("settingsPanel");
const settingsToggle = document.getElementById("settingsToggle");
const whatsAppActions = document.getElementById("whatsAppActions");
const sendAllPanelsBtn = document.getElementById("sendAllPanelsBtn");
const sendAdminPanelBtn = document.getElementById("sendAdminPanelBtn");
const sendHospitalPanelBtn = document.getElementById("sendHospitalPanelBtn");
const sendAmbulancePanelBtn = document.getElementById("sendAmbulancePanelBtn");
const adminPanelLinks = document.getElementById("adminPanelLinks");
const hospitalPanelLinks = document.getElementById("hospitalPanelLinks");
const ambulancePanelLinks = document.getElementById("ambulancePanelLinks");

let pendingWhatsAppLinksByRole = {
  admin: [],
  hospital: [],
  ambulance: [],
};

let previewStream = null;
let frameDetectionActive = false;
let frameDetectionLoopPromise = null;

// Settings toggle
settingsToggle.addEventListener("click", () => {
  settingsPanel.classList.toggle("open");
});

// Close settings when clicking outside on mobile
document.addEventListener("click", (e) => {
  if (window.innerWidth <= 480) {
    if (!e.target.closest(".header-card")) {
      settingsPanel.classList.remove("open");
    }
  }
});

function getCurrentPreviewStream() {
  return previewStream || cameraPreview.srcObject || null;
}

function hardStopPreview() {
  const stream = getCurrentPreviewStream();
  if (stream && typeof stream.getTracks === "function") {
    stream.getTracks().forEach((track) => {
      try {
        track.stop();
      } catch (_error) {
      }
    });
  }

  previewStream = null;
  cameraPreview.pause();
  cameraPreview.srcObject = null;
  cameraPreview.removeAttribute("src");
  cameraPreview.load();
  clearDetectionOverlay();
}

function stopFrameDetectionLoop() {
  frameDetectionActive = false;
}

function captureVideoFrameAsBase64(videoElement) {
  const width = videoElement.videoWidth || 640;
  const height = videoElement.videoHeight || 480;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  context.drawImage(videoElement, 0, 0, width, height);
  return canvas.toDataURL("image/jpeg", 0.65);
}

function clearDetectionOverlay() {
  if (!detectionOverlay) {
    return;
  }
  const context = detectionOverlay.getContext("2d");
  if (!context) {
    return;
  }
  context.clearRect(0, 0, detectionOverlay.width, detectionOverlay.height);
}

function renderDetectionOverlay(data) {
  if (!detectionOverlay || !cameraPreview.videoWidth || !cameraPreview.videoHeight) {
    return;
  }

  const overlayWidth = cameraPreview.clientWidth;
  const overlayHeight = cameraPreview.clientHeight;
  if (!overlayWidth || !overlayHeight) {
    return;
  }

  detectionOverlay.width = overlayWidth;
  detectionOverlay.height = overlayHeight;

  const context = detectionOverlay.getContext("2d");
  if (!context) {
    return;
  }

  context.clearRect(0, 0, overlayWidth, overlayHeight);

  const detections = Array.isArray(data?.detections) ? data.detections : [];
  if (!detections.length) {
    return;
  }

  const sourceWidth = Number(data?.frame_width) || cameraPreview.videoWidth;
  const sourceHeight = Number(data?.frame_height) || cameraPreview.videoHeight;
  const scaleX = overlayWidth / sourceWidth;
  const scaleY = overlayHeight / sourceHeight;

  detections.forEach((item) => {
    const bbox = Array.isArray(item?.bbox) ? item.bbox : [];
    if (bbox.length !== 4) {
      return;
    }

    const x1 = Number(bbox[0]) * scaleX;
    const y1 = Number(bbox[1]) * scaleY;
    const x2 = Number(bbox[2]) * scaleX;
    const y2 = Number(bbox[3]) * scaleY;
    const width = Math.max(0, x2 - x1);
    const height = Math.max(0, y2 - y1);

    const isAccident = Boolean(item?.is_accident);
    const strokeColor = isAccident ? "#ff3b30" : "#2ecc71";
    const label = `${String(item?.class_name || "object").toUpperCase()} ${Math.round((Number(item?.confidence) || 0) * 100)}%`;

    context.lineWidth = 3;
    context.strokeStyle = strokeColor;
    context.strokeRect(x1, y1, width, height);

    context.font = "12px Segoe UI";
    const labelWidth = context.measureText(label).width + 10;
    const labelHeight = 20;
    const labelY = Math.max(0, y1 - labelHeight);

    context.fillStyle = strokeColor;
    context.fillRect(x1, labelY, labelWidth, labelHeight);
    context.fillStyle = "#ffffff";
    context.fillText(label, x1 + 5, labelY + 14);
  });
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function startFrameDetectionLoop() {
  if (!previewStream) {
    showMessage("Preview is not running. Cannot start frame detection loop.");
    return;
  }

  const source = document.getElementById("detectSource").value.trim() || "0";
  if (!/^\d+$/.test(source)) {
    return;
  }

  if (frameDetectionActive) {
    return;
  }

  frameDetectionActive = true;
  showMessage("Camera preview opened. Live frame detection started.");

  // Fixed interval timing for consistent frame capture (not affected by processing time)
  const detectionInterval = window.detectionIntervalMs || 200;
  const cameraId = document.getElementById("detectCameraId").value.trim();
  const maxFrames = Number(document.getElementById("detectMaxFrames").value || 0);
  let processed = 0;
  let lastFrameTime = Date.now();

  while (frameDetectionActive) {
    if (!previewStream || !cameraPreview.srcObject) {
      frameDetectionActive = false;
      break;
    }

    if (maxFrames > 0 && processed >= maxFrames) {
      frameDetectionActive = false;
      showMessage("Max frame limit reached for live detection loop.");
      break;
    }

    // Calculate time until next frame should be captured
    const now = Date.now();
    const elapsedSinceLastFrame = now - lastFrameTime;
    const sleepDuration = Math.max(0, detectionInterval - elapsedSinceLastFrame);
    
    if (sleepDuration > 0) {
      await sleep(sleepDuration);
    }

    lastFrameTime = Date.now();

    try {
      const imageBase64 = captureVideoFrameAsBase64(cameraPreview);
      const data = await post("/detect-frame", {
        camera_id: cameraId,
        image_base64: imageBase64,
      });

      renderDetectionOverlay(data);

      processed += 1;
      if (data.accident_detected) {
        showResultWithSummary(data);
        frameDetectionActive = false;
        break;
      }
    } catch (error) {
      showMessage(`Live frame detection failed: ${error.message}`);
      frameDetectionActive = false;
      break;
    }
  }

  frameDetectionLoopPromise = null;
}

function apiBase() {
  const value = document.getElementById("apiBase").value.trim().replace(/\/$/, "");
  // Default to relative /api if served from the same server or if value is localhost default
  if (!value || value === "http://127.0.0.1:8000" || value === "http://localhost:8000") {
    return "/api";
  }
  return value;
}

function showMessage(msg) {
  output.textContent = typeof msg === "string" ? msg : JSON.stringify(msg, null, 2);
}

function normalizeWhatsAppNumber(rawValue) {
  const digits = String(rawValue || "").replace(/\D/g, "");
  if (!digits) {
    return "";
  }
  if (digits.startsWith("91") && digits.length >= 12) {
    return digits;
  }
  if (digits.length === 10) {
    return `91${digits}`;
  }
  return digits;
}

function parseWhatsAppNumbers(rawValue) {
  return Array.from(
    new Set(
      String(rawValue || "")
        .split(/[\s,;]+/)
        .map((item) => normalizeWhatsAppNumber(item))
        .filter((item) => Boolean(item))
    )
  );
}

function renderRoleWhatsAppLinks(container, links) {
  if (!container) {
    return;
  }
  if (!links.length) {
    container.innerHTML = "";
    return;
  }

  const items = links.map((item) => {
    return `<a href="${item.url}" target="_blank" rel="noopener noreferrer">${item.roleLabel} (${item.number})</a>`;
  });
  container.innerHTML = items.join("");
}

function buildWhatsAppAlertMessage(data, displayTimestamp, roleLabel) {
  const cameraId = data.camera_id || "N/A";
  const severity = String(data.severity || "unknown").toUpperCase();
  const latitude = data.latitude ?? "N/A";
  const longitude = data.longitude ?? "N/A";
  const imageUrl = data.image_url || "N/A";
  const mapsUrl = latitude !== "N/A" && longitude !== "N/A"
    ? `https://maps.google.com/?q=${latitude},${longitude}`
    : "N/A";

  return [
    "🚨 ACCIDENT ALERT",
    `Role: ${roleLabel}`,
    `Camera: ${cameraId}`,
    `Severity: ${severity}`,
    `Date & Time: ${displayTimestamp}`,
    `Location: ${latitude}, ${longitude}`,
    `Maps: ${mapsUrl}`,
    `Image: ${imageUrl}`,
  ].join("\n");
}

function buildRoleLinks(numbers, roleLabel, data, displayTimestamp) {
  return numbers.map((number) => {
    const message = buildWhatsAppAlertMessage(data, displayTimestamp, roleLabel);
    return {
      number,
      roleLabel,
      url: `https://wa.me/${number}?text=${encodeURIComponent(message)}`,
    };
  });
}

function prepareClientSideWhatsAppAlerts(data, displayTimestamp) {
  const adminNumbers = parseWhatsAppNumbers(document.getElementById("adminWhatsApp")?.value || "");
  const hospitalNumbers = parseWhatsAppNumbers(document.getElementById("hospitalWhatsApp")?.value || "");
  const ambulanceNumbers = parseWhatsAppNumbers(document.getElementById("ambulanceWhatsApp")?.value || "");

  const adminLinks = buildRoleLinks(adminNumbers, "ADMIN", data, displayTimestamp);
  const hospitalLinks = buildRoleLinks(hospitalNumbers, "HOSPITAL", data, displayTimestamp);
  const ambulanceLinks = buildRoleLinks(ambulanceNumbers, "AMBULANCE", data, displayTimestamp);

  return {
    adminLinks,
    hospitalLinks,
    ambulanceLinks,
    recipients: adminLinks.length + hospitalLinks.length + ambulanceLinks.length,
  };
}

function openRoleLinks(links, roleName) {
  if (!links.length) {
    showMessage(`No ${roleName} WhatsApp recipients configured.`);
    return;
  }
  links.forEach((item, index) => {
    setTimeout(() => {
      window.open(item.url, "_blank", "noopener,noreferrer");
    }, index * 250);
  });
}

if (sendAllPanelsBtn) {
  sendAllPanelsBtn.addEventListener("click", () => {
    const allLinks = [
      ...pendingWhatsAppLinksByRole.admin,
      ...pendingWhatsAppLinksByRole.hospital,
      ...pendingWhatsAppLinksByRole.ambulance,
    ];
    openRoleLinks(allLinks, "all panels");
  });
}

if (sendAdminPanelBtn) {
  sendAdminPanelBtn.addEventListener("click", () => {
    openRoleLinks(pendingWhatsAppLinksByRole.admin, "admin");
  });
}

if (sendHospitalPanelBtn) {
  sendHospitalPanelBtn.addEventListener("click", () => {
    openRoleLinks(pendingWhatsAppLinksByRole.hospital, "hospital");
  });
}

if (sendAmbulancePanelBtn) {
  sendAmbulancePanelBtn.addEventListener("click", () => {
    openRoleLinks(pendingWhatsAppLinksByRole.ambulance, "ambulance");
  });
}

function showResultWithSummary(data) {
  const ambulances = data.notified_ambulances || data.notified_drivers || [];
  const hospitals = data.notified_hospitals || [];
  const admins = data.notified_admins || [];

  const rawTimestamp = data.timestamp || "N/A";
  // Format timestamp to readable local time
  let displayTimestamp = rawTimestamp;
  if (rawTimestamp !== "N/A") {
    try {
      const date = new Date(rawTimestamp);
      displayTimestamp = date.toLocaleString("en-US", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
    } catch (e) {
      displayTimestamp = rawTimestamp;
    }
  }
  
  const severity = (data.severity || "unknown").toUpperCase();
  const imageUrl = data.image_url || "N/A";
  const cameraId = data.camera_id || "N/A";
  const confidence = data.confidence ?? "N/A";

  let mapsUrl = "N/A";
  if (data.latitude !== undefined && data.longitude !== undefined) {
    mapsUrl = `https://maps.google.com/?q=${data.latitude},${data.longitude}`;
  }

  // Update results section
  resultsSection.style.display = "grid";
  detectionSection.style.display = "none";

  // Update dispatch stats
  document.getElementById("statAmbulances").textContent = ambulances.length;
  document.getElementById("statHospitals").textContent = hospitals.length;
  document.getElementById("statAdmins").textContent = admins.length;

  // Update dispatch message
  document.getElementById("dispatchMessage").textContent = data.message || "Accident detected from camera preview frames and alerts dispatched.";

  // Update raw response
  const summary = [
    `✅ ${data.message || "Alert processed."}`,
    `🚑 Ambulances alerted: ${ambulances.length}`,
    `🏥 Hospitals alerted: ${hospitals.length}`,
    `🛡 Admins alerted: ${admins.length}`,
    `⏰ Detected at: ${displayTimestamp}`,
    "",
    "Raw Response:",
    JSON.stringify(data, null, 2),
  ].join("\n");

  const whatsappResult = prepareClientSideWhatsAppAlerts(data, displayTimestamp);
  pendingWhatsAppLinksByRole = {
    admin: whatsappResult.adminLinks,
    hospital: whatsappResult.hospitalLinks,
    ambulance: whatsappResult.ambulanceLinks,
  };
  if (whatsAppActions) {
    whatsAppActions.style.display = whatsappResult.recipients > 0 ? "block" : "none";
  }
  renderRoleWhatsAppLinks(adminPanelLinks, whatsappResult.adminLinks);
  renderRoleWhatsAppLinks(hospitalPanelLinks, whatsappResult.hospitalLinks);
  renderRoleWhatsAppLinks(ambulancePanelLinks, whatsappResult.ambulanceLinks);
  const whatsappLines = [];

  if (whatsappResult.recipients > 0) {
    whatsappLines.push(`📲 WhatsApp JS alerts prepared for: ${whatsappResult.recipients} recipient(s)`);
    whatsappLines.push("Use Admin/Hospital/Ambulance panel buttons to open chats.");
  } else {
    whatsappLines.push("📲 No WhatsApp recipients configured in settings.");
  }

  const allLinks = [...whatsappResult.adminLinks, ...whatsappResult.hospitalLinks, ...whatsappResult.ambulanceLinks];
  if (allLinks.length > 0) {
    whatsappLines.push("WhatsApp Links (click if popup blocked):");
    allLinks.forEach((item) => {
      whatsappLines.push(`- ${item.roleLabel} (${item.number}): ${item.url}`);
    });
  }

  output.textContent = [summary, "", ...whatsappLines].join("\n");

  // Update incident details
  document.getElementById("detailCamera").textContent = cameraId;
  document.getElementById("detailSeverity").textContent = severity;
  document.getElementById("detailSeverity").className = `detail-value severity-${severity.toLowerCase()}`;
  document.getElementById("detailConfidence").textContent = `${Math.round(confidence * 100)}%`;
  document.getElementById("detailTime").textContent = displayTimestamp;

  // Update image link and preview
  if (imageUrl && imageUrl !== "N/A") {
    document.getElementById("detailImageLink").href = imageUrl;
    document.getElementById("detailImageLink").textContent = "🖼️ View on Cloudinary";
    
    // Try to load image preview
    const preview = document.getElementById("detailImagePreview");
    preview.innerHTML = `<img src="${imageUrl}" alt="Evidence" onerror="this.style.display='none'">`;
  }

  // Update maps link
  if (mapsUrl !== "N/A") {
    document.getElementById("detailMapsLink").href = mapsUrl;
  }

  // Update meta
  incidentMeta.textContent = [
    `Camera: ${cameraId}`,
    `Severity: ${severity}`,
    `Confidence: ${confidence}`,
    `Time: ${displayTimestamp}`,
    `Image URL: ${imageUrl}`,
    `Google Maps: ${mapsUrl}`,
  ].join("\n");

  // Scroll to results
  setTimeout(() => {
    resultsSection.scrollIntoView({ behavior: "smooth" });
  }, 100);
}

async function post(path, payload) {
  const response = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

async function openCameraPreview(startDetection = true) {
  try {
    hardStopPreview();
    stopFrameDetectionLoop();

    previewStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
    cameraPreview.srcObject = previewStream;
    
    // Show video status indicator
    const videoStatus = document.getElementById("videoStatus");
    videoStatus.classList.add("active");
    videoStatus.textContent = "🔴 LIVE";

    if (startDetection) {
      frameDetectionLoopPromise = startFrameDetectionLoop();
    } else {
      showMessage("Camera preview restored.");
    }
  } catch (error) {
    showMessage(`Unable to open camera preview: ${error.message}`);
  }
}

function stopCameraPreview() {
  stopFrameDetectionLoop();
  hardStopPreview();
  showMessage("Camera preview stopped.");
  
  // Hide video status indicator
  const videoStatus = document.getElementById("videoStatus");
  videoStatus.classList.remove("active");
}

document.getElementById("openCameraBtn").addEventListener("click", openCameraPreview);
document.getElementById("stopCameraBtn").addEventListener("click", stopCameraPreview);

// Back to detection button
document.getElementById("backToDetectionBtn").addEventListener("click", () => {
  resultsSection.style.display = "none";
  detectionSection.style.display = "block";
  stopCameraPreview();
  settingsPanel.classList.remove("open");
  pendingWhatsAppLinksByRole = {
    admin: [],
    hospital: [],
    ambulance: [],
  };
  if (whatsAppActions) {
    whatsAppActions.style.display = "none";
  }
  renderRoleWhatsAppLinks(adminPanelLinks, []);
  renderRoleWhatsAppLinks(hospitalPanelLinks, []);
  renderRoleWhatsAppLinks(ambulancePanelLinks, []);
});

document.getElementById("alertBtn").addEventListener("click", async () => {
  const cameraId = document.getElementById("alertCameraId").value.trim();
  const latText = document.getElementById("alertLat").value.trim();
  const lonText = document.getElementById("alertLon").value.trim();

  const payload = {
    camera_id: cameraId || null,
    latitude: latText ? Number(latText) : null,
    longitude: lonText ? Number(lonText) : null,
    image_url: document.getElementById("alertImageUrl").value.trim() || null,
    image_path: document.getElementById("alertImagePath").value.trim() || null,
    severity: document.getElementById("alertSeverity").value,
  };

  try {
    showMessage("Sending manual alert...");
    const data = await post("/send-alert", payload);
    showResultWithSummary(data);
  } catch (error) {
    showMessage(`Alert failed: ${error.message}`);
  }
});

document.getElementById("alertWhatsAppOnlyBtn").addEventListener("click", async () => {
  const cameraId = document.getElementById("alertCameraId").value.trim();
  const latText = document.getElementById("alertLat").value.trim();
  const lonText = document.getElementById("alertLon").value.trim();

  if (!latText || !lonText) {
    showMessage("❌ Latitude and Longitude are required for manual WhatsApp alert");
    return;
  }

  const payload = {
    camera_id: cameraId || null,
    latitude: Number(latText),
    longitude: Number(lonText),
    image_url: document.getElementById("alertImageUrl").value.trim() || null,
    image_path: document.getElementById("alertImagePath").value.trim() || null,
    severity: document.getElementById("alertSeverity").value,
    whatsapp_only: true,  // Flag to send only WhatsApp, no voice
  };

  try {
    showMessage("Sending WhatsApp-only alert...");
    const data = await post("/send-alert", payload);
    showResultWithSummary(data);
  } catch (error) {
    showMessage(`WhatsApp alert failed: ${error.message}`);
  }
});

