from fastapi import HTTPException

from core.http_client import requests_lib


def glpi_http_error(exc: Exception, accion: str = "conectar con GLPI") -> None:
    if requests_lib and isinstance(exc, requests_lib.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else "?"
        try:
            body = exc.response.json()
            if isinstance(body, list):
                detail = " | ".join(str(d) for d in body)
            else:
                detail = str(body)
        except Exception:
            detail = exc.response.text[:300] if exc.response is not None else str(exc)

        hints = {
            400: "Token inválido o sesión expirada. Verifica el User-Token en GLPI.",
            401: "Sin autorización. Verifica App-Token y User-Token.",
            403: "Acceso denegado. El usuario no tiene permisos suficientes en GLPI.",
            404: "URL de GLPI incorrecta o endpoint no encontrado.",
        }
        hint = hints.get(int(status) if str(status).isdigit() else 0, "")
        msg = f"Error al {accion} (HTTP {status}). {hint} Detalle: {detail}"
        raise HTTPException(status_code=502, detail=msg)
    raise HTTPException(status_code=502, detail=f"Error al {accion}: {exc}")
