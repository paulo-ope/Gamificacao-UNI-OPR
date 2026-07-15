from __future__ import annotations

import logging
from contextlib import contextmanager
from time import perf_counter

from app.core.config import get_settings

logger = logging.getLogger("app.performance")


def performance_debug_enabled() -> bool:
    settings = get_settings()
    return settings.debug_performance or settings.app_env.lower() in {"development", "dev", "local"}


@contextmanager
def performance_step(endpoint: str, step: str):
    if not performance_debug_enabled():
        yield
        return

    started_at = perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (perf_counter() - started_at) * 1000
        logger.info("performance endpoint=%s step=%s elapsed_ms=%.2f", endpoint, step, elapsed_ms)
