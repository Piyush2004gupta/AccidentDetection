import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(log_level: str = "INFO") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    
    # Add file logging for production if we have a logs directory
    log_dir = Path("logs")
    try:
        log_dir.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handlers.append(file_handler)
    except Exception:
        # Fallback if we can't create logs dir (e.g. read-only filesystem)
        pass

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=handlers,
        force=True,
    )
