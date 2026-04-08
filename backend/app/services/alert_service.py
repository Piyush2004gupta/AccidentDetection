from __future__ import annotations

from datetime import datetime

from app.core.config import get_settings


class WhatsAppAlertService:
    def __init__(self) -> None:
        from twilio.rest import Client

        settings = get_settings()
        self._from = settings.twilio_whatsapp_from
        self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    @staticmethod
    def _to_whatsapp_number(number: str) -> str:
        return number if number.startswith("whatsapp:") else f"whatsapp:{number}"

    @staticmethod
    def _role_instruction(role: str) -> str:
        if role == "ambulance":
            return "🚑 Please respond immediately."
        if role == "hospital":
            return "🏥 Please prepare emergency team and trauma bed."
        return "🛡 Admin alert: coordinate responders and monitor incident."

    @staticmethod
    def _format_alert_datetime(timestamp: datetime) -> tuple[str, str]:
        if timestamp.tzinfo is not None:
            local_dt = timestamp.astimezone()
        else:
            local_dt = timestamp
        return local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%I:%M:%S %p")

    @staticmethod
    def _default_hospital_name() -> str:
        return "Max Hospital"

    def send_alert(
        self,
        *,
        recipient_name: str,
        recipient_phone: str,
        role: str,
        latitude: float,
        longitude: float,
        timestamp: datetime,
        image_url: str,
        severity: str,
    ) -> str:
        settings = get_settings()
        effective_latitude = latitude if latitude is not None else settings.default_latitude
        effective_longitude = longitude if longitude is not None else settings.default_longitude
        maps_link = f"https://maps.google.com/?q={effective_latitude},{effective_longitude}"
        alert_date, alert_time = self._format_alert_datetime(timestamp)
        effective_hospital_name = self._default_hospital_name()

        effective_recipient = recipient_name.strip() if recipient_name and recipient_name.strip() else "Control Room Admin"
        if role == "hospital":
            effective_recipient = self._default_hospital_name()

        instruction = self._role_instruction(role)
        body = (
            "🚨 ACCIDENT DETECTED!\n\n"
            f"Recipient: {effective_recipient} ({role.upper()})\n"
            f"Hospital: {effective_hospital_name}\n"
            f"Severity: {severity.upper()}\n"
            f"📍 Location:\n{maps_link}\n\n"
            f"{instruction}\n\n"
            f"📅 Date: {alert_date}\n"
            f"⏱ Time: {alert_time}"
        )

        message = self._client.messages.create(
            from_=self._to_whatsapp_number(self._from),
            to=self._to_whatsapp_number(recipient_phone),
            body=body,
            media_url=[image_url],
        )
        return message.sid
