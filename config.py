import os
import secrets
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration"""
    # Generate a random secret key if not set
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(24))

    # API key
    GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')

    # General settings
    DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'
    TESTING = False
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1MB max upload size

    # Path configurations
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    LOG_FOLDER = os.path.join(BASE_DIR, 'logs')

    # Rate limiting
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"
    RATELIMIT_STORAGE_URL = "memory://"

    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = os.environ.get('CSRF_SECRET_KEY', secrets.token_hex(24))

    # Ensure directories exist
    @classmethod
    def init_directories(cls):
        os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(cls.LOG_FOLDER, exist_ok=True)


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

    # More verbose logging
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

    # Stricter security settings
    LOG_LEVEL = 'INFO'
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Production rate limiting (use Redis in production)
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')

    # You can also specify a different log folder for production
    LOG_FOLDER = os.environ.get('LOG_FOLDER', Config.LOG_FOLDER)


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True

    # Use a memory database for testing
    LOG_LEVEL = 'DEBUG'
    WTF_CSRF_ENABLED = False  # Disable CSRF in testing


# Dictionary to easily select configuration
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


# Get config from environment or use default
def get_config():
    env = os.environ.get('FLASK_ENV', 'default')
    return config.get(env, config['default'])