from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    """Limite de requisições por IP numa janela deslizante, em memória (processo único, como o
    resto dos limites das rotas públicas - ver `api/routes/auth.py`/`access_requests.py`). Zera num
    restart; limites que precisam sobreviver a isso (ex.: por e-mail alvo) ficam no banco."""

    def __init__(self, *, window_minutes: int, max_attempts: int, message: str) -> None:
        self._window = timedelta(minutes=window_minutes)
        self._max_attempts = max_attempts
        self._message = message
        self._attempts: dict[str, list[datetime]] = {}

    def check(self, request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        now = datetime.now(timezone.utc)
        recent = [attempt for attempt in self._attempts.get(client_host, []) if attempt >= now - self._window]
        if len(recent) >= self._max_attempts:
            self._attempts[client_host] = recent
            raise HTTPException(status_code=429, detail=self._message)
        recent.append(now)
        self._attempts[client_host] = recent

    def reset(self) -> None:
        self._attempts.clear()
