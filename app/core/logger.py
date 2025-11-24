from functools import lru_cache
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger as loguru_logger
import sys
import time
from pathlib import Path


import sentry_sdk
from sentry_sdk.integrations.loguru import LoguruIntegration
from app.core.config import settings


LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGGER_NAME = "playwright-webrun"


def replace_name_filter(record):
    record["name"] = LOGGER_NAME
    return True


def setup_logger():
    loguru_logger.remove()

    loguru_logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
        backtrace=True,
        diagnose=True,
        enqueue=True,
        filter=replace_name_filter,
    )

    if settings.debug:
        loguru_logger.add(
            "logs/app.log",
            serialize=True,
            rotation="10 MB",  # or "00:00" for daily rotation
            retention="20 days",
            compression="zip",
            level="DEBUG",
            enqueue=True,
        )
    else:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[
                LoguruIntegration(
                    level=settings.log_level,  # Capture logs from INFO level and above
                    event_level="ERROR",  # Send events to Sentry for logs at ERROR level and above
                )
            ],
            enable_logs=True,
        )

    return loguru_logger


@lru_cache(maxsize=1)
def get_logger():
    return setup_logger()


logger = get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        logger.info(f"→ {request.method} {request.url.path}")

        try:
            response = await call_next(request)
        except Exception as e:
            logger.exception(f"Unhandled error: {e}")
            raise
        finally:
            process_time = time.time() - start_time

            logger.info(
                f"← {request.method} {request.url.path} | "
                f"Status: {getattr(response, 'status_code', 'N/A')} | "
                f"{process_time:.4f}s"
            )

        return response
