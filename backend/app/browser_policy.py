"""Public frontend routing. No credentials or trading configuration belongs here."""
from .config import get_settings
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse

FRONTEND_URL = "https://protoss.trade/app"
API_URL = "https://api.protoss.trade"

def install_browser_policy(app):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://protoss.trade", "https://www.protoss.trade", "https://app.protoss.trade", "http://localhost:4173", "http://127.0.0.1:4173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
        max_age=600,
    )

    @app.middleware("http")
    async def legacy_frontend(request, call_next):
        # Only the old UI entrypoint moves. Existing native/API clients keep their paths.
        # A redirect without a fragment preserves the browser's original hash route.
        enabled = get_settings().redirect_legacy_frontend
        if enabled and request.url.hostname == "app.protoss.trade" and request.method in ("GET", "HEAD") and request.url.path in ("/", "/index.html", "/app", "/app/"):
            query = ("?" + request.url.query) if request.url.query else ""
            return RedirectResponse(FRONTEND_URL + "/" + query, status_code=307, headers={"Cache-Control": "no-store"})
        return await call_next(request)
