from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.config import get_settings


class CloudinaryService:
    def __init__(self) -> None:
        import cloudinary
        import cloudinary.uploader as uploader

        self._cloudinary = cloudinary
        self._uploader = uploader
        settings = get_settings()
        cloud_name = settings.cloudinary_cloud_name.strip()
        api_key = settings.cloudinary_api_key.strip()
        api_secret = settings.cloudinary_api_secret.strip()

        if settings.cloudinary_url:
            parsed = urlparse(settings.cloudinary_url)
            if parsed.scheme == "cloudinary":
                cloud_name = cloud_name or (parsed.hostname or "")
                api_key = api_key or (unquote(parsed.username) if parsed.username else "")
                api_secret = api_secret or (unquote(parsed.password) if parsed.password else "")

        if cloud_name and api_key and api_secret:
            self._cloudinary.config(
                cloud_name=cloud_name,
                api_key=api_key,
                api_secret=api_secret,
                secure=True,
            )

    def upload_image(self, image_path: str | Path, public_id: str | None = None) -> str:
        result = self._uploader.upload(
            str(image_path),
            folder="accident_alerts",
            public_id=public_id,
            resource_type="image",
            overwrite=False,
        )
        return result["secure_url"]
