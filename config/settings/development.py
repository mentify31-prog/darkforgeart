"""
DarkForge Art — Development Settings
"""

from .base import *  # noqa: F401, F403

DEBUG = True

# Use console email in dev when no Resend key is set (base.py already handles this)

# Allow all hosts in local development
ALLOWED_HOSTS = ["*"]

# More verbose logging in development
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "darkforge": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
