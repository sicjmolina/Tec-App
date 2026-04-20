from typing import Optional

from fastapi import APIRouter
from fastapi.responses import Response

from adapters.json_repositories import JsonInventoryRepository
from application.inventory_use_cases import InventoryUseCases
from core.service_container import resolve_glpi
from schemas import InventoryMovimientoIn

router = APIRouter(prefix="/api/inventario", tags=["inventory"])
inventory_uc = InventoryUseCases(JsonInventoryRepository())


@router.get("/activos")
def get_inventario_activos(modo_prueba: bool = True):
    activos = inventory_uc.list_activos(modo_prueba, resolve_glpi)
    return {"items": activos, "total": len(activos)}


@router.get("/activos.csv")
def get_inventario_activos_csv(modo_prueba: bool = True):
    activos = inventory_uc.list_activos(modo_prueba, resolve_glpi)
    payload, fn = inventory_uc.activos_csv(activos)

    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/usuarios")
def get_inventario_usuarios(modo_prueba: bool = True):
    return inventory_uc.usuarios(modo_prueba, resolve_glpi)


@router.get("/historial")
def get_inventario_historial(asset_id: Optional[str] = None):
    return inventory_uc.historial(asset_id)


@router.get("/historial.csv")
def get_inventario_historial_csv(asset_id: Optional[str] = None):
    payload, fn = inventory_uc.historial_csv(asset_id)

    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.post("/movimiento")
def post_inventario_movimiento(data: InventoryMovimientoIn):
    return inventory_uc.registrar_movimiento(data, resolve_glpi)
