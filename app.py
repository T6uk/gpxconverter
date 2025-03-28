import os
import tempfile
from flask import Flask, render_template, request, send_file, jsonify, flash, redirect, url_for
from route_parser import extract_coordinates_from_google_maps_url, extract_travel_mode
from gpx_generator import create_gpx
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file (for Google API key)
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For flash messages

print(f"API KEY: {os.environ.get('GOOGLE_MAPS_API_KEY')}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/convert', methods=['POST'])
def convert():
    google_maps_url = request.form.get('google_maps_url')
    route_name = request.form.get('route_name') or "Google Maps Route"

    if not google_maps_url:
        flash("Please provide a Google Maps URL", "error")
        return redirect(url_for('index'))

    # Detect travel mode
    travel_mode = extract_travel_mode(google_maps_url)

    # Extract coordinates from the URL
    coordinates = extract_coordinates_from_google_maps_url(google_maps_url)

    if not coordinates or len(coordinates) < 2:
        flash("Could not extract route coordinates from URL. Please check the URL and try again.", "error")
        return redirect(url_for('index'))

    # Create GPX file
    gpx_data = create_gpx(coordinates, route_name, travel_mode)

    # Save to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.gpx') as temp_file:
        temp_file.write(gpx_data.encode())
        temp_file_path = temp_file.name

    # Generate a more descriptive filename
    safe_route_name = "".join(c if c.isalnum() or c in "-_. " else "_" for c in route_name)
    download_filename = f"{safe_route_name}_{datetime.now().strftime('%Y%m%d')}.gpx"

    # Provide some debug info in development mode
    if app.debug:
        print(f"Extracted {len(coordinates)} waypoints")
        print(f"Travel mode: {travel_mode}")
        print(f"First few coordinates: {coordinates[:3]}")

    return send_file(
        temp_file_path,
        as_attachment=True,
        download_name=download_filename,
        mimetype="application/gpx+xml"
    )


@app.route('/about')
def about():
    """Information page about the app"""
    return render_template('about.html')


@app.route('/api-key-instructions')
def api_key_instructions():
    """Page with instructions on setting up a Google API key"""
    return render_template('api_key_instructions.html')


@app.route('/api-key-status')
def api_key_status():
    """Check if API key is configured and return status"""
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    if api_key:
        return jsonify({"status": "active", "message": "Google API key is configured"})
    else:
        return jsonify(
            {"status": "missing", "message": "No Google API key found. Routes will use straight lines between points."})


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    # Make sure required directories exist
    os.makedirs('templates', exist_ok=True)

    # Create API key instructions template if it doesn't exist
    template_path = os.path.join('templates', 'api_key_instructions.html')
    if not os.path.exists(template_path):
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Google API Key Setup | Google Maps to GPX Converter</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: #fff;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        h1 {
            text-align: center;
            color: #2c3e50;
            margin-bottom: 30px;
        }
        h2 {
            color: #3498db;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
            margin-top: 30px;
        }
        h3 {
            color: #2c3e50;
            margin-top: 25px;
        }
        code {
            background-color: #f8f9fa;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: monospace;
        }
        pre {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
        }
        .note {
            background-color: #e8f4fc;
            padding: 15px;
            border-radius: 4px;
            border-left: 4px solid #3498db;
            margin: 15px 0;
        }
        .note strong {
            color: #2980b9;
        }
        .home-link {
            display: block;
            text-align: center;
            margin-top: 30px;
        }
        .home-link a {
            color: #3498db;
            text-decoration: none;
            font-weight: bold;
        }
        .home-link a:hover {
            text-decoration: underline;
        }
        footer {
            text-align: center;
            margin-top: 40px;
            font-size: 14px;
            color: #7f8c8d;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Setting Up a Google API Key</h1>

        <div class="note">
            <strong>Free Usage:</strong> Google provides a $200 monthly credit for Maps API usage, which is enough for approximately 40,000 route conversions per month at no cost.
        </div>

        <p>
            To make the Google Maps to GPX converter follow roads properly (rather than just connecting waypoints 
            with straight lines), you need to set up a Google API key with access to the Directions API.
        </p>

        <h2>Step 1: Create a Google Cloud Platform Account</h2>
        <ol>
            <li>Go to <a href="https://console.cloud.google.com/" target="_blank">Google Cloud Platform</a></li>
            <li>Sign in with your Google account or create a new one</li>
            <li>Create a new project (or use an existing one)</li>
        </ol>

        <h2>Step 2: Enable the Directions API</h2>
        <ol>
            <li>In the Google Cloud Console, navigate to "APIs & Services" > "Library"</li>
            <li>Search for "Directions API"</li>
            <li>Click on "Directions API" in the results</li>
            <li>Click "Enable"</li>
        </ol>

        <h2>Step 3: Create an API Key</h2>
        <ol>
            <li>Navigate to "APIs & Services" > "Credentials"</li>
            <li>Click "Create Credentials" > "API key"</li>
            <li>A new API key will be created. Copy this key.</li>
        </ol>

        <h2>Step 4: (Optional but Recommended) Restrict Your API Key</h2>
        <p>For security, it's good practice to restrict your API key:</p>
        <ol>
            <li>In the Credentials page, find your API key and click "Edit"</li>
            <li>Under "Application restrictions", you can select "IP addresses" and add your IP address</li>
            <li>Under "API restrictions", select "Restrict key" and choose "Directions API" from the dropdown</li>
            <li>Click "Save"</li>
        </ol>

        <h2>Step 5: Add the API Key to the Application</h2>
        <p>There are two ways to add your API key to the application:</p>

        <h3>Option 1: Environment Variable</h3>
        <p>Set the <code>GOOGLE_API_KEY</code> environment variable before running the application:</p>

        <p><strong>Windows:</strong></p>
        <pre>set GOOGLE_API_KEY=your_api_key_here</pre>

        <p><strong>macOS/Linux:</strong></p>
        <pre>export GOOGLE_API_KEY=your_api_key_here</pre>

        <h3>Option 2: Create a .env File</h3>
        <ol>
            <li>Create a file named <code>.env</code> in the application directory</li>
            <li>Add the following line to the file:
            <pre>GOOGLE_API_KEY=your_api_key_here</pre>
            </li>
            <li>Save the file</li>
        </ol>

        <h2>Step 6: Restart the Application</h2>
        <p>After setting up your API key, restart the application to apply the changes.</p>

        <h2>Free Usage Limits</h2>
        <ul>
            <li>Google provides a <strong>$200 monthly credit</strong> for using Google Maps Platform APIs</li>
            <li>The Directions API costs $5 per 1,000 requests</li>
            <li>With the free credit, you can make approximately <strong>40,000 route conversions per month at no cost</strong></li>
            <li>For most personal use, this should be more than enough</li>
        </ul>

        <div class="note">
            <strong>Note:</strong> If you exceed the free limits, you will need to enable billing in your Google Cloud account. Make sure to monitor your usage if you're concerned about costs.
        </div>

        <div class="home-link">
            <a href="/">&larr; Back to Converter</a>
        </div>
    </div>

    <footer>
        <p>Google Maps to GPX Converter | Made for outdoor enthusiasts</p>
    </footer>
</body>
</html>
            ''')

    app.run(debug=True)