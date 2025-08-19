# config/logging_setup.py
import logging
import logging.config
import os

class RedactSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        for key in ("token", "api_key", "authorization", "password"):
            if key in msg.lower():
                record.msg = msg[:200] + " [REDACTED]"
                record.args = ()
                break
        return True

def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = os.getenv("LOG_FILE", "")

    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "level": level,
            "formatter": "standard",
            "filters": ["redact_secrets"],
        }
    }

    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": level,
            "filename": log_file,
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "encoding": "utf-8",
            "formatter": "standard",
            "filters": ["redact_secrets"],
        }

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"redact_secrets": {"()": RedactSecrets}},
        "formatters": {"standard": {"format": fmt, "datefmt": datefmt}},
        "handlers": handlers,
        "loggers": {
            "": {"level": level, "handlers": list(handlers.keys())},
            "urllib3": {"level": "WARNING"},
            "httpx": {"level": "WARNING"},
        },
    }

    logging.config.dictConfig(config)
    logging.captureWarnings(True)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

__all__ = ["setup_logging", "get_logger"]
