import os
import sys
import time
import functools
import logging
import traceback
from typing import Any, Callable

# Sensitive keys to sanitize in logs
SENSITIVE_KEYS = {
    "password", "password_hash", "client_secret", "access_token",
    "refresh_token", "secret", "authorization", "token", "google_client_secret"
}

def sanitize_data(data: Any) -> Any:
    """Recursively mask sensitive keys in dictionaries or lists for safe logging."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if any(sens in k.lower() for sens in SENSITIVE_KEYS):
                sanitized[k] = "****** [REDACTED]"
            elif isinstance(v, (dict, list)):
                sanitized[k] = sanitize_data(v)
            else:
                sanitized[k] = v
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data

def setup_logger(name: str = "event_tracker", log_level: str = None) -> logging.Logger:
    """
    Configures and returns a heavy debug logger with rich formatting.
    """
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()

    numeric_level = getattr(logging, log_level, logging.DEBUG)

    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)

    # Avoid duplicate handlers if already configured
    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-7s] [%(name)s:%(filename)s:%(lineno)d] -> %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Standard console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

# Global application logger
app_logger = setup_logger()

def log_execution(func: Callable) -> Callable:
    """
    Decorator for heavy debug logging at the start, end, and error of functions/routes.
    Logs execution time, sanitized arguments, return values, and full stack traces on error.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = f"{func.__module__}.{func.__qualname__}"
        clean_kwargs = sanitize_data(kwargs)
        # We sanitize args representation lightly
        clean_args = [sanitize_data(a) if isinstance(a, (dict, list)) else repr(a) for a in args]

        app_logger.debug(f"[ENTER] -> Function: {func_name} | Args: {clean_args} | Kwargs: {clean_kwargs}")
        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            duration = (time.time() - start_time) * 1000
            # Truncate result in logs if it's huge (e.g. large binary or big dict)
            res_str = str(result)
            if len(res_str) > 500:
                res_str = res_str[:500] + "... [TRUNCATED]"
            app_logger.debug(f"[EXIT]  <- Function: {func_name} | Duration: {duration:.2f}ms | Result: {res_str}")
            return result
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            app_logger.error(
                f"[ERROR] !! Function: {func_name} FAILED after {duration:.2f}ms | Error: {type(e).__name__}: {str(e)}\n"
                f"Stack Trace:\n{traceback.format_exc()}"
            )
            raise e

    return wrapper

def log_db_transaction(action: str, model_name: str, entity_id: Any = None, details: Any = None):
    """Explicit helper for logging database transactions."""
    sanitized_details = sanitize_data(details) if details else {}
    app_logger.debug(
        f"[DATABASE TRANSACTION] Action: {action.upper()} | Model: {model_name} | ID: {entity_id} | Details: {sanitized_details}"
    )

def log_external_api(service_name: str, endpoint: str, method: str = "GET", payload: Any = None, response: Any = None, status_code: int = 200):
    """Explicit helper for logging external API calls (Google Drive, Google Auth, etc.)."""
    app_logger.debug(
        f"[EXTERNAL API] Service: {service_name} | Method: {method} | Endpoint: {endpoint} | "
        f"Status: {status_code} | Payload: {sanitize_data(payload)} | Response: {sanitize_data(response)}"
    )
