"""Voice alert service using Twilio for emergency calls."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.core.config import get_settings


class VoiceAlertService:
    """Handles emergency voice calls using Twilio API."""

    def __init__(self) -> None:
        """Initialize Twilio client with credentials from settings."""
        from twilio.rest import Client

        settings = get_settings()
        self._twilio_number = settings.twilio_phone_number
        self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    def make_call(
        self,
        *,
        to_number: str,
        location: str,
        severity: str,
        maps_link: str,
        recipient_name: str,
        timestamp: datetime,
    ) -> str:
        """
        Make an emergency call with accident alert information.

        Args:
            to_number: Phone number to call (international format)
            location: Human-readable location (e.g., "Meerut, Uttar Pradesh")
            severity: Severity level (e.g., "high", "critical")
            maps_link: Google Maps link to accident location
            recipient_name: Name of the recipient (ambulance, hospital, etc.)
            timestamp: Timestamp of the accident

        Returns:
            Call SID (unique identifier for the call)
        """
        twiml = self._build_twiml(location, severity, recipient_name, timestamp, maps_link)

        try:
            call = self._client.calls.create(
                twiml=twiml,
                to=to_number,
                from_=self._twilio_number,
            )
            print(f"✅ Voice call initiated: {call.sid}")
            return call.sid

        except Exception as e:
            print(f"❌ Voice call error: {e}")
            raise

    @staticmethod
    def _build_twiml(
        location: str,
        severity: str,
        recipient_name: str,
        timestamp: datetime,
        maps_link: str,
    ) -> str:
        """
        Build TwiML (Twilio Markup Language) response for IVR system.

        Args:
            location: Location of the accident
            severity: Severity level of the accident
            recipient_name: Name of recipient
            timestamp: Time of accident
            maps_link: Google Maps link

        Returns:
            TwiML XML string for voice playback
        """
        time_str = timestamp.strftime("%I:%M %p")
        severity_text = "CRITICAL ACCIDENT" if severity.lower() == "critical" else "ACCIDENT DETECTED"

        twiml = f"""
        <Response>
            <Say>Alert. {severity_text}.</Say>
            <Pause length="1"/>
            <Say>Recipient: {recipient_name}.</Say>
            <Pause length="1"/>
            <Say>Location: {location}.</Say>
            <Pause length="1"/>
            <Say>Severity level: {severity}.</Say>
            <Pause length="1"/>
            <Say>Time: {time_str}.</Say>
            <Pause length="2"/>
            <Say>Google Maps link has been sent to your device. Please respond immediately.</Say>
            <Pause length="1"/>
            <Say>This message will repeat.</Say>
        </Response>
        """
        return twiml.strip()

    def send_emergency_call(
        self,
        *,
        recipient_name: str,
        recipient_phone: str,
        role: str,
        latitude: float,
        longitude: float,
        timestamp: datetime,
        severity: str,
    ) -> str:
        """
        Send emergency call with accident details.

        Args:
            recipient_name: Name of the recipient
            recipient_phone: Phone number in international format
            role: Role (ambulance, hospital, admin)
            latitude: Accident latitude
            longitude: Accident longitude
            timestamp: Accident timestamp
            severity: Accident severity

        Returns:
            Call SID
        """
        # Build location string
        location = self._get_location_string(latitude, longitude)
        maps_link = f"https://maps.google.com/?q={latitude},{longitude}"

        # Get role-specific greeting (this replaces the recipient_name in the call)
        role_greeting = self._get_role_greeting(role)

        # Make the call with role-specific greeting
        return self.make_call(
            to_number=recipient_phone,
            location=location,
            severity=severity,
            maps_link=maps_link,
            recipient_name=role_greeting,  # Use role greeting instead of name
            timestamp=timestamp,
        )

    @staticmethod
    def _get_role_prefix(role: str) -> str:
        """Get role-specific prefix for the call."""
        prefixes = {
            "ambulance": "🚑 Ambulance Alert:",
            "hospital": "🏥 Hospital Alert:",
            "admin": "🛡 Admin Alert:",
            "police": "👮 Police Alert:",
        }
        return prefixes.get(role, "Alert:")

    @staticmethod
    def _get_role_greeting(role: str) -> str:
        """Get role-specific greeting for voice message."""
        greetings = {
            "ambulance": "Ambulance Service",
            "hospital": "Hospital Emergency Department",
            "admin": "Control Room Admin",
            "police": "Police Department",
        }
        return greetings.get(role, "Emergency Responder")

    @staticmethod
    def _get_location_string(latitude: float, longitude: float) -> str:
        """
        Get human-readable location string (can be extended with reverse geocoding).

        Args:
            latitude: Location latitude
            longitude: Location longitude

        Returns:
            Human-readable location string
        """
        # TODO: Integrate with reverse geocoding service (Google Maps API, Nominatim, etc.)
        # For now, return coordinates with generic format
        return f"Latitude {latitude:.4f}, Longitude {longitude:.4f}"
