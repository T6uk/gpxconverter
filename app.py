import os
import atexit
import secrets
import tempfile
from flask import Flask, render_template, request, send_file, jsonify, flash, redirect, url_for, g
from datetime import datetime
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from logging.handlers import RotatingFileHandler

# Load environment variables from .env file
load_dotenv()

# Create Flask application
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(24))

# Track temp files to ensure they're deleted
temp_files = []

# Configure CSRF protection
csrf = CSRFProtect(app)

# Setup rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


# Setup logging
def setup_logging(app):
    """Configure application logging"""
    # Ensure logs directory exists
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Configure file handler
    file_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10485760,  # 10 MB
        backupCount=10
    )

    # Set log level based on environment
    log_level = logging.DEBUG if app.debug else logging.INFO

    file_handler.setLevel(log_level)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    # Add handlers to app logger
    app.logger.addHandler(file_handler)
    app.logger.setLevel(log_level)

    # Log app startup
    app.logger.info('Application startup')


setup_logging(app)


# Security headers
@app.after_request
def add_security_headers(response):
    """Add security headers to response"""
    # Content Security Policy
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )

    # Prevent browsers from MIME-sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'

    # Enables browser's XSS filtering
    response.headers['X-XSS-Protection'] = '1; mode=block'

    # Controls how much information is included in referrer
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # Prevents page from being framed (clickjacking protection)
    response.headers['X-Frame-Options'] = 'DENY'

    # Strict Transport Security (only in production)
    if not app.debug and not app.testing:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    return response


# Import route parser and GPX generator after app creation
from route_parser import extract_coordinates_from_google_maps_url, extract_travel_mode
from gpx_generator import create_gpx


# Validation functions
def validate_google_maps_url(url):
    """
    Validate that the URL is from Google Maps and follows expected patterns

    Parameters:
    url (str): Google Maps URL to validate

    Returns:
    tuple: (is_valid, error_message)
    """
    # Check if URL is not empty
    if not url or not url.strip():
        return False, "URL cannot be empty"

    # Basic Google Maps URL validation
    valid_domains = [
        'google.com/maps',
        'maps.google.com',
        'www.google.com/maps',
        'goo.gl/maps',
        'maps.app.goo.gl'
    ]

    if not any(domain in url.lower() for domain in valid_domains):
        return False, "This doesn't appear to be a Google Maps URL"

    # Advanced pattern matching for directions URLs
    if '/dir/' not in url and '@' not in url:
        return False, "URL doesn't contain directions or map coordinates"

    return True, ""


def is_api_key_configured():
    """Check if API key is configured without exposing it"""
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    return bool(api_key and api_key.strip())


def create_temp_gpx_file(gpx_data):
    """
    Create a secure temporary file for the GPX data

    Parameters:
    gpx_data (str): GPX XML content

    Returns:
    str: Path to temporary file
    """
    # Create a secure temporary file with restricted permissions
    fd, temp_path = tempfile.mkstemp(suffix='.gpx', prefix='gpx_', dir=None, text=False)

    try:
        # Write data to the file
        with os.fdopen(fd, 'wb') as temp_file:
            temp_file.write(gpx_data.encode())

        # Track for cleanup
        temp_files.append(temp_path)
        return temp_path

    except Exception as e:
        # Clean up in case of error
        os.unlink(temp_path)
        raise e


def cleanup_temp_files():
    """Delete any remaining temporary files"""
    for file_path in temp_files[:]:
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                temp_files.remove(file_path)
        except Exception as e:
            app.logger.error(f"Error cleaning up temporary file {file_path}: {e}")


# Register cleanup function to run on application exit
atexit.register(cleanup_temp_files)


# Routes
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/convert', methods=['POST'])
@limiter.limit("3 per minute")  # Rate limit to prevent abuse
def convert():
    google_maps_url = request.form.get('google_maps_url', '').strip()
    route_name = request.form.get('route_name', '').strip() or "Google Maps Route"

    # Validate the URL
    is_valid, error_message = validate_google_maps_url(google_maps_url)
    if not is_valid:
        flash(error_message, "error")
        return redirect(url_for('index'))

    # Sanitize the route name (prevent directory traversal, etc.)
    route_name = "".join(c if c.isalnum() or c in "-_. " else "_" for c in route_name)

    # Detect travel mode
    travel_mode = extract_travel_mode(google_maps_url)

    # Extract coordinates from the URL
    try:
        coordinates = extract_coordinates_from_google_maps_url(google_maps_url)
    except Exception as e:
        app.logger.error(f"Error extracting coordinates: {str(e)}")
        flash(f"Error processing URL: {str(e)}", "error")
        return redirect(url_for('index'))

    if not coordinates or len(coordinates) < 2:
        flash("Could not extract route coordinates from URL. Please check the URL and try again.", "error")
        return redirect(url_for('index'))

    try:
        # Create GPX file
        gpx_data = create_gpx(coordinates, route_name, travel_mode)

        # Save to secure temporary file
        temp_file_path = create_temp_gpx_file(gpx_data)

        # Generate a secure filename with the route name
        safe_route_name = "".join(c if c.isalnum() or c in "-_. " else "_" for c in route_name)
        download_filename = f"{safe_route_name}_{datetime.now().strftime('%Y%m%d')}.gpx"

        # Provide some debug info in development mode only
        if app.debug:
            app.logger.debug(f"Extracted {len(coordinates)} waypoints")
            app.logger.debug(f"Travel mode: {travel_mode}")

        response = send_file(
            temp_file_path,
            as_attachment=True,
            download_name=download_filename,
            mimetype="application/gpx+xml"
        )

        return response

    except Exception as e:
        app.logger.error(f"Error generating GPX: {str(e)}")
        flash(f"Error generating GPX: {str(e)}", "error")
        return redirect(url_for('index'))


@app.route('/about')
def about():
    """Information page about the app"""
    return render_template('about.html')


@app.route('/api-key-instructions')
def api_key_instructions():
    """Page with instructions on setting up a Google API key"""
    return render_template('api_key_instructions.html')


@app.route('/api-key-status')
@limiter.limit("10 per minute")
def api_key_status():
    """Check if API key is configured and return status"""
    if is_api_key_configured():
        return jsonify({"status": "active", "message": "Google API key is configured"})
    else:
        return jsonify(
            {"status": "missing", "message": "No Google API key found. Routes will use straight lines between points."})


# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    app.logger.info(f"404 error: {request.path}")
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.error(f"500 error: {str(e)}")
    return render_template('500.html'), 500


@app.errorhandler(429)
def ratelimit_handler(e):
    app.logger.warning(f"Rate limit exceeded: {request.remote_addr} - {request.path}")
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "Too many requests. Please try again later."
    }), 429


if __name__ == '__main__':
    # Make sure required directories exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('logs', exist_ok=True)

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
        <p>Set the <code>GOOGLE_MAPS_API_KEY</code> environment variable before running the application:</p>

        <p><strong>Windows:</strong></p>
        <pre>set GOOGLE_MAPS_API_KEY=your_api_key_here</pre>

        <p><strong>macOS/Linux:</strong></p>
        <pre>export GOOGLE_MAPS_API_KEY=your_api_key_here</pre>

        <h3>Option 2: Create a .env File</h3>
        <ol>
            <li>Create a file named <code>.env</code> in the application directory</li>
            <li>Add the following line to the file:
            <pre>GOOGLE_MAPS_API_KEY=your_api_key_here</pre>
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