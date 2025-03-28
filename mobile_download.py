# mobile_download.py - This handles special download routes for mobile devices

import os
import secrets
import tempfile
import time
from flask import send_file, abort, request, render_template, jsonify, url_for, make_response
from werkzeug.utils import secure_filename


def register_mobile_download_routes(app):
    """
    Register mobile-friendly download routes with the Flask app

    Parameters:
    app (Flask): The Flask application
    """

    @app.route('/direct-download/<path:temp_id>')
    def direct_download(temp_id):
        """
        Provide a direct download method for mobile devices
        This bypasses AJAX for devices that struggle with the standard download method

        Parameters:
        temp_id (str): The temporary ID for the generated GPX file

        Returns:
        Response: File download or error response
        """
        # Security validation - ensure the temp_id is alphanumeric + underscore only
        if not temp_id or not temp_id.replace('_', '').isalnum():
            app.logger.warning(f"Invalid temp_id format attempted: {temp_id}")
            return abort(404)

        # Get file path from the session storage
        file_path = app.config.get('TEMP_FILES', {}).get(temp_id)

        if not file_path or not os.path.exists(file_path):
            app.logger.warning(f"Attempted to download non-existent file with ID: {temp_id}")
            return abort(404)

        # Extract original name from stored metadata or generate one
        file_metadata = app.config.get('TEMP_FILE_METADATA', {}).get(temp_id, {})
        original_name = file_metadata.get('name', f"route_{secrets.token_hex(4)}.gpx")

        # Clean up the filename for security
        filename = secure_filename(original_name)
        if not filename.endswith('.gpx'):
            filename += '.gpx'

        try:
            # Create a response with the file
            response = make_response(send_file(
                file_path,
                as_attachment=True,
                download_name=filename,
                mimetype="application/gpx+xml"
            ))

            # Add headers that help with mobile downloads
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.headers['Content-Type'] = 'application/gpx+xml'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

            # This can help with iOS Safari
            response.headers['X-Content-Type-Options'] = 'nosniff'

            return response
        except Exception as e:
            app.logger.error(f"Error sending file: {str(e)}")
            return abort(500)

    @app.route('/ios-download/<path:temp_id>')
    def ios_download(temp_id):
        """
        Special download handler for iOS Safari
        iOS Safari requires special handling for file downloads

        Parameters:
        temp_id (str): The temporary ID for the generated GPX file

        Returns:
        Response: GPX file inline for iOS to handle
        """
        # Security validation
        if not temp_id or not temp_id.replace('_', '').isalnum():
            app.logger.warning(f"Invalid temp_id format attempted: {temp_id}")
            return abort(404)

        # Get file path from the session storage
        file_path = app.config.get('TEMP_FILES', {}).get(temp_id)

        if not file_path or not os.path.exists(file_path):
            app.logger.warning(f"Attempted to download non-existent file with ID: {temp_id}")
            return abort(404)

        # Extract original name from stored metadata or generate one
        file_metadata = app.config.get('TEMP_FILE_METADATA', {}).get(temp_id, {})
        original_name = file_metadata.get('name', f"route_{secrets.token_hex(4)}.gpx")

        # Clean up the filename for security
        filename = secure_filename(original_name)
        if not filename.endswith('.gpx'):
            filename += '.gpx'

        try:
            # For iOS, we send the file with inline disposition first
            with open(file_path, 'r') as f:
                gpx_content = f.read()

            response = make_response(gpx_content)
            response.headers['Content-Type'] = 'application/gpx+xml'
            response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
            response.headers['X-Filename'] = filename
            return response
        except Exception as e:
            app.logger.error(f"Error serving iOS file: {str(e)}")
            return abort(500)

    @app.route('/mobile-download-helper')
    def mobile_download_helper():
        """
        Render a simple page that helps mobile devices download files
        This is a fallback for devices where the automatic download doesn't work

        Returns:
        Response: HTML page with download link
        """
        temp_id = request.args.get('id')
        filename = request.args.get('name', 'route.gpx')

        if not temp_id:
            return abort(400)

        # Detect iOS
        user_agent = request.headers.get('User-Agent', '').lower()
        is_ios = 'iphone' in user_agent or 'ipad' in user_agent or 'ipod' in user_agent
        is_android = 'android' in user_agent

        # Construct appropriate download URL
        if is_ios:
            download_url = url_for('ios_download', temp_id=temp_id)
            direct_url = url_for('direct_download', temp_id=temp_id)
        else:
            download_url = url_for('direct_download', temp_id=temp_id)
            direct_url = download_url

        return render_template(
            'mobile_download.html',
            download_url=download_url,
            direct_url=direct_url,
            filename=filename,
            is_ios=is_ios,
            is_android=is_android
        )

    # Register helper functions to store and manage temporary files
    def store_temp_file(file_content, original_name=None):
        """
        Store a temporary file and return an ID for retrieving it

        Parameters:
        file_content (str): Content to store in the file
        original_name (str, optional): Original filename

        Returns:
        tuple: (temp_id, file_path)
        """
        # Initialize storage dictionaries if they don't exist
        if not hasattr(app.config, 'TEMP_FILES'):
            app.config['TEMP_FILES'] = {}

        if not hasattr(app.config, 'TEMP_FILE_METADATA'):
            app.config['TEMP_FILE_METADATA'] = {}

        # Create a temporary file with binary write mode
        fd, temp_path = tempfile.mkstemp(suffix='.gpx', prefix='gpx_', text=False)

        try:
            # Write content to file
            with os.fdopen(fd, 'wb') as temp_file:
                temp_file.write(file_content.encode('utf-8') if isinstance(file_content, str) else file_content)

            # Generate an ID for this file
            temp_id = f"gpx_{secrets.token_hex(8)}"

            # Store the path mapped to the ID
            app.config['TEMP_FILES'][temp_id] = temp_path

            # Store metadata
            app.config['TEMP_FILE_METADATA'][temp_id] = {
                'name': original_name or f"route_{secrets.token_hex(4)}.gpx",
                'created': time.time()
            }

            return temp_id, temp_path

        except Exception as e:
            # Clean up in case of error
            try:
                os.unlink(temp_path)
            except:
                pass

            app.logger.error(f"Error creating temporary file: {str(e)}")
            raise

    # Add the helper function to the app context
    app.store_temp_file = store_temp_file

    # Add a cleanup function for temporary files
    def cleanup_old_temp_files():
        """
        Clean up temporary files that are older than a threshold (e.g., 1 hour)
        This should be called periodically or on application startup
        """
        import time

        # Current time
        now = time.time()

        # Maximum age (1 hour = 3600 seconds)
        max_age = 3600

        # Get the temporary files dict
        temp_files = app.config.get('TEMP_FILES', {})
        temp_file_metadata = app.config.get('TEMP_FILE_METADATA', {})

        # Find old files to remove
        to_remove = []

        for temp_id, file_path in temp_files.items():
            # Skip if file doesn't exist
            if not os.path.exists(file_path):
                to_remove.append(temp_id)
                continue

            # Get creation time from metadata or fall back to file timestamp
            metadata = temp_file_metadata.get(temp_id, {})
            created_time = metadata.get('created') or os.path.getmtime(file_path)

            # Check if file is older than threshold
            if now - created_time > max_age:
                try:
                    os.unlink(file_path)
                except:
                    pass
                to_remove.append(temp_id)

        # Remove entries from dictionaries
        for temp_id in to_remove:
            temp_files.pop(temp_id, None)
            temp_file_metadata.pop(temp_id, None)

        app.logger.info(f"Cleaned up {len(to_remove)} temporary files")

    # Add cleanup function to app context
    app.cleanup_temp_files = cleanup_old_temp_files

    # Run cleanup on startup
    cleanup_old_temp_files()

    # Return the helper functions for use elsewhere
    return {
        'store_temp_file': store_temp_file,
        'cleanup_temp_files': cleanup_old_temp_files
    }