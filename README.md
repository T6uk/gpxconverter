# Google Maps Route to GPX Converter

A simple Python Flask web application to convert a Google Maps directions URL into a downloadable GPX file suitable for GPS devices (Garmin, Suunto, Wahoo, etc.) and smartphone apps (Komoot, Gaia GPS, OsmAnd, etc.).

## Features

*   Accepts standard Google Maps directions URLs (typically containing `/dir/...`).
*   Parses origin, destination, and waypoints (both named and coordinates) from the URL path.
*   Uses the official Google Maps Directions API to fetch the route path (overview polyline).
*   Generates a standard GPX file (version 1.1) containing the route as a track.
*   Supports different travel modes (Driving, Walking, Bicycling). Transit mode is experimental as GPX representation might be limited.
*   Simple web interface with user feedback and basic loading indicator.
*   Configurable via environment variables (`.env` file).
*   Includes basic logging to the console.
*   Basic health check endpoint (`/health`).

## Prerequisites

*   Python 3.7+
*   `pip` (Python package installer)
*   `venv` (for creating virtual environments)
*   A **Google Maps API Key** with the **Directions API** enabled. You can get this from the [Google Cloud Console](https://console.cloud.google.com/). Make sure billing is enabled for your Google Cloud project if you exceed the free tier usage.

## Setup

1.  **Clone or Download:**
    Get the code on your machine (e.g., using `git clone` or downloading a ZIP).
    ```bash
    # Example using git:
    # git clone https://github.com/your-username/gmaps-to-gpx-converter.git
    cd gmaps-to-gpx-converter
    ```

2.  **Create and Activate Virtual Environment:**
    It's highly recommended to use a virtual environment to isolate dependencies.
    ```bash
    python -m venv venv
    # On Windows (cmd/powershell)
    .\venv\Scripts\activate
    # On macOS/Linux (bash/zsh)
    source venv/bin/activate
    ```
    You should see `(venv)` prepended to your command prompt.

3.  **Install Dependencies:**
    Install all the required Python packages.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    *   Create a file named `.env` in the project root directory (where `app.py` is).
    *   Copy the contents from the example below into your `.env` file.
    *   **Replace `YOUR_ACTUAL_API_KEY_HERE` with your real Google Maps API key.**
        ```dotenv
        # Replace YOUR_ACTUAL_API_KEY_HERE with your real Google Maps API Key
        # Ensure the Directions API is enabled for this key in Google Cloud Console
        GOOGLE_MAPS_API_KEY=YOUR_ACTUAL_API_KEY_HERE

        # Set to 1 for development (enables debug mode, auto-reloading, more detailed logs)
        # Set to 0 for production deployments
        FLASK_DEBUG=1

        # Optional: Set a fixed secret key for Flask sessions (recommended for production)
        # Generate one using: python -c 'import os; print(os.urandom(24).hex())'
        # FLASK_SECRET_KEY=your_generated_hex_secret_key

        # Optional: Override the default port (5000)
        # PORT=8080
        ```
    *   **Security:** In the Google Cloud Console, restrict your API key to prevent unauthorized use. For local development, you can restrict it to your public IP address(es). For deployment, restrict it to the server's IP address or use HTTP referrer restrictions if applicable.

## Running the Application (Development)

1.  **Ensure your virtual environment is active.** (`source venv/bin/activate` or `.\venv\Scripts\activate`)
2.  **Check your `.env` file:** Make sure `GOOGLE_MAPS_API_KEY` is set and `FLASK_DEBUG=1` is present.
3.  **Start the Flask development server:**
    ```bash
    flask run
    # Or specify host/port explicitly if needed (though defaults in app.py handle debug mode)
    # flask run --host=0.0.0.0 --port=5000
    ```
    *   With `FLASK_DEBUG=1`, `flask run` automatically enables debug mode and typically listens on `0.0.0.0:5000`.

4.  **Access the application:**
    Open your web browser and go to `http://localhost:5000` (or `http://127.0.0.1:5000`). If accessing from another device on your network, use `http://<your-machine-ip>:5000`.

## How to Use

1.  Go to [Google Maps](https://www.google.com/maps) on your desktop browser.
2.  Get directions for a route (Driving, Walking, or Bicycling work best). Include any desired waypoints.
3.  Copy the **entire URL** from the browser's address bar. It should look similar to `https://www.google.com/maps/dir/Origin+Name/WaypointCoord/Destination+Name/...`
4.  Paste the full URL into the input field on the converter web app.
5.  Select the travel mode that matches the route you generated on Google Maps.
6.  Click the "Convert to GPX" button.
7.  Wait for processing (a loading indicator should appear). If successful, the GPX file will be generated and automatically downloaded by your browser. Error messages will appear on the page if something goes wrong.
8.  Transfer the downloaded `.gpx` file to your GPS device or import it into your preferred navigation app.

## Production Deployment

For deploying this application publicly or for more robust usage, **do not use the Flask development server (`flask run`)**. Use a production-ready WSGI server like Gunicorn or Waitress behind a reverse proxy like Nginx or Caddy.

**Example using Gunicorn:**

1.  Install Gunicorn: `pip install gunicorn`
2.  Ensure `FLASK_DEBUG=0` in your `.env` file.
3.  Run Gunicorn (adjust worker count as needed):
    ```bash
    gunicorn --workers 3 --bind 0.0.0.0:5000 app:app
    ```
    You would typically configure Nginx/Caddy to proxy requests to Gunicorn running on a local port (e.g., `127.0.0.1:5000`). Set appropriate environment variables (`GOOGLE_MAPS_API_KEY`, `FLASK_SECRET_KEY`, `FLASK_DEBUG=0`) in your production environment.

## Limitations & Notes

*   **URL Parsing Reliability:** The app relies on parsing common Google Maps URL formats, specifically the `/dir/...` structure. Google can change these formats without notice. URLs not generated directly from the "Directions" function might not parse correctly.
*   **API Quotas & Costs:** The Google Maps Directions API has usage limits and associated costs beyond the free tier. Monitor your usage in the Google Cloud Console. This tool makes one Directions API call per conversion request.
*   **Transit Routes:** Generating GPX for transit routes is experimental. The Directions API often provides a less detailed `overview_polyline` for transit, which may not accurately represent walking segments or the exact path of buses/trains.
*   **Route Detail:** The GPX file contains the track points derived from Google's `overview_polyline`. It does not include turn-by-turn instructions, elevation data (usually), or timestamps. It represents the *path* of the route.
*   **Error Handling:** If conversion fails, check the error messages on the web page and the application logs (console output) for more details. Common issues include invalid API keys, API quota exceeded, or unparseable URLs.

## Contributing

Contributions (bug fixes, improvements, better URL parsing) are welcome! Please feel free to fork the repository and submit a pull request.