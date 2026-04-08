import json
from pathlib import Path

from app.core.config import get_settings


class CameraLocationService:
    def __init__(self) -> None:
        settings = get_settings()
        self._file_path: Path = settings.cameras_file_path
        self._cache: dict[str, dict[str, float]] = {}
        self.reload()

    def reload(self) -> None:
        if not self._file_path.exists():
            self._cache = {}
            return
        data = json.loads(self._file_path.read_text(encoding="utf-8"))
        self._cache = {item["camera_id"]: item for item in data}

    def get_location(self, camera_id: str) -> tuple[float, float]:
        settings = get_settings()
        return settings.default_latitude, settings.default_longitude
