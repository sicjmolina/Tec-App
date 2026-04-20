import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.router_registry import include_api_routers
from core.http_client import requests_lib as _requests
from settings import LOG_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("mant")


def create_app() -> FastAPI:
    app = FastAPI(title="Mantenimientos Preventivos — Sicolsa", version="2.0.0")

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        msg = str(exc)
        if _requests and isinstance(exc, _requests.exceptions.HTTPError):
            status = exc.response.status_code if exc.response is not None else "?"
            try:
                detail = exc.response.json()
                if isinstance(detail, list):
                    detail = " | ".join(str(d) for d in detail)
            except Exception:
                detail = exc.response.text[:200] if exc.response is not None else ""
            msg = f"GLPI respondió {status}: {detail}"
        elif _requests and isinstance(exc, _requests.exceptions.ConnectionError):
            msg = "No se pudo conectar al servidor. Verifica la URL y la red."
        elif _requests and isinstance(exc, _requests.exceptions.Timeout):
            msg = "Tiempo de espera agotado al conectar con el servidor."

        log.error(f"Error no capturado en {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": msg})

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    include_api_routers(app)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(static_dir / "index.html"))

    return app
