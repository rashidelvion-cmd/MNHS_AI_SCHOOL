from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]


# ==========================
# Installed Apps
# ==========================

INSTALLED_APPS = [
    # Django Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Project Apps
    'accounts',
    'dashboard',
    'students',
    'teachers',
    'attendance',
    'academics',
    'enrollment',
    'grades',
    'classrecord',
    'reports',
]


# ==========================
# Middleware
# ==========================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'config.urls'


# ==========================
# Templates
# ==========================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'academics.context_processors.events_badge',
            ],
        },
    },
]


WSGI_APPLICATION = 'config.wsgi.application'


# ==========================
# PostgreSQL Database
# ==========================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ["DB_NAME"],
        'USER': os.environ["DB_USER"],
        'PASSWORD': os.environ["DB_PASSWORD"],
        'HOST': os.environ["DB_HOST"],
        'PORT': os.environ["DB_PORT"],
    }
}


# ==========================
# Password Validators
# ==========================

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ==========================
# Internationalization
# ==========================

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Karachi'

USE_I18N = True

USE_TZ = True


# ==========================
# Static Files
# ==========================

STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"



# ==========================
# Media Files
# ==========================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# ==========================
# Default Primary Key
# ==========================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'


# ==========================
# School identity (used on generated reports e.g. SF9)
# ==========================

SCHOOL_NAME = os.environ.get('SCHOOL_NAME', 'Mayorga National High School')
SCHOOL_ADDRESS = os.environ.get('SCHOOL_ADDRESS', 'Mayorga, Leyte')

# DepEd form header identity (SF1/SF2/SF9/SF10). Set the real values in .env.
SCHOOL_ID = os.environ.get('SCHOOL_ID', '')
SCHOOL_DISTRICT = os.environ.get('SCHOOL_DISTRICT', '')
SCHOOL_DIVISION = os.environ.get('SCHOOL_DIVISION', 'Leyte')
SCHOOL_REGION = os.environ.get('SCHOOL_REGION', 'VIII')


# ==========================
# Messages (map to Bootstrap alert classes)
# ==========================

from django.contrib.messages import constants as message_constants

MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
}
