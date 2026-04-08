from __future__ import annotations

import logging
import shutil
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DetectionResult:
    accident_detected: bool
    confidence: float
    severity: str
    detections: list[dict[str, Any]]
    frame_width: int
    frame_height: int


class AccidentDetector:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.model_type = self.settings.model_type.lower().strip()
        self.model_path = Path(self.settings.model_path)
        self.threshold = self.settings.detection_confidence_threshold
        self.model: Any = None
        self.timesformer_num_frames: int = 0
        self.timesformer_image_size: int = 224
        self.required_frames: int = 1
        self.vehicle_class_names = {
            "car",
            "truck",
            "bus",
            "motorcycle",
            "bicycle",
            "van",
            "auto",
            "rickshaw",
            "scooter",
        }
        self.accident_keywords = {"accident", "crash", "collision", "rollover", "fire"}

        self._load_model()

    @staticmethod
    def _install_torch_compat_shims() -> None:
        import torch
        import torch.nn.modules.linear as linear

        if not hasattr(linear, "_LinearWithBias"):
            linear._LinearWithBias = torch.nn.Linear

        if "torch._six" not in sys.modules:
            import collections.abc

            six_mod = types.ModuleType("torch._six")
            six_mod.container_abcs = collections.abc
            six_mod.int_classes = (int,)
            six_mod.string_classes = (str,)
            six_mod.FileNotFoundError = FileNotFoundError
            sys.modules["torch._six"] = six_mod

    def _try_load_timesformer_state_dict(self) -> bool:
        import torch
        import torch.nn as nn

        checkpoint = torch.load(str(self.model_path), map_location=self.settings.device)
        if not isinstance(checkpoint, dict):
            return False
        if "model.time_embed" not in checkpoint or "model.patch_embed.proj.weight" not in checkpoint:
            return False

        self._install_torch_compat_shims()
        from timesformer.models.vit import TimeSformer

        num_frames = int(checkpoint["model.time_embed"].shape[1])
        image_size = int((checkpoint["model.pos_embed"].shape[1] - 1) ** 0.5 * 16)
        num_classes = int(checkpoint["model.head.4.weight"].shape[0])

        base_model = TimeSformer(
            img_size=image_size,
            patch_size=16,
            num_classes=num_classes,
            num_frames=num_frames,
            attention_type="divided_space_time",
        )
        base_model.load_state_dict(checkpoint, strict=False)

        head = nn.Sequential(
            nn.Identity(),
            nn.Linear(768, 256),
            nn.Identity(),
            nn.BatchNorm1d(256),
            nn.Linear(256, num_classes),
        )
        head_state = {k.replace("model.head.", ""): v for k, v in checkpoint.items() if k.startswith("model.head.")}
        head.load_state_dict(head_state, strict=False)

        base_model.model.head = nn.Identity()
        base_model.eval()
        head.eval()

        self.model = {"backbone": base_model, "head": head}
        self.timesformer_num_frames = num_frames
        self.timesformer_image_size = image_size
        self.required_frames = num_frames
        self.model_type = "timesformer_state_dict"
        logger.warning(
            "Loaded custom TimeSformer state_dict checkpoint: frames=%s image_size=%s",
            num_frames,
            image_size,
        )
        return True

    def _load_model(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found at {self.model_path}")

        if self.model_type == "yolo":
            from ultralytics import YOLO

            model_path_for_yolo = self.model_path
            if self.model_path.suffix.lower() == ".pth":
                converted_path = self.model_path.with_suffix(".pt")
                if not converted_path.exists():
                    shutil.copy2(self.model_path, converted_path)
                model_path_for_yolo = converted_path
                logger.warning(
                    "MODEL_PATH has .pth suffix for YOLO. Using copied .pt path: %s",
                    model_path_for_yolo,
                )

            try:
                self.model = YOLO(str(model_path_for_yolo))
                self.model_type = "yolo"
            except Exception as exc:
                if self.model_path.suffix.lower() == ".pth":
                    try:
                        import torch

                        self.model = torch.jit.load(str(self.model_path), map_location=self.settings.device)
                        self.model.eval()
                        self.model_type = "torchscript"
                        logger.warning(
                            "YOLO load failed for %s; using TorchScript fallback for .pth checkpoint.",
                            self.model_path,
                        )
                    except Exception as ts_exc:
                        try:
                            if not self._try_load_timesformer_state_dict():
                                raise RuntimeError("TimeSformer markers not found")
                        except Exception as custom_exc:
                            raise RuntimeError(
                                "Unable to load checkpoint as YOLO, TorchScript, or TimeSformer state_dict. "
                                "Use an Ultralytics .pt model for MODEL_TYPE=yolo, a valid TorchScript file for "
                                "MODEL_TYPE=torchscript, or provide the original model architecture for this .pth file."
                            ) from custom_exc
                else:
                    raise RuntimeError(
                        "Unable to load YOLO model. If your checkpoint is not an Ultralytics .pt model, "
                        "export/convert it to a supported YOLO .pt format or set MODEL_TYPE correctly."
                    ) from exc
            logger.info("Loaded YOLO model from %s", self.model_path)
            return

        if self.model_type == "torchscript":
            import torch

            self.model = torch.jit.load(str(self.model_path), map_location=self.settings.device)
            self.model.eval()
            logger.info("Loaded TorchScript model from %s", self.model_path)
            return

        raise ValueError("MODEL_TYPE must be one of: yolo, torchscript")

    def infer(self, frame_or_frames) -> DetectionResult:
        if isinstance(frame_or_frames, list):
            if not frame_or_frames:
                return DetectionResult(
                    accident_detected=False,
                    confidence=0.0,
                    severity="none",
                    detections=[],
                    frame_width=0,
                    frame_height=0,
                )
            frame = frame_or_frames[-1]
            frames = frame_or_frames
        else:
            frame = frame_or_frames
            frames = [frame_or_frames]

        if self.model_type == "yolo":
            return self._infer_yolo(frame)
        if self.model_type == "torchscript":
            return self._infer_torchscript(frame)
        if self.model_type == "timesformer_state_dict":
            return self._infer_timesformer_state_dict(frames)
        return DetectionResult(
            accident_detected=False,
            confidence=0.0,
            severity="unknown",
            detections=[],
            frame_width=int(frame.shape[1]) if hasattr(frame, "shape") else 0,
            frame_height=int(frame.shape[0]) if hasattr(frame, "shape") else 0,
        )

    def _infer_yolo(self, frame) -> DetectionResult:
        results = self.model.predict(source=frame, verbose=False, conf=self.threshold)
        if not results:
            return DetectionResult(
                accident_detected=False,
                confidence=0.0,
                severity="none",
                detections=[],
                frame_width=int(frame.shape[1]),
                frame_height=int(frame.shape[0]),
            )

        result = results[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return DetectionResult(
                accident_detected=False,
                confidence=0.0,
                severity="none",
                detections=[],
                frame_width=int(frame.shape[1]),
                frame_height=int(frame.shape[0]),
            )

        names = result.names if hasattr(result, "names") else {}
        detections: list[dict[str, Any]] = []
        accident_confidences: list[float] = []

        for index in range(len(boxes)):
            cls_idx = int(boxes.cls[index].item()) if boxes.cls is not None else -1
            class_name = str(names.get(cls_idx, cls_idx)).lower()
            confidence = float(boxes.conf[index].item()) if boxes.conf is not None else 0.0
            coords = boxes.xyxy[index].tolist() if boxes.xyxy is not None else [0, 0, 0, 0]

            is_vehicle = class_name in self.vehicle_class_names
            is_accident = any(keyword in class_name for keyword in self.accident_keywords)

            if not is_vehicle and not is_accident:
                continue

            if is_accident:
                accident_confidences.append(confidence)

            detections.append(
                {
                    "class_name": class_name,
                    "confidence": confidence,
                    "bbox": [float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])],
                    "is_accident": is_accident,
                    "is_vehicle": is_vehicle,
                }
            )

        if not accident_confidences:
            return DetectionResult(
                accident_detected=False,
                confidence=0.0,
                severity="none",
                detections=detections,
                frame_width=int(frame.shape[1]),
                frame_height=int(frame.shape[0]),
            )

        conf = max(accident_confidences)
        severity = self._confidence_to_severity(conf)
        return DetectionResult(
            accident_detected=True,
            confidence=conf,
            severity=severity,
            detections=detections,
            frame_width=int(frame.shape[1]),
            frame_height=int(frame.shape[0]),
        )

    def _infer_torchscript(self, frame) -> DetectionResult:
        import torch
        import cv2

        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(image).float().permute(2, 0, 1).unsqueeze(0) / 255.0
        with torch.no_grad():
            prediction = self.model(tensor)

        if isinstance(prediction, (list, tuple)):
            score = float(prediction[0].squeeze().item())
        elif hasattr(prediction, "item"):
            score = float(prediction.item())
        else:
            score = float(prediction)

        detected = score >= self.threshold
        severity = self._confidence_to_severity(score) if detected else "none"
        return DetectionResult(
            accident_detected=detected,
            confidence=score,
            severity=severity,
            detections=[],
            frame_width=int(frame.shape[1]),
            frame_height=int(frame.shape[0]),
        )

    def _infer_timesformer_state_dict(self, frames: list) -> DetectionResult:
        import cv2
        import torch

        backbone = self.model["backbone"]
        head = self.model["head"]

        clip_frames = frames[-self.timesformer_num_frames :]
        if len(clip_frames) < self.timesformer_num_frames:
            clip_frames = [clip_frames[-1]] * (self.timesformer_num_frames - len(clip_frames)) + clip_frames

        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)

        processed_frames = []
        for frame in clip_frames:
            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = cv2.resize(image, (self.timesformer_image_size, self.timesformer_image_size))
            tensor = torch.from_numpy(image).float().permute(2, 0, 1) / 255.0
            tensor = (tensor - mean) / std
            processed_frames.append(tensor)

        clip = torch.stack(processed_frames, dim=1).unsqueeze(0)

        with torch.no_grad():
            features = backbone.model.forward_features(clip)
            logits = head(features)
            probabilities = torch.softmax(logits, dim=1)

        class_count = int(probabilities.shape[1])
        class_index = self.settings.accident_class_index
        if class_count == 1:
            score = float(probabilities[0, 0].item())
        else:
            if class_index < 0 or class_index >= class_count:
                class_index = min(1, class_count - 1)
            score = float(probabilities[0, class_index].item())

        detected = score >= self.threshold
        severity = self._confidence_to_severity(score) if detected else "none"
        frame = frames[-1]
        return DetectionResult(
            accident_detected=detected,
            confidence=score,
            severity=severity,
            detections=[],
            frame_width=int(frame.shape[1]),
            frame_height=int(frame.shape[0]),
        )

    @staticmethod
    def _confidence_to_severity(confidence: float) -> str:
        if confidence >= 0.85:
            return "high"
        if confidence >= 0.65:
            return "medium"
        return "low"
