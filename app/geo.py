import os
import requests
from math import radians, cos, sin, asin, sqrt

MAPBOX_TOKEN = os.environ.get('MAPBOX_TOKEN')
ORS_API_KEY = os.environ.get('ORS_API_KEY') or os.environ.get('OPENROUTESERVICE_KEY')


def haversine_miles(lat1, lon1, lat2, lon2):
    """Return distance between two lat/lon points in miles."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 3958.8  # Earth radius in miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return R * c


def geocode_mapbox(address):
    """Geocode an address using Mapbox. Returns (lat, lon) or (None, None).

    Requires MAPBOX_TOKEN in the environment. If not present returns (None, None).
    """
    if not address:
        return None, None
    if not MAPBOX_TOKEN:
        # Fallback to Nominatim when Mapbox token is not provided
        return geocode_nominatim(address)
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{requests.utils.requote_uri(address)}.json"
    params = {"access_token": MAPBOX_TOKEN, "limit": 1}
    try:
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get('features'):
            lon, lat = data['features'][0]['center']
            return lat, lon
    except Exception:
        pass
    return None, None

def geocode_ors(address):
    """Geocode using OpenRouteService. Returns (lat, lon) or (None, None).

    Requires `ORS_API_KEY` in env. Uses the ORS geocode/search endpoint.
    """
    if not address or not ORS_API_KEY:
        return None, None
    url = "https://api.openrouteservice.org/geocode/search"
    params = {"api_key": ORS_API_KEY, "text": address, "size": 1}
    headers = {"User-Agent": "PoolParty/1.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=6)
        r.raise_for_status()
        data = r.json()
        if data.get('features'):
            coords = data['features'][0]['geometry']['coordinates']
            lon, lat = coords[0], coords[1]
            return float(lat), float(lon)
    except Exception:
        pass
    return None, None


def geocode_nominatim(address):
    """Geocode using Nominatim (OpenStreetMap). Returns (lat, lon) or (None, None).

    Note: respect Nominatim usage policy for heavy usage. We set a custom User-Agent.
    """
    if not address:
        return None, None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": "PoolParty/1.0 (contact: none)"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            return lat, lon
    except Exception:
        pass
    return None, None


def geocode_any(address):
    """Try geocoding with ORS, then Mapbox, then Nominatim.

    Returns a tuple (lat, lon, provider) where provider is one of
    'ors', 'mapbox', 'nominatim' or None when geocoding failed.
    """
    if not address:
        return None, None, None

    # Prefer ORS when key is available
    try:
        if ORS_API_KEY:
            lat, lon = geocode_ors(address)
            if lat and lon:
                return lat, lon, 'ors'
    except Exception:
        pass

    # Then try Mapbox (mapbox function already falls back to nominatim when token is missing)
    try:
        lat, lon = geocode_mapbox(address)
        if lat and lon:
            return lat, lon, 'mapbox' if MAPBOX_TOKEN else 'nominatim'
    except Exception:
        pass

    # Finally try Nominatim explicitly
    try:
        lat, lon = geocode_nominatim(address)
        if lat and lon:
            return lat, lon, 'nominatim'
    except Exception:
        pass

    return None, None, None


def route_mapbox(coords):
    """Get a single route from Mapbox Directions.

    coords: list of (lon,lat)
    Returns dict with distance_meters and duration_seconds, or None on error.
    """
    if not MAPBOX_TOKEN:
        return None
    if not coords or len(coords) < 2:
        return None
    coord_str = ";".join([f"{lon},{lat}" for lon, lat in coords])
    url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coord_str}"
    params = {"access_token": MAPBOX_TOKEN, "overview": "simplified", "geometries": "geojson", "steps": "false"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get('routes'):
            route = data['routes'][0]
            return {"distance_meters": route.get('distance'), "duration_seconds": route.get('duration')}
    except Exception:
        pass
    return None

def route_ors(coords):
    """Route using OpenRouteService Directions API. coords: list of (lon,lat).

    Returns dict with distance_meters and duration_seconds or None. Requires ORS_API_KEY.
    """
    if not ORS_API_KEY or not coords or len(coords) < 2:
        return None
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {"Authorization": ORS_API_KEY, "Accept": "application/json", "Content-Type": "application/json"}
    # ORS accepts a list of coordinate pairs [ [lon,lat], [lon,lat], ... ]
    body = {"coordinates": [[c[0], c[1]] for c in coords]}
    try:
        r = requests.post(url, json=body, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        # ORS returns features -> properties -> summary
        feat = data.get('features') and data['features'][0]
        if feat and feat.get('properties') and feat['properties'].get('summary'):
            summ = feat['properties']['summary']
            return {"distance_meters": summ.get('distance'), "duration_seconds": summ.get('duration')}
    except Exception:
        pass
    return None


def route_osrm(coords):
    """Get route from OSRM public demo server. coords: list of (lon,lat).

    Returns dict with distance_meters and duration_seconds or None.
    Note: OSRM public server is for demo/light use.
    """
    if not coords or len(coords) < 2:
        return None
    coord_str = ";".join([f"{lon},{lat}" for lon, lat in coords])
    url = f"https://router.project-osrm.org/route/v1/driving/{coord_str}"
    params = {"overview": "false", "geometries": "geojson", "steps": "false"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get('routes'):
            route = data['routes'][0]
            return {"distance_meters": route.get('distance'), "duration_seconds": route.get('duration')}
    except Exception:
        pass
    return None

    return None


def estimate_duration_seconds_from_meters(distance_meters, avg_speed_mph=35):
    """Estimate duration (seconds) from distance in meters using avg speed in mph."""
    try:
        if distance_meters is None:
            return None
        # meters per second = mph * 0.44704
        avg_mps = avg_speed_mph * 0.44704
        if avg_mps <= 0:
            return None
        return int(round(distance_meters / avg_mps))
    except Exception:
        return None


def route_result_is_reasonable(route, lat1, lon1, lat2, lon2, max_duration_seconds=86400, max_distance_ratio=10.0):
    """Basic sanity checks for a routing result.

    - If route is None, return False.
    - If route duration > max_duration_seconds (default 24h) return False.
    - If route distance is more than max_distance_ratio times straight-line distance, return False.

    Returns True if route appears reasonable.
    """
    try:
        if not route:
            return False
        dur = route.get('duration_seconds')
        dist = route.get('distance_meters')
        if dur is None or dist is None:
            return True  # can't judge, assume ok
        if dur > max_duration_seconds:
            return False
        # compute straight-line meters
        miles = haversine_miles(lat1, lon1, lat2, lon2)
        if miles is None:
            return True
        straight_m = miles * 1609.344
        if straight_m <= 0:
            return True
        # distance ratio check
        if dist / straight_m > max_distance_ratio:
            return False
        # duration ratio check: ensure route duration isn't wildly larger than a straight-line estimate
        try:
            # estimate duration at a reasonable avg speed (35 mph)
            est_dur = estimate_duration_seconds_from_meters(straight_m, avg_speed_mph=35)
            if est_dur and dur / est_dur > 5.0:
                return False
        except Exception:
            pass
        return True
    except Exception:
        return False


def route_any(coords):
    """Try Mapbox, then OSRM, then return None.

    This prefers real road routing results (distance and duration). If both
    external services fail, caller can fall back to haversine-based estimate.
    """
    # Try Mapbox first (if token present)
    try:
        if MAPBOX_TOKEN:
            m = route_mapbox(coords)
            if m:
                return m
    except Exception:
        pass

    # Try OpenRouteService next (requires key)
    try:
        if ORS_API_KEY:
            o = route_ors(coords)
            if o:
                return o
    except Exception:
        pass

    # Try OSRM public server as a last resort
    try:
        o2 = route_osrm(coords)
        if o2:
            return o2
    except Exception:
        pass

    return None

    # Try OSRM public server
    try:
        o = route_osrm(coords)
        if o:
            return o
    except Exception:
        pass

    return None


def google_maps_directions_url(origin=None, destination=None, origin_lat=None, origin_lng=None, dest_lat=None, dest_lng=None):
    """Build a Google Maps directions URL.

    Prefer human-readable address strings if provided (origin/destination). If not,
    fall back to coordinates when available (format: lat,lng).

    Returns a string URL suitable for opening in a browser.
    """
    base = "https://www.google.com/maps/dir/?api=1"
    params = []
    def _quote(v):
        from urllib.parse import quote_plus
        return quote_plus(str(v))

    if origin:
        params.append("origin=" + _quote(origin))
    elif origin_lat is not None and origin_lng is not None:
        params.append("origin=" + _quote(str(origin_lat) + "," + str(origin_lng)))

    if destination:
        params.append("destination=" + _quote(destination))
    elif dest_lat is not None and dest_lng is not None:
        params.append("destination=" + _quote(str(dest_lat) + "," + str(dest_lng)))

    # default to driving directions
    params.append("travelmode=driving")

    if len(params) == 1:
        # only one side known; let Google Maps show pin / place
        return base + "&" + params[0]
    return base + "&" + "&".join(params)
