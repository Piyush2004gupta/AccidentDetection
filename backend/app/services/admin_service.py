import json
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings


@dataclass(slots=True)
class AdminContact:
    name: str
    phone_number: str


class AdminService:
    def __init__(self) -> None:
        settings = get_settings()
        self._file_path: Path = settings.admins_file_path
        self._cache: list[AdminContact] = []
        self.reload()

    def reload(self) -> None:
        if not self._file_path.exists():
            self._cache = []
            return

        raw = json.loads(self._file_path.read_text(encoding="utf-8"))
        self._cache = [
            AdminContact(
                name=item["name"],
                phone_number=item["phone_number"],
            )
            for item in raw
        ]

    def get_all(self) -> list[AdminContact]:
        return list(self._cache)
