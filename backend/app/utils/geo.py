from math import asin, cos, radians, sin, sqrt


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0

    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    lat1_r = radians(lat1)
    lat2_r = radians(lat2)

    a = sin(d_lat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(d_lon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return radius_km * c
