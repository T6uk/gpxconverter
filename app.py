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

# Password settings
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'gpxconverter2025')  # Default password if not set in .env

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
        return False, "URL ei saa olla tühi"

    # Basic Google Maps URL validation
    valid_domains = [
        'google.com/maps',
        'maps.google.com',
        'www.google.com/maps',
        'goo.gl/maps',
        'maps.app.goo.gl'
    ]

    if not any(domain in url.lower() for domain in valid_domains):
        return False, "See ei tundu olevat Google Maps URL"

    # Advanced pattern matching for directions URLs
    if '/dir/' not in url and '@' not in url:
        return False, "URL ei sisalda suunajuhiseid ega kaardi koordinaate"

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
    route_name = request.form.get('route_name', '').strip() or "Google Maps Marsruut"
    password = request.form.get('password', '').strip()

    # Validate password - simple direct comparison with APP_PASSWORD
    if password != APP_PASSWORD:
        app.logger.warning(f"Invalid password attempt from {request.remote_addr}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "Vale parool"}), 401
        flash("Vale parool. Palun proovige uuesti.", "error")
        return redirect(url_for('index'))

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
        flash(f"Viga URL töötlemisel: {str(e)}", "error")
        return redirect(url_for('index'))

    if not coordinates or len(coordinates) < 2:
        flash("Ei õnnestunud URL-ist marsruudi koordinaate leida. Palun kontrollige URL-i ja proovige uuesti.", "error")
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
        flash(f"Viga GPX genereerimisel: {str(e)}", "error")
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
        return jsonify({"status": "active", "message": "Google API võti on konfigureeritud"})
    else:
        return jsonify(
            {"status": "missing", "message": "Google API võtit ei leitud. Marsruudid kasutavad sirgjoonelisi ühendusi punktide vahel."})


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
        "error": "Piirang ületatud",
        "message": "Liiga palju päringuid. Palun proovige hiljem uuesti."
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
<html lang="et">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Google API Võtme Seadistamine | Google Maps GPX Konverter</title>
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
        <h1>Google API Võtme Seadistamine</h1>

        <div class="note">
            <strong>Tasuta Kasutamine:</strong> Google pakub igakuiselt $200 krediiti Maps API kasutamiseks, millest piisab umbes 40 000 marsruudi konverteerimiseks kuus ilma lisakuluta.
        </div>

        <p>
            Selleks, et Google Maps GPX konverter järgiks korrektselt teid (mitte ei ühendaks teekonnapunkte sirgjoonega), 
            peate seadistama Google API võtme juurdepääsuga suunajuhiste (Directions) API-le.
        </p>

        <h2>Samm 1: Looge Google Cloud Platform konto</h2>
        <ol>
            <li>Minge <a href="https://console.cloud.google.com/" target="_blank">Google Cloud Platform</a> lehele</li>
            <li>Logige sisse oma Google kontoga või looge uus</li>
            <li>Looge uus projekt (või kasutage olemasolevat)</li>
        </ol>

        <h2>Samm 2: Aktiveerige Directions API</h2>
        <ol>
            <li>Google Cloud Console'is navigeerige "APIs & Services" > "Library"</li>
            <li>Otsige "Directions API"</li>
            <li>Klikkige tulemuste seas "Directions API" peale</li>
            <li>Klikkige "Enable"</li>
        </ol>

        <h2>Samm 3: Looge API Võti</h2>
        <ol>
            <li>Navigeerige "APIs & Services" > "Credentials"</li>
            <li>Klikkige "Create Credentials" > "API key"</li>
            <li>Luuakse uus API võti. Kopeerige see võti.</li>
        </ol>

        <h2>Samm 4: (Valikuline, kuid Soovitatav) Piirake Oma API Võtit</h2>
        <p>Turvalisuse huvides on hea tava piirata oma API võtit:</p>
        <ol>
            <li>Credentials lehel leidke oma API võti ja klikkige "Edit"</li>
            <li>"Application restrictions" all valige "IP addresses" ja lisage oma IP-aadress</li>
            <li>"API restrictions" all valige "Restrict key" ja valige rippmenüüst "Directions API"</li>
            <li>Klikkige "Save"</li>
        </ol>

        <h2>Samm 5: Lisage API Võti Rakendusele</h2>
        <p>API võtme lisamiseks rakendusse on kaks võimalust:</p>

        <h3>Variant 1: Keskkonnamuutuja</h3>
        <p>Määrake <code>GOOGLE_MAPS_API_KEY</code> keskkonnamuutuja enne rakenduse käivitamist:</p>

        <p><strong>Windows:</strong></p>
        <pre>set GOOGLE_MAPS_API_KEY=your_api_key_here</pre>

        <p><strong>macOS/Linux:</strong></p>
        <pre>export GOOGLE_MAPS_API_KEY=your_api_key_here</pre>

        <h3>Variant 2: .env Faili Loomine</h3>
        <ol>
            <li>Looge fail nimega <code>.env</code> rakenduse kataloogis</li>
            <li>Lisage järgmine rida faili:
            <pre>GOOGLE_MAPS_API_KEY=your_api_key_here</pre>
            </li>
            <li>Salvestage fail</li>
        </ol>

        <h2>Samm 6: Taaskäivitage Rakendus</h2>
        <p>Pärast API võtme seadistamist taaskäivitage rakendus muudatuste rakendamiseks.</p>

        <h2>Tasuta Kasutamise Piirangud</h2>
        <ul>
            <li>Google pakub <strong>$200 igakuist krediiti</strong> Google Maps Platform API-de kasutamiseks</li>
            <li>Directions API maksab $5 iga 1000 päringu kohta</li>
            <li>Tasuta krediidiga saate teha ligikaudu <strong>40 000 marsruudi konverteerimist kuus ilma kuluta</strong></li>
            <li>Enamiku isikliku kasutuse jaoks peaks sellest piisama</li>
        </ul>

        <div class="note">
            <strong>Märkus:</strong> Kui ületate tasuta piirangud, peate oma Google Cloud kontol aktiveerima arvelduse. Kui olete kulude pärast mures, jälgige oma kasutust.
        </div>

        <div class="home-link">
            <a href="/">&larr; Tagasi Konverterisse</a>
        </div>
    </div>

    <footer>
        <p>Google Maps GPX Konverter | Loodud matkahuvilistele</p>
    </footer>
</body>
</html>
            ''')

    app.run(debug=True)