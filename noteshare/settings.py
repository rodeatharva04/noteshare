from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- SECURITY ---
# If on Render -> DEBUG is False. If on Laptop -> DEBUG is True.
# We default to True for local development if the env var isn't found.
DEBUG = os.environ.get('DEBUG') == 'True'

# Force Debug=True for your local testing right now (You can change this later)
# DEBUG = False # Uncomment this only when deploying to Production

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-local-dev-key')

# Allow all hosts (Simplifies local vs production setup)
ALLOWED_HOSTS = ['*']

# Trusted Origins (Important for Railway/Render + AJAX CSRF)
CSRF_TRUSTED_ORIGINS = [
    'https://*.onrender.com',
    'https://*.railway.app',
    'https://*.up.railway.app',
    'https://127.0.0.1',
    'https://localhost',
]

INSTALLED_APPS = [
    'core',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # <--- ENABLED FOR STATIC FILES
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', # <--- CRITICAL FOR AJAX POST
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'noteshare.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'noteshare.wsgi.application'

# --- DATABASE (SQLite) ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata' 
USE_I18N = True
USE_TZ = True

# --- STATIC FILES (WhiteNoise) ---
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles' 
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = 'home'
LOGIN_URL = 'login'
LOGOUT_REDIRECT_URL = 'login'

# --- EMAIL CONFIGURATION (Brevo API) ---
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
DEFAULT_FROM_EMAIL = "rodeatharva05@gmail.com"

# --- AI CONFIGURATION (Gemini) ---
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', None)
if not GOOGLE_API_KEY:
    print("❌ WARNING: GOOGLE_API_KEY is None! AI will not work.")
else:
    print(f"✅ Google API Key loaded (Length: {len(GOOGLE_API_KEY)})")

# --- CRITICAL FIX FOR LOCALHOST ---
# Only require HTTPS/SSL when in Production (DEBUG=False).
# If we force these on Localhost (DEBUG=True), cookies fail and you can't log in.
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
else:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# Allows iframe embedding for the PDF viewer
X_FRAME_OPTIONS = 'SAMEORIGIN'
