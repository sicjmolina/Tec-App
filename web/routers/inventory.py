import csv
import io
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import Response

from core.glpi_errors import glpi_http_error
from core.http_client import requests_lib as _requests
from core.jsonutil import load_json, save_json
from core.service_container import resolve_glpi
from core.state_meta import record_last_glpi_sync
from schemas import InventoryMovimientoIn
from settings import INVENTORY_PATH, get_merged_config

router = APIRouter(prefix="/api/inventario", tags=["inventory"])


def _load_inventory():
    data = load_json(INVENTORY_PATH, {"movimientos": [], "activos": {}})
    if not isinstance(data, dict):
        return {"movimientos": [], "activos": {}}
    if "movimientos" not in data or not isinstance(data["movimientos"], list):
        data["movimientos"] = []
    if "activos" not in data or not isinstance(data["activos"], dict):
        data["activos"] = {}
    return data


def _save_inventory(data: dict):
    save_json(INVENTORY_PATH, data)


def _tipo_equipo(comp: dict, type_map: dict | None) -> str:
    if not type_map:
        return ""
    raw = comp.get("computertypes_id")
    if raw is None or str(raw).strip() == "":
        raw = comp.get("4")
    if raw is None or str(raw).strip() == "":
        return ""
    s = str(raw).strip()
    if not s.isdigit():
        return s
    return type_map.get(s, "")


def _fmt_asset(comp: dict, local_asset: dict | None = None, type_map: dict | None = None):
    local_asset = local_asset or {}
    asset_id = str(comp.get("id") or comp.get("2") or local_asset.get("asset_id") or "")
    nombre = str(comp.get("name") or comp.get("1") or local_asset.get("nombre") or "Sin nombre")
    usuario_glpi = str(comp.get("users_id") or comp.get("70") or "").strip()
    estado_glpi = str(comp.get("states_id") or comp.get("31") or "").strip()
    serial = str(comp.get("serial") or comp.get("10") or comp.get("5") or "").strip()
    ultima = str(comp.get("date_mod") or comp.get("19") or local_asset.get("ultima_actualizacion") or "")
    return {
        "asset_id": asset_id,
        "nombre": nombre,
        "tipo": _tipo_equipo(comp, type_map),
        "serial": serial,
        "usuario_actual": local_asset.get("usuario_actual") or usuario_glpi,
        "estado_actual": local_asset.get("estado_actual") or estado_glpi,
        "baja": bool(local_asset.get("baja", False)),
        "ultima_actualizacion": local_asset.get("ultima_actualizacion") or ultima,
    }


def _list_inventario_activos(modo_prueba: bool) -> list[dict]:
    inv = _load_inventory()
    activos_local = inv.get("activos", {})

    if modo_prueba:
        type_map = {"1": "Portátil", "2": "Sobremesa", "3": "Todo en uno"}
        base = [
            {"id": "9001", "name": "PC-PRUEBA-01", "serial": "SN-PRUEBA-01", "computertypes_id": "1"},
            {"id": "9002", "name": "PC-PRUEBA-02", "serial": "SN-PRUEBA-02", "computertypes_id": "2"},
            {"id": "9003", "name": "PC-PRUEBA-03", "serial": "SN-PRUEBA-03", "computertypes_id": "3"},
        ]
        activos = [_fmt_asset(c, activos_local.get(str(c["id"]), {}), type_map) for c in base]
    else:
        cfg = get_merged_config()
        if not cfg.get("glpi_url"):
            raise HTTPException(400, "Configura la URL de GLPI primero.")
        if _requests is None:
            raise HTTPException(500, "Instala requests: pip install requests")

        g = resolve_glpi(cfg)
        try:
            g.login()
            type_map = g.computer_type_id_to_name_map()
            raw = g._get_all(
                "Computer",
                {
                    "is_deleted": "0",
                    "is_template": "0",
                    "forcedisplay[0]": "1",
                    "forcedisplay[1]": "2",
                    "forcedisplay[2]": "4",
                    "forcedisplay[3]": "10",
                    "forcedisplay[4]": "70",
                    "forcedisplay[5]": "31",
                    "forcedisplay[6]": "19",
                },
            )
        except Exception as ex:
            glpi_http_error(ex, "cargar activos de inventario")
        finally:
            g.logout()

        record_last_glpi_sync()

        activos = []
        for c in raw:
            asset_id = str(c.get("id") or c.get("2") or "")
            activos.append(_fmt_asset(c, activos_local.get(asset_id, {}), type_map))

    activos.sort(key=lambda a: (a.get("baja", False), a.get("nombre", "")))
    return activos


@router.get("/activos")
def get_inventario_activos(modo_prueba: bool = True):
    activos = _list_inventario_activos(modo_prueba)
    return {"items": activos, "total": len(activos)}


# (cabecera CSV, clave en el dict del activo)
_ACTIVOS_CSV_FIELDS = [
    ("asset_id", "asset_id"),
    ("nombre", "nombre"),
    ("Tipo", "tipo"),
    ("serial", "serial"),
    ("usuario_actual", "usuario_actual"),
    ("estado_actual", "estado_actual"),
    ("baja", "baja"),
    ("ultima_actualizacion", "ultima_actualizacion"),
]


@router.get("/activos.csv")
def get_inventario_activos_csv(modo_prueba: bool = True):
    activos = _list_inventario_activos(modo_prueba)

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([h for h, _ in _ACTIVOS_CSV_FIELDS])
    for a in activos:
        row = []
        for _, k in _ACTIVOS_CSV_FIELDS:
            v = a.get(k, "")
            if k == "baja":
                row.append("sí" if v else "no")
            else:
                row.append(v)
        writer.writerow(row)

    body = "\ufeff" + out.getvalue()
    sufijo = "_prueba" if modo_prueba else ""
    fn = f"inventario_equipos{sufijo}_{date.today().isoformat()}.csv"

    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/usuarios")
def get_inventario_usuarios(modo_prueba: bool = True):
    if modo_prueba:
        items = [
            {"id": "60", "nombre": "j.perez"},
            {"id": "72", "nombre": "m.garcia"},
            {"id": "81", "nombre": "a.lopez"},
        ]
        return {"items": items, "total": len(items)}

    cfg = get_merged_config()
    if not cfg.get("glpi_url"):
        raise HTTPException(400, "Configura la URL de GLPI primero.")
    if _requests is None:
        raise HTTPException(500, "Instala requests: pip install requests")

    g = resolve_glpi(cfg)
    try:
        g.login()
        raw = g._get_all(
            "User",
            {
                "is_deleted": "0",
                "is_active": "1",
                "forcedisplay[0]": "1",
                "forcedisplay[1]": "2",
                "forcedisplay[2]": "34",
            },
        )
    except Exception as ex:
        glpi_http_error(ex, "cargar usuarios de GLPI")
    finally:
        g.logout()

    record_last_glpi_sync()

    items = []
    for u in raw:
        uid = str(u.get("2") or u.get("id") or "").strip()
        nombre = str(u.get("1") or u.get("name") or "").strip()
        if not uid or not nombre:
            continue
        display = str(u.get("34") or "").strip()
        items.append({"id": uid, "nombre": display or nombre})

    uniq = {}
    for u in items:
        uniq[u["id"]] = u
    sorted_items = sorted(uniq.values(), key=lambda x: x["nombre"].lower())
    return {"items": sorted_items, "total": len(sorted_items)}


@router.get("/historial")
def get_inventario_historial(asset_id: Optional[str] = None):
    inv = _load_inventory()
    movs = inv.get("movimientos", [])
    if asset_id:
        movs = [m for m in movs if str(m.get("asset_id")) == str(asset_id)]
    movs.sort(key=lambda m: (m.get("fecha", ""), m.get("created_at", "")), reverse=True)
    return {"items": movs, "total": len(movs)}


_CSV_COLUMNS = [
    "fecha",
    "created_at",
    "asset_id",
    "asset_nombre",
    "tipo",
    "usuario_anterior",
    "usuario_nuevo",
    "estado_nuevo",
    "motivo",
    "responsable",
    "ticket_id",
]


@router.get("/historial.csv")
def get_inventario_historial_csv(asset_id: Optional[str] = None):
    inv = _load_inventory()
    movs = inv.get("movimientos", [])
    if asset_id:
        movs = [m for m in movs if str(m.get("asset_id")) == str(asset_id)]
    movs.sort(key=lambda m: (m.get("fecha", ""), m.get("created_at", "")), reverse=True)

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(_CSV_COLUMNS)
    for m in movs:
        writer.writerow([m.get(c, "") for c in _CSV_COLUMNS])

    body = "\ufeff" + out.getvalue()
    fn = f"historial_inventario_{date.today().isoformat()}.csv"
    if asset_id:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(asset_id))[:40]
        fn = f"historial_inventario_{safe}_{date.today().isoformat()}.csv"

    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.post("/movimiento")
def post_inventario_movimiento(data: InventoryMovimientoIn):
    tipos_validos = {"asignacion", "reasignacion", "baja", "desactivacion", "reactivacion", "observacion"}
    if data.tipo not in tipos_validos:
        raise HTTPException(400, f"Tipo inválido. Usa: {', '.join(sorted(tipos_validos))}")
    if not data.asset_id.strip():
        raise HTTPException(400, "asset_id es obligatorio.")
    if not data.asset_nombre.strip():
        raise HTTPException(400, "asset_nombre es obligatorio.")
    if data.tipo in {"asignacion", "reasignacion"} and not data.usuario_nuevo.strip():
        raise HTTPException(400, "usuario_nuevo es obligatorio para asignación/reasignación.")
    if data.tipo == "baja" and not data.motivo.strip():
        raise HTTPException(400, "Debes indicar un motivo para la baja.")

    inv = _load_inventory()
    asset_id = str(data.asset_id).strip()
    fecha = data.fecha.strip() or date.today().isoformat()
    created_at = datetime.now().isoformat()
    glpi_sync = {"attempted": False, "ok": False, "detail": ""}

    if not data.modo_prueba:
        cfg = get_merged_config()
        if not cfg.get("glpi_url"):
            raise HTTPException(400, "Configura la URL de GLPI primero.")
        if _requests is None:
            raise HTTPException(500, "Instala requests: pip install requests")

        usuario_nuevo = data.usuario_nuevo.strip()
        usuario_id = None
        if data.tipo in {"asignacion", "reasignacion"} and usuario_nuevo:
            try:
                usuario_id = int(usuario_nuevo)
            except Exception:
                raise HTTPException(400, "El usuario seleccionado no es válido (ID numérico).")

        estado_objetivo = data.estado_nuevo.strip()
        if not estado_objetivo and data.tipo == "baja":
            estado_objetivo = "Baja"
        elif not estado_objetivo and data.tipo == "desactivacion":
            estado_objetivo = "Inactivo"
        elif not estado_objetivo and data.tipo == "reactivacion":
            estado_objetivo = "Activo"

        g = resolve_glpi(cfg)
        try:
            g.login()
            glpi_sync["attempted"] = True
            state_id = None
            if estado_objetivo:
                state_id = g.find_state_id_by_name(estado_objetivo)
                if not state_id:
                    raise HTTPException(
                        400,
                        f"No existe un estado '{estado_objetivo}' en GLPI. "
                        "Crea ese estado o selecciona uno existente.",
                    )
            g.update_computer_fields(
                computer_id=asset_id,
                users_id=usuario_id,
                states_id=state_id,
            )

            line_parts = [
                fecha,
                data.tipo.upper(),
                (data.usuario_anterior.strip() or "—") + " -> " + (data.usuario_nuevo.strip() or "—"),
            ]
            if estado_objetivo:
                line_parts.append(f"Estado: {estado_objetivo}")
            if data.responsable.strip():
                line_parts.append(f"Responsable: {data.responsable.strip()}")
            if data.ticket_id.strip():
                line_parts.append(f"Ticket: {data.ticket_id.strip()}")
            if data.motivo.strip():
                line_parts.append(f"Motivo: {data.motivo.strip()}")
            g.append_computer_comment(asset_id, " | ".join(line_parts))

            glpi_sync["ok"] = True
            glpi_sync["detail"] = "Activo y comentario actualizados en GLPI."
        except HTTPException:
            raise
        except Exception as ex:
            glpi_http_error(ex, "actualizar el activo en GLPI")
        finally:
            g.logout()

    mov = {
        "asset_id": asset_id,
        "asset_nombre": data.asset_nombre.strip(),
        "tipo": data.tipo,
        "usuario_anterior": data.usuario_anterior.strip(),
        "usuario_nuevo": data.usuario_nuevo.strip(),
        "estado_nuevo": data.estado_nuevo.strip(),
        "motivo": data.motivo.strip(),
        "responsable": data.responsable.strip(),
        "ticket_id": data.ticket_id.strip(),
        "fecha": fecha,
        "created_at": created_at,
    }
    inv["movimientos"].append(mov)

    activos = inv["activos"]
    actual = activos.get(
        asset_id,
        {
            "asset_id": asset_id,
            "nombre": data.asset_nombre.strip(),
            "usuario_actual": "",
            "estado_actual": "",
            "baja": False,
            "ultima_actualizacion": created_at,
        },
    )
    actual["nombre"] = data.asset_nombre.strip()
    actual["ultima_actualizacion"] = created_at

    if data.tipo in {"asignacion", "reasignacion"}:
        actual["usuario_actual"] = data.usuario_nuevo.strip()
    if data.tipo == "baja":
        actual["baja"] = True
        actual["estado_actual"] = data.estado_nuevo.strip() or "Baja"
    elif data.tipo == "desactivacion":
        actual["baja"] = False
        actual["estado_actual"] = data.estado_nuevo.strip() or "Inactivo"
    elif data.tipo == "reactivacion":
        actual["baja"] = False
        actual["estado_actual"] = data.estado_nuevo.strip() or "Activo"
    elif data.estado_nuevo.strip():
        actual["estado_actual"] = data.estado_nuevo.strip()

    activos[asset_id] = actual
    _save_inventory(inv)

    if data.modo_prueba:
        glpi_sync = {"attempted": False, "ok": False, "detail": "Modo prueba activo."}

    return {"ok": True, "movimiento": mov, "activo": actual, "glpi_sync": glpi_sync}
