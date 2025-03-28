import gpxpy
import gpxpy.gpx
from datetime import datetime, timedelta


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
    # Create GPX object
    gpx_obj = gpxpy.gpx.GPX()

    # Set metadata directly on the GPX object
    gpx_obj.name = name
    gpx_obj.description = f"Converted from Google Maps on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    gpx_obj.author_name = "Google Maps to GPX Converter"

    # Set metadata time
    gpx_obj.time = datetime.now()

    # Create track
    track = gpxpy.gpx.GPXTrack()
    track.name = name
    track.type = travel_mode.capitalize()  # Set activity type
    gpx_obj.tracks.append(track)

    # Create segment
    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    # Add points with timestamps
    # Start time roughly now, with 10-second intervals between points
    base_time = datetime.now()

    for i, (lat, lon) in enumerate(coordinates):
        # Calculate time with proper delta
        seconds_to_add = i * 10
        point_time = base_time + timedelta(seconds=seconds_to_add)

        # Create track point
        point = gpxpy.gpx.GPXTrackPoint(
            latitude=lat,
            longitude=lon,
            elevation=0,
            time=point_time
        )

        # Add the point to the segment
        segment.points.append(point)

    # Generate GPX string
    gpx_xml = gpx_obj.to_xml()

    return gpx_xml