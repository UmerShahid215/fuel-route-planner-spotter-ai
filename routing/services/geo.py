import numpy as np

EARTH_RADIUS_MILES = 3958.8
METERS_PER_MILE = 1609.344


def haversine_miles(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = (np.radians(v) for v in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def to_unit_xyz(lat, lon):
    lat, lon = np.radians(lat), np.radians(lon)
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


def miles_to_chord(miles):
    return 2 * np.sin(miles / (2 * EARTH_RADIUS_MILES))


def chord_to_miles(chord):
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.clip(np.asarray(chord) / 2, 0, 1))


def densify(latlon, step_miles=1.0):
    """Interpolate an (n, 2) lat/lon polyline so no gap exceeds step_miles; returns (points, cumulative_miles)."""
    latlon = np.asarray(latlon, dtype=float)
    if len(latlon) < 2:
        return latlon, np.zeros(len(latlon))
    lat, lon = latlon[:, 0], latlon[:, 1]
    seg = haversine_miles(lat[:-1], lon[:-1], lat[1:], lon[1:])
    pieces = np.maximum(np.ceil(seg / step_miles).astype(int), 1)
    idx = np.repeat(np.arange(len(seg)), pieces)
    t = (np.arange(pieces.sum()) - np.repeat(np.cumsum(pieces) - pieces, pieces)) / pieces[idx]
    cum = np.concatenate(([0.0], np.cumsum(seg)))
    points = np.column_stack((lat[idx] + (lat[idx + 1] - lat[idx]) * t, lon[idx] + (lon[idx + 1] - lon[idx]) * t))
    miles = cum[idx] + seg[idx] * t
    return np.vstack((points, latlon[-1])), np.append(miles, cum[-1])
