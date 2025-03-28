import gpxpy
import gpxpy.gpx
from datetime import datetime, timedelta
import secrets
from flask import current_app


def log_info(message):
    """Log informational messages"""
    if hasattr(current_app, 'logger'):
        current_app.logger.info(message)
    else:
        print(message)


def create_gpx(coordinates, name="Google Maps Route", travel_mode="walking"):
    """
    Create a GPX file from a list of coordinates with improved metadata

    Parameters:
    coordinates (list): List of (latitude, longitude) tuples
    name (str): Name for the GPX track
    travel_mode (str): Travel mode (walking, cycling, driving, etc.)

    Returns:
    str: GPX content as XML string
    """
    # Input validation
    if not coordinates or len(coordinates) < 2:
        raise ValueError("At least two coordinate points are required to create a GPX route")

    if not isinstance(name, str) or not name.strip():
        name = f"Route {datetime.now().strftime('%Y-%m-%d')}"

    # Sanitize travel mode
    valid_modes = ["walking", "cycling", "driving", "running", "hiking", "transit", "unknown"]
    if travel_mode.lower() not in valid_modes:
        travel_mode = "unknown"

    # Create GPX object
    gpx_obj = gpxpy.gpx.GPX()

    # Set metadata directly on the GPX object
    gpx_obj.name = name
    gpx_obj.description = f"Converted from Google Maps on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    gpx_obj.author_name = "Google Maps to GPX Converter"

    # Add creator info
    gpx_obj.creator = "Google Maps to GPX Converter v1.0"

    # Set metadata time
    gpx_obj.time = datetime.now()

    # Add keywords for better compatibility
    keywords = f"google maps,{travel_mode},gpx,navigation"
    gpx_obj.keywords = keywords

    # Create track
    track = gpxpy.gpx.GPXTrack()
    track.name = name
    track.type = travel_mode.capitalize()  # Set activity type

    # Add track description
    track.description = f"Route exported from Google Maps ({travel_mode})"

    # Add track to GPX
    gpx_obj.tracks.append(track)

    # Create segment
    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    # Add points with timestamps
    # Start time roughly now, with interval between points
    base_time = datetime.now()

    # Calculate a reasonable time interval based on travel mode and number of points
    # This helps create more realistic timestamps
    total_distance_meters = calculate_total_distance(coordinates)
    point_count = len(coordinates)

    # Estimate reasonable speeds based on travel mode (in m/s)
    speeds = {
        "walking": 1.4,  # ~5 km/h
        "hiking": 1.0,  # ~3.6 km/h
        "running": 3.0,  # ~10.8 km/h
        "cycling": 4.2,  # ~15 km/h
        "driving": 13.9,  # ~50 km/h
        "transit": 8.3,  # ~30 km/h
        "unknown": 2.8  # ~10 km/h
    }

    speed = speeds.get(travel_mode.lower(), speeds["unknown"])

    # Estimate total duration and calculate interval
    estimated_duration_seconds = total_distance_meters / speed
    time_interval = estimated_duration_seconds / (point_count - 1) if point_count > 1 else 10

    log_info(
        f"Created GPX with {point_count} points, estimated duration: {estimated_duration_seconds / 60:.1f} minutes")

    for i, (lat, lon) in enumerate(coordinates):
        # Validate coordinates
        try:
            lat_float = float(lat)
            lon_float = float(lon)

            if not (-90 <= lat_float <= 90) or not (-180 <= lon_float <= 180):
                log_info(f"Invalid coordinates at point {i}: {lat_float}, {lon_float} - skipping")
                continue

        except (ValueError, TypeError) as e:
            log_info(f"Error parsing coordinates at point {i}: {e} - skipping")
            continue

        # Calculate time with proper delta
        seconds_to_add = i * time_interval
        point_time = base_time + timedelta(seconds=seconds_to_add)

        # Create track point with unique identifier for better device compatibility
        point = gpxpy.gpx.GPXTrackPoint(
            latitude=lat,
            longitude=lon,
            elevation=0,  # Set default elevation to 0
            time=point_time
        )

        # Add a unique identifier to each point for better compatibility
        point_id = f"pt-{secrets.token_hex(4)}-{i}"
        point.name = point_id

        # Add the point to the segment
        segment.points.append(point)

    # Generate GPX string
    gpx_xml = gpx_obj.to_xml()

    return gpx_xml


def calculate_total_distance(coordinates):
    """
    Calculate approximate total distance of route in meters

    Parameters:
    coordinates (list): List of (latitude, longitude) tuples

    Returns:
    float: Approximate distance in meters
    """
    import math

    def haversine(lat1, lon1, lat2, lon2):
        """Calculate the great circle distance between two points in meters"""
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        r = 6371000  # Radius of earth in meters
        return c * r

    total_distance = 0
    for i in range(len(coordinates) - 1):
        lat1, lon1 = coordinates[i]
        lat2, lon2 = coordinates[i + 1]
        try:
            segment_distance = haversine(lat1, lon1, lat2, lon2)
            total_distance += segment_distance
        except (ValueError, TypeError):
            continue  # Skip invalid coordinates

    return total_distance