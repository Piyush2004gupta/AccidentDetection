import json
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.utils.geo import haversine_km


@dataclass(slots=True)
class AmbulanceDriver:
    name: str
    phone_number: str
    latitude: float
    longitude: float


class AmbulanceService:
    def __init__(self) -> None:
        settings = get_settings()
        self._file_path: Path = settings.ambulances_file_path
        self._cache: list[AmbulanceDriver] = []
        self.reload()

    def reload(self) -> None:
        if not self._file_path.exists():
            self._cache = []
            return

        raw = json.loads(self._file_path.read_text(encoding="utf-8"))
        self._cache = [
            AmbulanceDriver(
                name=item["name"],
                phone_number=item["phone_number"],
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
            )
            for item in raw
        ]

    def nearest(
        self,
        accident_lat: float,
        accident_lon: float,
        *,
        top_k: int,
        radius_km: float,
    ) -> list[tuple[AmbulanceDriver, float]]:
        ranked: list[tuple[AmbulanceDriver, float]] = []
        for driver in self._cache:
            distance = haversine_km(accident_lat, accident_lon, driver.latitude, driver.longitude)
            if distance <= radius_km:
                ranked.append((driver, distance))

        ranked.sort(key=lambda item: item[1])
        return ranked[:top_k]
