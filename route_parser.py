import re
import requests
import urllib.parse
import os
from datetime import datetime


def extract_coordinates_from_google_maps_url(url):
    """
    Extract coordinates from a Google Maps URL with support for complex routes and multiple waypoints

    Parameters:
    url (str): Google Maps URL

    Returns:
    list: List of (latitude, longitude) tuples representing all waypoints in the route
    """
    # Handle shortened URLs (e.g., goo.gl links)
    if any(domain in url for domain in ['goo.gl/maps', 'maps.app.goo.gl']):
        try:
            response = requests.get(url, allow_redirects=True)
            url = response.url
        except Exception as e:
            print(f"Error expanding shortened URL: {e}")

    # Extract all waypoints from the URL's 'dir/' section
    waypoints = []

    # Pattern to get the entire part after 'dir/' and before '@'
    dir_path_pattern = r'maps/dir/([^@]+)'
    dir_path_match = re.search(dir_path_pattern, url)

    if dir_path_match:
        # Split by '/' to get individual waypoints
        path_elements = dir_path_match.group(1).split('/')

        # Process each waypoint
        for element in path_elements:
            if not element:  # Skip empty elements
                continue

            # Check if it's a coordinate pair (lat,lng)
            coord_pattern = r'^(-?\d+\.\d+),(-?\d+\.\d+)$'
            coord_match = re.match(coord_pattern, element)

            if coord_match:
                # It's a direct coordinate
                lat = float(coord_match.group(1))
                lng = float(coord_match.group(2))
                waypoints.append((lat, lng))
            else:
                # It's a place name, try to geocode it
                try:
                    place_name = urllib.parse.unquote(element)
                    if place_name and place_name.strip():  # Skip empty or whitespace-only names
                        coords = geocode_address(place_name)
                        if coords:
                            waypoints.append(coords)
                except Exception as e:
                    print(f"Error geocoding place name '{element}': {e}")

    # Extract the travel mode for better information
    travel_mode = extract_travel_mode(url)
    print(f"Detected travel mode: {travel_mode}")

    # If we have waypoints, use them to get the full route with road-following
    if waypoints and len(waypoints) >= 2:
        # Get API key if available
        api_key = os.environ.get('GOOGLE_MAPS_API_KEY')

        # For routes with Google API key, use Directions API to get road-following path
        if api_key:
            # Use first point as start, last point as end, and middle points as waypoints
            start = waypoints[0]
            end = waypoints[-1]
            middle_waypoints = waypoints[1:-1] if len(waypoints) > 2 else []

            return get_directions_from_google_api(
                start[0], start[1],
                end[0], end[1],
                travel_mode,
                middle_waypoints
            )
        else:
            print("No Google API key found. Road-following routes require an API key.")
            return waypoints

    # If we couldn't extract waypoints or only have one waypoint, try more patterns
    if not waypoints or len(waypoints) < 2:
        # Look for center coordinates (@lat,lon)
        center_pattern = r'@(-?\d+\.\d+),(-?\d+\.\d+)'
        center_match = re.search(center_pattern, url)

        # Look for data coordinates (often in format !2d<lon>!3d<lat>)
        data_coords = []
        data_pattern = r'!2d([-\d.]+)!3d([-\d.]+)'
        data_matches = re.findall(data_pattern, url)

        if data_matches:
            for lng, lat in data_matches:
                data_coords.append((float(lat), float(lng)))

        # If we found data coordinates, use them
        if data_coords:
            return data_coords

        # If we found a center coordinate, use it as a last resort
        if center_match:
            lat = float(center_match.group(1))
            lng = float(center_match.group(2))
            return [(lat, lng)]

    # If we have waypoints, return them
    if waypoints:
        return waypoints

    # If we got here, we couldn't extract anything useful
    print("Could not extract coordinates from URL")
    return None


def extract_travel_mode(url):
    """
    Extract the travel mode from a Google Maps URL

    Parameters:
    url (str): Google Maps URL

    Returns:
    str: Travel mode (walking, driving, cycling, transit, or unknown)
    """
    mode_pattern = r'!3e(\d+)'
    mode_match = re.search(mode_pattern, url)

    if not mode_match:
        return "unknown"

    # Google Maps mode codes
    mode_map = {
        "0": "driving",
        "1": "cycling",
        "2": "walking",
        "3": "transit",
        "4": "flight"
    }

    return mode_map.get(mode_match.group(1), "unknown")


def geocode_address(address):
    """
    Convert an address to coordinates using a geocoding service

    Parameters:
    address (str): Address or place name to geocode

    Returns:
    tuple: (latitude, longitude) or None if geocoding failed
    """
    try:
        # Use Nominatim (OpenStreetMap) for geocoding
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": address,
                "format": "json",
                "limit": 1
            },
            headers={
                "User-Agent": "GoogleMapsToGPXConverter/1.0",
                "Accept-Language": "en-US,en;q=0.9"
            }
        )

        # Check if we got a successful response
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                return (float(data[0]['lat']), float(data[0]['lon']))
    except Exception as e:
        print(f"Geocoding error: {e}")

    return None


def get_directions_from_google_api(start_lat, start_lon, end_lat, end_lon, mode="walking", waypoints=None):
    """
    Get detailed route waypoints from Google Directions API

    Note: Requires a valid Google API key stored in the GOOGLE_API_KEY environment variable

    Parameters:
    start_lat (float): Starting point latitude
    start_lon (float): Starting point longitude
    end_lat (float): Ending point latitude
    end_lon (float): Ending point longitude
    mode (str): Travel mode (walking, driving, bicycling, transit)
    waypoints (list): Optional list of waypoints (lat, lon) tuples

    Returns:
    list: List of (latitude, longitude) tuples for the route
    """
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')

    if not api_key:
        print("No Google API key found. Using direct line between points.")
        # No API key, return direct line
        if waypoints and len(waypoints) > 0:
            # If we have waypoints, include them in the direct path
            result = [(start_lat, start_lon)]
            result.extend(waypoints)
            result.append((end_lat, end_lon))
            return result
        else:
            # Just start and end points
            return [(start_lat, start_lon), (end_lat, end_lon)]

    # Valid modes for the Google API
    valid_modes = {
        "walking": "walking",
        "driving": "driving",
        "cycling": "bicycling",
        "bicycling": "bicycling",
        "transit": "transit"
    }

    # Map our internal mode names to Google API mode names
    google_mode = valid_modes.get(mode.lower(), "walking")

    try:
        # Prepare the API request
        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": f"{start_lat},{start_lon}",
            "destination": f"{end_lat},{end_lon}",
            "mode": google_mode,
            "key": api_key
        }

        # Add waypoints if provided
        if waypoints and len(waypoints) > 0:
            # Format waypoints as required by the API
            waypoints_str = "|".join([f"{lat},{lon}" for lat, lon in waypoints])
            params["waypoints"] = waypoints_str

        # Make the request
        response = requests.get(url, params=params)
        data = response.json()

        if data['status'] == 'OK':
            # Extract route points from the response
            coordinates = []
            route = data['routes'][0]

            # Process each leg (a leg is the route between two waypoints)
            for leg in route['legs']:
                # Add the start location of the leg if it's not already added
                if not coordinates or coordinates[-1] != (leg['start_location']['lat'], leg['start_location']['lng']):
                    coordinates.append((leg['start_location']['lat'], leg['start_location']['lng']))

                # Process each step in the leg
                for step in leg['steps']:
                    # Decode the polyline for this step to get detailed path points
                    if 'polyline' in step and 'points' in step['polyline']:
                        polyline_points = decode_polyline(step['polyline']['points'])
                        if polyline_points:
                            coordinates.extend(polyline_points)

                    # Add the end location of this step
                    coordinates.append((step['end_location']['lat'], step['end_location']['lng']))

                # Make sure we add the end location of the leg
                if coordinates[-1] != (leg['end_location']['lat'], leg['end_location']['lng']):
                    coordinates.append((leg['end_location']['lat'], leg['end_location']['lng']))

            # Remove any duplicate consecutive points
            deduplicated = []
            for point in coordinates:
                if not deduplicated or deduplicated[-1] != point:
                    deduplicated.append(point)

            return deduplicated
        else:
            print(f"Google Directions API error: {data['status']}")
            print(f"For mode: {google_mode}")
            # Fall back to direct line
            if waypoints and len(waypoints) > 0:
                result = [(start_lat, start_lon)]
                result.extend(waypoints)
                result.append((end_lat, end_lon))
                return result
            else:
                return [(start_lat, start_lon), (end_lat, end_lon)]

    except Exception as e:
        print(f"Error with Google Directions API: {e}")
        # Fall back to direct line
        if waypoints and len(waypoints) > 0:
            result = [(start_lat, start_lon)]
            result.extend(waypoints)
            result.append((end_lat, end_lon))
            return result
        else:
            return [(start_lat, start_lon), (end_lat, end_lon)]


def decode_polyline(polyline_str):
    """
    Decode a Google encoded polyline string into a list of coordinates

    Parameters:
    polyline_str (str): Google encoded polyline

    Returns:
    list: List of (latitude, longitude) tuples
    """
    # Implementation based on Google's algorithm
    # https://developers.google.com/maps/documentation/utilities/polylinealgorithm

    points = []
    index = lat = lng = 0

    while index < len(polyline_str):
        # For each dimension (lat and lng)
        for b in range(2):
            shift = result = 0

            while True:
                byte = ord(polyline_str[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if not byte >= 0x20:
                    break

            if result & 1:
                result = ~(result >> 1)
            else:
                result = result >> 1

            if b == 0:
                lat += result
            else:
                lng += result

        points.append((lat / 100000.0, lng / 100000.0))

    return points