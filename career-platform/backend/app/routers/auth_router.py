from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.auth import verify_password, create_access_token
from app import schemas

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory brute-force guard. Fine for a single-process, single-user deployment —
# resets on restart, which is an acceptable trade-off at this scale (not worth a
# Redis dependency for a tool with exactly one legitimate user).
_failed_attempts: dict[str, list[datetime]] = {}
MAX_ATTEMPTS = 5
WINDOW_MINUTES = 15


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=schemas.Token)
def login(payload: schemas.LoginRequest, request: Request):
    key = _client_key(request)
    now = datetime.now(timezone.utc)
    recent = [t for t in _failed_attempts.get(key, []) if now - t < timedelta(minutes=WINDOW_MINUTES)]
    _failed_attempts[key] = recent

    if len(recent) >= MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail=f"Too many failed login attempts. Try again in {WINDOW_MINUTES} minutes.")

    if payload.email != settings.auth_email or not settings.auth_password_hash:
        _failed_attempts[key].append(now)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, settings.auth_password_hash):
        _failed_attempts[key].append(now)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _failed_attempts.pop(key, None)  # clear on success
    token = create_access_token(payload.email)
    return {"access_token": token, "token_type": "bearer"}
