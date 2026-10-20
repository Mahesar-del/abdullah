"""
Trading Platform - Django Settings
Phase 1: Foundation & Architecture
"""

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', '')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
if not SECRET_KEY and not DEBUG:
    raise RuntimeError('SECRET_KEY must be set when DEBUG is disabled.')
if not SECRET_KEY:
    SECRET_KEY = 'django-insecure-local-development-only-change-me'
ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv(
        'CSRF_TRUSTED_ORIGINS', 'https://tradesense-pro-live.onrender.com'
    ).split(',') if origin.strip()
]

# ─── Installed Apps ───────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third Party
    'rest_framework',
    'corsheaders',
    'channels',

    # Our Apps
    'signals',
    'market_data',
    'accounts',
    'dashboard',
    'engines',
]

# ─── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'trading_platform.urls'
WSGI_APPLICATION = 'trading_platform.wsgi.application'
ASGI_APPLICATION = 'trading_platform.asgi.application'

# ─── Templates ────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ─── Database ─────────────────────────────────────────────────────────────────
# Use PostgreSQL in production, SQLite for local dev/testing
USE_POSTGRES = os.getenv('USE_POSTGRES', 'False') == 'True'

if USE_POSTGRES:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'trading_platform'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    # SQLite for local development (no setup required)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                'timeout': 30,
            }
        }
    }

# ─── Cache & Channels (Redis) ─────────────────────────────────────────────────
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
    }
}

# Use In-Memory channel layer for dev (no Redis needed), Redis in production
USE_REDIS = os.getenv('USE_REDIS', 'False') == 'True'

if USE_REDIS:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [REDIS_URL]},
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# ─── Celery (Background Tasks) ────────────────────────────────────────────────
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Karachi'

# ─── REST Framework ───────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

# ─── CORS ─────────────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 31_536_000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG

# ─── Static & Media Files ─────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─── Telegram Notifications (Bot API) ─────────────────────────────────────────
# Real credentials only. If unset, deliveries are recorded as SKIPPED (never DELIVERED).
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID', '')
# api.telegram.org is blocked in some countries; set a mirror/reverse-proxy base or an HTTPS proxy.
TELEGRAM_API_BASE  = os.getenv('TELEGRAM_API_BASE', 'https://api.telegram.org')
TELEGRAM_PROXY     = os.getenv('TELEGRAM_PROXY', '')

# ─── WhatsApp Notifications (official Business APIs only) ─────────────────────
# WHATSAPP_PROVIDER: 'meta' (WhatsApp Business Cloud API) or 'twilio' (Twilio WhatsApp Business API)
WHATSAPP_PROVIDER = os.getenv('WHATSAPP_PROVIDER', 'meta').lower()
# Meta WhatsApp Cloud API
META_WA_TOKEN           = os.getenv('META_WA_TOKEN', '')
META_WA_PHONE_NUMBER_ID = os.getenv('META_WA_PHONE_NUMBER_ID', '')
META_WA_TO              = os.getenv('META_WA_TO', '')            # recipient in E.164 without '+'
META_WA_API_VERSION     = os.getenv('META_WA_API_VERSION', 'v20.0')
META_WA_VERIFY_TOKEN    = os.getenv('META_WA_VERIFY_TOKEN', '')  # webhook verification handshake
META_WA_APP_SECRET      = os.getenv('META_WA_APP_SECRET', '')    # X-Hub-Signature-256 validation
# Business-initiated messages outside the 24h window MUST use an approved template.
META_WA_TEMPLATE_NAME   = os.getenv('META_WA_TEMPLATE_NAME', '')
META_WA_TEMPLATE_LANG   = os.getenv('META_WA_TEMPLATE_LANG', 'en')
# Twilio WhatsApp
TWILIO_ACCOUNT_SID   = os.getenv('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN    = os.getenv('TWILIO_AUTH_TOKEN', '')
TWILIO_FROM_WHATSAPP = os.getenv('TWILIO_FROM_WHATSAPP', '')
TWILIO_TO_WHATSAPP   = os.getenv('TWILIO_TO_WHATSAPP', '')
PUBLIC_BASE_URL      = os.getenv('PUBLIC_BASE_URL', '')   # used for Twilio status-callback signature checks

NOTIFY_MAX_RETRIES   = int(os.getenv('NOTIFY_MAX_RETRIES', '3'))

# ─── Trading Mode & Production Gate ───────────────────────────────────────────
# PAPER is always allowed. LIVE is only honoured when the validation gate has passed
# (see engines/validation.py) -- otherwise the system silently stays in PAPER.
TRADING_MODE = os.getenv('TRADING_MODE', 'PAPER').upper()

# ─── Risk Engine Configuration (explicit config; defaults per spec) ───────────
RISK_CONFIG = {
    'ACCOUNT_BALANCE':         float(os.getenv('ACCOUNT_BALANCE', '10000')),
    'RISK_PER_TRADE_PCT':      float(os.getenv('RISK_PER_TRADE_PCT', '1.0')),   # strict 1% unless changed here
    'MAX_DAILY_LOSS_PCT':      float(os.getenv('MAX_DAILY_LOSS_PCT', '3.0')),
    'MAX_DRAWDOWN_PCT':        float(os.getenv('MAX_DRAWDOWN_PCT', '10.0')),
    'MAX_OPEN_TRADES':         int(os.getenv('MAX_OPEN_TRADES', '5')),
    'MIN_RR':                  float(os.getenv('MIN_RR', '1.5')),
    'MAX_SPREAD_PCT_OF_SL':    float(os.getenv('MAX_SPREAD_PCT_OF_SL', '10.0')),  # spec: <=10% of SL distance
    'MIN_CONFIDENCE':          float(os.getenv('MIN_CONFIDENCE', '50.0')),
    'MIN_ATR_PCT':             float(os.getenv('MIN_ATR_PCT', '0.02')),           # low-volatility floor (ATR % of price)
    'MIN_DATA_QUALITY':        float(os.getenv('MIN_DATA_QUALITY', '60.0')),
    'BLACKOUT_BEFORE_MIN':     int(os.getenv('BLACKOUT_BEFORE_MIN', '30')),
    'BLACKOUT_AFTER_MIN':      int(os.getenv('BLACKOUT_AFTER_MIN', '30')),
    'CB_BLACKOUT_MIN':         int(os.getenv('CB_BLACKOUT_MIN', '60')),
    'MAX_ENGINE_CONFLICT':     int(os.getenv('MAX_ENGINE_CONFLICT', '1')),       # opposing engines tolerated
}

# ─── Validation Gate (criteria must pass before LIVE is allowed) ──────────────
VALIDATION_CRITERIA = {
    'MIN_TRADES_TOTAL':        int(os.getenv('VAL_MIN_TRADES', '30')),
    'MIN_PROFIT_FACTOR':       float(os.getenv('VAL_MIN_PF', '1.2')),
    'MIN_EXPECTANCY_R':        float(os.getenv('VAL_MIN_EXPECTANCY_R', '0.10')),
    'MAX_DRAWDOWN_PCT':        float(os.getenv('VAL_MAX_DD', '20.0')),
    'MIN_OOS_PROFIT_FACTOR':   float(os.getenv('VAL_MIN_OOS_PF', '1.0')),
    'MIN_PROFITABLE_ASSET_FRACTION': float(os.getenv('VAL_MIN_ASSET_FRACTION', '0.6')),
    'MIN_ASSETS':              int(os.getenv('VAL_MIN_ASSETS', '3')),
    'MIN_PAPER_TRADES':        int(os.getenv('VAL_MIN_PAPER_TRADES', '20')),
    'MIN_PAPER_EXPECTANCY_R':  float(os.getenv('VAL_MIN_PAPER_EXPECTANCY_R', '0.0')),
    'MAX_VALIDATION_AGE_DAYS': int(os.getenv('VAL_MAX_AGE_DAYS', '30')),
}

# ─── Data freshness thresholds (days unless noted) ───────────────────────────
DATA_FRESHNESS = {
    'CENTRAL_BANK_RATE_MAX_AGE_DAYS':   int(os.getenv('CB_RATE_MAX_AGE_DAYS', '10')),   # rate feed must have synced this recently
    'CENTRAL_BANK_STALE_AFTER_DAYS':    int(os.getenv('CB_STALE_AFTER_DAYS', '75')),   # policy meetings are ~6-8 weeks apart
    'CALENDAR_MAX_AGE_HOURS':           int(os.getenv('CAL_MAX_AGE_HOURS', '24')),
    'NEWS_MAX_AGE_HOURS':               int(os.getenv('NEWS_MAX_AGE_HOURS', '6')),
    'COT_MAX_AGE_DAYS':                 int(os.getenv('COT_MAX_AGE_DAYS', '12')),      # weekly report, Tuesday data / Friday release
    'DERIVATIVES_MAX_AGE_MINUTES':      int(os.getenv('DERIV_MAX_AGE_MIN', '120')),
    'SPREAD_MAX_AGE_MINUTES':           int(os.getenv('SPREAD_MAX_AGE_MIN', '10')),
}

# ─── Optional Data Providers ──────────────────────────────────────────────────
OANDA_API_KEY    = os.getenv('OANDA_API_KEY', '')       # live FX/metal bid-ask (optional)
OANDA_ACCOUNT_ID = os.getenv('OANDA_ACCOUNT_ID', '')
OANDA_ENV        = os.getenv('OANDA_ENV', 'practice')

# Directory for versioned ML model artifacts
ML_MODEL_DIR = BASE_DIR / 'ml_models'
ML_RETRAIN_INTERVAL_DAYS = int(os.getenv('ML_RETRAIN_INTERVAL_DAYS', '14'))

# ─── Auth & Passwords ─────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── API Keys ─────────────────────────────────────────────────────────────────
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', '')
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY', '')      # optional: economic-calendar ACTUAL values
NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')
FRED_API_KEY = os.getenv('FRED_API_KEY', '')            # optional: faster/more reliable yields

# ─── Logging ──────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'std': {'format': '%(asctime)s %(levelname)s %(name)s: %(message)s'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'std'}},
    'loggers': {
        'engines':  {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO')},
        'signals':  {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO')},
    },
}
