import calendar as cal_module
import logging
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter
from fastapi import HTTPException

try:
    from msal import ConfidentialClientApplication
except ImportError:
    ConfidentialClientApplication = None

from core.checklist_util import load_checklist
from core.constants import MESES_ES
from core.dates import asignar_fechas_habiles, fmt_fecha_larga, mes_anterior_key, mes_key
from core.glpi_errors import glpi_http_error
from core.http_client import requests_lib as _requests
from core.jsonutil import load_json, save_json
from core.service_container import resolve_glpi, resolve_outlook
from core.state_meta import get_last_glpi_sync_at, merge_meta_into_state, record_last_glpi_sync
from schemas import CompletarIn, ConfirmarIn
from services.email_templates import build_email_html
from services.mantenimiento_report import build_mantenimiento_mes_excel
from settings import CONFIG_PATH, STATE_PATH, get_merged_config

log = logging.getLogger("mant")

router = APIRouter(prefix="/api", tags=["maintenance"])


def _procesar_tickets_ant(glpi_list: list, state_list: list) -> dict:
    todos = {}
    for t in state_list:
        todos[t["nombre"]] = {
            "nombre": t["nombre"],
            "fecha": t.get("fecha", ""),
            "ticket_id": t.get("ticket_id"),
            "status_glpi": None,
        }
    for t in glpi_list:
        nombre_raw = str(t.get("1", "") or t.get("name", ""))
        nombre = nombre_raw.replace("Mantenimiento Preventivo: ", "").strip()
        status = t.get("12") or t.get("status")
        s = int(status) if status else 1
        if nombre in todos:
            todos[nombre]["status_glpi"] = s
        else:
            todos[nombre] = {
                "nombre": nombre,
                "fecha": "",
                "ticket_id": None,
                "status_glpi": s,
            }
    completados = [v for v in todos.values() if v.get("status_glpi") in [5, 6]]
    pendientes = [v for v in todos.values() if v not in completados]
    return {
        "items": list(todos.values()),
        "completados": len(completados),
        "pendientes": len(pendientes),
    }


def _mes_actual_done() -> bool:
    state = load_json(STATE_PATH, {})
    return bool(state.get(mes_key(), {}).get("completado"))


def _completados_desde_state(year: int, month: int) -> dict[int, dict]:
    """ticket_id → {fecha_cierre, nombre} según marcas de 'Completar' en la app."""
    key = mes_key(date(year, month, 1))
    ultimo = cal_module.monthrange(year, month)[1]
    desde_s = f"{year}-{month:02d}-01"
    hasta_s = f"{year}-{month:02d}-{ultimo:02d}"
    out: dict[int, dict] = {}
    for eq in load_json(STATE_PATH, {}).get(key, {}).get("equipos", []):
        if not eq.get("completado"):
            continue
        fc = (eq.get("fecha_completado") or "")[:10]
        if not fc or not (desde_s <= fc <= hasta_s):
            continue
        tid = eq.get("ticket_id")
        if tid is None:
            continue
        try:
            tid_i = int(tid)
        except (TypeError, ValueError):
            continue
        out[tid_i] = {"fecha_cierre": fc, "nombre": eq.get("nombre", "—")}
    return out


def _merge_realizados_con_state(realizados: list, comp_state: dict[int, dict]) -> None:
    seen: set[int] = set()
    for r in realizados:
        tid = r.get("ticket_id")
        tidi = None
        if tid is not None:
            try:
                tidi = int(tid)
                seen.add(tidi)
            except (TypeError, ValueError):
                pass
        if not r.get("fecha_cierre") and tidi is not None and tidi in comp_state:
            r["fecha_cierre"] = comp_state[tidi]["fecha_cierre"]
            r["nota"] = "Fecha de cierre tomada del registro en la aplicación."
    for tidi, info in comp_state.items():
        if tidi not in seen:
            realizados.append({
                "ticket_id": tidi,
                "titulo": f"Mantenimiento Preventivo: {info['nombre']}",
                "nombre": info["nombre"],
                "fecha_apertura": "—",
                "fecha_limite": "—",
                "fecha_cierre": info["fecha_cierre"],
                "status": 6,
                "estado_txt": "Cerrado",
                "nota": "Completado desde la aplicación (GLPI sin fecha en el listado).",
            })
            seen.add(tidi)
    realizados.sort(key=lambda x: (x.get("fecha_cierre") or "", str(x.get("nombre") or "").lower()))


def _datos_prueba():
    demo_users = [
        "gmartinez@sicolsa.demo",
        "r.lopez@sicolsa.demo",
        "a.fernandez@sicolsa.demo",
        "c.ruiz@sicolsa.demo",
        "m.santos@sicolsa.demo",
        "vecino.reserva@sicolsa.demo",
        "otro.reserva@sicolsa.demo",
        "demo.user.8@sicolsa.demo",
        "demo.user.9@sicolsa.demo",
        "demo.user.10@sicolsa.demo",
    ]
    base = [
        {
            "id": 9001 + i,
            "nombre": f"PC-PRUEBA-{i + 1:02d}",
            "ultima_fecha": f"2024-{i + 1:02d}-15",
            "usuario_asignado": demo_users[i],
        }
        for i in range(10)
    ]
    candidatos = asignar_fechas_habiles(base[:5])
    reserva = base[5:]
    tickets_ant_raw = [
        {"1": "Mantenimiento Preventivo: ESPECTOMETRO", "12": 6},
        {"1": "Mantenimiento Preventivo: SADMINISTRACION", "12": 1},
        {"1": "Mantenimiento Preventivo: SALMACEN", "12": 5},
    ]
    tickets_ant = _procesar_tickets_ant(tickets_ant_raw, [])
    return {
        "total": 60,
        "cuota": 5,
        "ya_tienen": 0,
        "candidatos": candidatos,
        "reserva": reserva,
        "tickets_mes": [],
        "tickets_ant": tickets_ant,
        "mes_actual_done": _mes_actual_done(),
        "last_glpi_sync_at": get_last_glpi_sync_at(),
    }


@router.get("/cargar")
def cargar_equipos(modo_prueba: bool = True):
    if modo_prueba:
        return _datos_prueba()

    cfg = get_merged_config()
    if not cfg.get("glpi_url"):
        raise HTTPException(400, "Configura la URL de GLPI primero.")
    if _requests is None:
        raise HTTPException(500, "Instala requests: pip install requests")

    g = resolve_glpi(cfg)
    try:
        log.info("Iniciando sesión en GLPI")
        try:
            g.login()
        except Exception as ex:
            glpi_http_error(ex, "iniciar sesión en GLPI")

        computers = g.get_computers()
        if not computers:
            raise HTTPException(502, "GLPI no devolvió equipos. Verifica el App-Token y User-Token.")

        log.info(f"Computadores obtenidos: {len(computers)}")
        candidatos, total, cuota, ya_tienen, tickets_mes, reserva = g.select_candidates(computers)
        candidatos = asignar_fechas_habiles(candidatos)

        tickets_ant = []
        try:
            tickets_ant = g.get_tickets_mes_anterior()
        except Exception as ex:
            log.warning(f"No se pudo obtener mes anterior: {ex}")

        state = load_json(STATE_PATH, {})
        key_ant = mes_anterior_key()
        state_ant = state.get(key_ant, {}).get("equipos", [])
    finally:
        g.logout()

    record_last_glpi_sync()

    return {
        "total": total,
        "cuota": cuota,
        "ya_tienen": ya_tienen,
        "candidatos": candidatos,
        "reserva": reserva,
        "tickets_mes": tickets_mes,
        "tickets_ant": _procesar_tickets_ant(tickets_ant, state_ant),
        "mes_actual_done": _mes_actual_done(),
        "last_glpi_sync_at": get_last_glpi_sync_at(),
    }


@router.post("/confirmar")
def confirmar(data: ConfirmarIn):
    incluidos = [e for e in data.equipos if e.incluido]
    cfg = get_merged_config()
    creados = []
    errores = []

    if data.modo_prueba:
        if data.cuota_mes > 0 and len(incluidos) != data.cuota_mes:
            raise HTTPException(
                400,
                f"[Prueba] Debes incluir exactamente {data.cuota_mes} equipo(s). "
                f"Ahora hay {len(incluidos)} marcado(s).",
            )
        if data.cuota_mes <= 0 and not incluidos:
            raise HTTPException(400, "Selecciona al menos un equipo.")
        for i, eq in enumerate(incluidos):
            time.sleep(0.1)
            d = date.fromisoformat(eq.fecha_limite)
            creados.append({
                "nombre": eq.nombre,
                "fecha": fmt_fecha_larga(d),
                "ticket_id": 90000 + i,
                "evento_id": f"fake-event-{i}",
                "correo_ok": False,
            })
        log.info(f"[PRUEBA] {len(creados)} tickets simulados")
    else:
        if _requests is None:
            raise HTTPException(500, "Instala requests")

        glpi = resolve_glpi(cfg)
        outlook = resolve_outlook(cfg)
        log.info("Conectando GLPI + Outlook para confirmar")
        glpi.login()
        outlook.authenticate()

        try:
            if data.cuota_mes > 0:
                _, tickets_mes_actuales = glpi.get_tickets_abiertos_mes()
                con_ticket = len(tickets_mes_actuales)
                requeridos = max(0, data.cuota_mes - con_ticket)
                if requeridos == 0:
                    if incluidos:
                        raise HTTPException(
                            400,
                            "La cuota del mes ya está cubierta por los tickets abiertos este mes. "
                            "Quita las marcas o recarga la lista desde GLPI.",
                        )
                    raise HTTPException(
                        400,
                        "La cuota del mes ya está cubierta. No hay equipos pendientes por confirmar.",
                    )
                if len(incluidos) != requeridos:
                    raise HTTPException(
                        400,
                        f"Debes incluir exactamente {requeridos} equipo(s) para completar la cuota de "
                        f"{data.cuota_mes} (ya hay {con_ticket} ticket(s) este mes). "
                        f"Ahora hay {len(incluidos)} marcado(s). Ajusta las casillas o la lista.",
                    )
            elif not incluidos:
                raise HTTPException(400, "Selecciona al menos un equipo.")

            for eq in incluidos:
                try:
                    d = date.fromisoformat(eq.fecha_limite)
                    h, mn = eq.hora_inicio.split(":")
                    h_fin = str((int(h) + 1) % 24).zfill(2)
                    inicio_iso = f"{eq.fecha_limite}T{h.zfill(2)}:{mn}:00"
                    fin_iso = f"{eq.fecha_limite}T{h_fin}:{mn}:00"
                    fecha_larga = fmt_fecha_larga(d)

                    if not glpi.ticket_exists(eq.nombre):
                        ticket_id = glpi.create_ticket(eq.nombre, eq.fecha_limite)
                        glpi.link_computer(ticket_id, eq.id)
                    else:
                        ticket_id = None

                    dest_eq = (
                        [e.strip() for e in eq.destinatarios.split(",") if e.strip()]
                        if eq.destinatarios
                        else []
                    )
                    todos_destinatarios = list(set(outlook.notify_emails + dest_eq))

                    evento_id = outlook.create_event(
                        f"Mantenimiento Preventivo: {eq.nombre}",
                        inicio_iso,
                        fin_iso,
                        attendees=todos_destinatarios,
                    )

                    correo_ok = False
                    if todos_destinatarios:
                        try:
                            html = build_email_html(
                                nombre=eq.nombre,
                                fecha_larga=fecha_larga,
                                hora_inicio=eq.hora_inicio,
                                ticket_id=ticket_id,
                                glpi_url=cfg.get("glpi_url", "").replace("/apirest.php", ""),
                            )
                            outlook.send_email(
                                destinatarios=todos_destinatarios,
                                subject=f"🖥️ Mantenimiento Preventivo programado: {eq.nombre}",
                                body_html=html,
                            )
                            correo_ok = True
                        except Exception as ex_mail:
                            log.warning(f"Correo no enviado para {eq.nombre}: {ex_mail}")

                    creados.append({
                        "nombre": eq.nombre,
                        "fecha": fecha_larga,
                        "ticket_id": ticket_id,
                        "evento_id": evento_id,
                        "correo_ok": correo_ok,
                    })
                    log.info(f"OK {eq.nombre} — ticket {ticket_id} | correo: {correo_ok}")

                except Exception as ex:
                    msg = f"{eq.nombre}: {ex}"
                    errores.append(msg)
                    log.error(msg)
        finally:
            glpi.logout()

    state = load_json(STATE_PATH, {})
    key = mes_key()
    state[key] = {
        "completado": len(errores) == 0,
        "equipos": creados,
        "fecha_ejecucion": datetime.now().isoformat(),
        "modo_prueba": data.modo_prueba,
    }
    merge_meta_into_state(state)
    save_json(STATE_PATH, state)

    return {"creados": creados, "errores": errores, "ok": len(errores) == 0}


@router.post("/completar")
def completar_mantenimiento(data: CompletarIn):
    hoy = date.today().isoformat()
    checklist = load_checklist()
    total_ok = len(data.items_ok)
    total_ch = len(checklist)

    lineas = [
        f"Mantenimiento preventivo completado el {hoy}.",
        f"Items verificados: {total_ok}/{total_ch}",
        "",
    ]
    cat_actual = None
    for item in checklist:
        if item["categoria"] != cat_actual:
            cat_actual = item["categoria"]
            lineas.append(f"[{cat_actual}]")
        marca = "✓" if item["id"] in data.items_ok else "✗"
        lineas.append(f"  {marca} {item['texto']}")

    if data.notas.strip():
        lineas += ["", "Notas del técnico:", data.notas.strip()]

    resolucion = "\n".join(lineas)
    fecha_ok = False

    if data.modo_prueba:
        log.info(f"[PRUEBA] Completar mantenimiento '{data.nombre}' ticket #{data.ticket_id}")
        return {
            "ok": True,
            "ticket_cerrado": True,
            "fecha_actualizada": hoy,
            "modo_prueba": True,
        }

    cfg = get_merged_config()
    if _requests is None:
        raise HTTPException(500, "Instala requests")

    g = resolve_glpi(cfg)
    try:
        g.login()
        g.close_ticket(int(data.ticket_id), resolucion)
        log.info(f"Ticket #{data.ticket_id} cerrado — {data.nombre}")

        cid = data.computer_id
        if not cid:
            cid = g.find_computer_by_name(data.nombre)

        if cid:
            try:
                g.update_computer_fecha(cid, hoy)
                log.info(f"Fecha de mant. actualizada en Computer #{cid} → {hoy}")
                fecha_ok = True
            except Exception as ex:
                log.warning(f"No se pudo actualizar fecha del equipo: {ex}")
    finally:
        g.logout()

    state = load_json(STATE_PATH, {})
    key = mes_key()
    equipos = state.get(key, {}).get("equipos", [])
    for eq in equipos:
        if eq.get("nombre") == data.nombre:
            eq["completado"] = True
            eq["fecha_completado"] = hoy
            break
    if key in state:
        state[key]["equipos"] = equipos
        merge_meta_into_state(state)
        save_json(STATE_PATH, state)

    return {
        "ok": True,
        "ticket_cerrado": True,
        "fecha_actualizada": hoy if fecha_ok else None,
        "modo_prueba": False,
    }


@router.get("/estado")
def get_estado():
    state = load_json(STATE_PATH, {})
    key = mes_key()
    hoy = date.today()
    return {
        "mes_key": key,
        "mes_label": f"{MESES_ES[hoy.month]} {hoy.year}",
        "completado": bool(state.get(key, {}).get("completado")),
        "equipos": state.get(key, {}).get("equipos", []),
        "last_glpi_sync_at": get_last_glpi_sync_at(),
    }


@router.get("/reporte/mantenimiento-excel")
def reporte_mantenimiento_excel(
    anio: int | None = None,
    mes: int | None = None,
    modo_prueba: bool = False,
):
    """Excel con dos hojas: tickets abiertos en el mes y mantenimientos cerrados/resueltos en el mes."""
    hoy = date.today()
    y = anio if anio is not None else hoy.year
    m = mes if mes is not None else hoy.month
    if m < 1 or m > 12:
        raise HTTPException(400, "El mes debe estar entre 1 y 12.")
    if y < 2000 or y > 2100:
        raise HTTPException(400, "Año no válido.")

    if modo_prueba:
        reportados = [
            {
                "ticket_id": 90001,
                "titulo": "Mantenimiento Preventivo: PC-EJEMPLO-01",
                "nombre": "PC-EJEMPLO-01",
                "fecha_apertura": f"{y}-{m:02d}-03",
                "fecha_limite": f"{y}-{m:02d}-10",
                "fecha_cierre": "",
                "status": 2,
                "estado_txt": "En curso",
                "nota": "",
            },
        ]
        realizados = [
            {
                "ticket_id": 90002,
                "titulo": "Mantenimiento Preventivo: PC-EJEMPLO-02",
                "nombre": "PC-EJEMPLO-02",
                "fecha_apertura": f"{y}-{m:02d}-01",
                "fecha_limite": f"{y}-{m:02d}-15",
                "fecha_cierre": f"{y}-{m:02d}-12",
                "status": 6,
                "estado_txt": "Cerrado",
                "nota": "",
            },
        ]
    else:
        cfg = get_merged_config()
        if not cfg.get("glpi_url"):
            raise HTTPException(400, "Configura la URL de GLPI primero.")
        if _requests is None:
            raise HTTPException(500, "Instala requests")

        glpi = resolve_glpi(cfg)
        reportados: list = []
        realizados: list = []
        try:
            glpi.login()
            reportados, realizados = glpi.reporte_mantenimiento_mes(y, m)
        except Exception as ex:
            glpi_http_error(ex, "generar el reporte de mantenimientos desde GLPI")
        finally:
            glpi.logout()
        for r in realizados:
            r.setdefault("nota", "")
        comp_state = _completados_desde_state(y, m)
        _merge_realizados_con_state(realizados, comp_state)

    for r in reportados:
        r.setdefault("nota", "")
    for r in realizados:
        r.setdefault("nota", "")

    return build_mantenimiento_mes_excel(reportados, realizados, y, m)


@router.get("/test-outlook")
def test_outlook():
    cfg = get_merged_config()
    faltantes = []
    if not cfg.get("azure_client_id"):
        faltantes.append("azure_client_id")
    if not cfg.get("azure_client_secret"):
        faltantes.append("azure_client_secret")
    if not cfg.get("azure_tenant_id"):
        faltantes.append("azure_tenant_id")
    if not cfg.get("outlook_user_upn"):
        faltantes.append("outlook_user_upn (email del buzón)")
    if faltantes:
        return {"ok": False, "step": "config", "error": f"Faltan campos: {', '.join(faltantes)}"}

    try:
        outlook = resolve_outlook(cfg)
        outlook.authenticate()
    except Exception as ex:
        return {"ok": False, "step": "auth", "error": f"Error obteniendo token Azure: {ex}"}

    user_path = outlook._user_path()
    h = outlook._graph_headers()

    r_cals = _requests.get(
        f"https://graph.microsoft.com/v1.0/{user_path}/calendars",
        headers=h,
        timeout=15,
    )

    if not r_cals.ok:
        code = r_cals.status_code
        if code == 403:
            return {
                "ok": False,
                "step": "calendar_access",
                "error": (
                    f"Token OK, pero Graph denegó acceso a calendarios de {cfg.get('outlook_user_upn')} (403). "
                    "Verifica ApplicationAccessPolicy en Exchange Online para esta app y buzón."
                ),
            }
        return {
            "ok": False,
            "step": "calendar_access",
            "error": f"No se pudo listar calendarios ({code}): {r_cals.text[:200]}",
        }

    calendarios_disponibles = []
    for c in r_cals.json().get("value", []):
        calendarios_disponibles.append({"id": c.get("id"), "name": c.get("name")})

    cal_id = cfg.get("outlook_calendar_id", "").strip()
    cal_name = None
    cal_warning = None

    if cal_id:
        r_cal = _requests.get(
            f"https://graph.microsoft.com/v1.0/{user_path}/calendars/{cal_id}",
            headers=h,
            timeout=15,
        )
        if r_cal.ok:
            cal_name = r_cal.json().get("name", "—")
        else:
            cal_warning = (
                f"El Calendar ID guardado no es accesible ({r_cal.status_code}). "
                "Usa uno de los calendarios disponibles listados abajo, "
                "o deja el campo Calendar ID vacío para usar el calendario principal."
            )
    else:
        r_primary = _requests.get(
            f"https://graph.microsoft.com/v1.0/{user_path}/calendar",
            headers=h,
            timeout=15,
        )
        if r_primary.ok:
            cal_name = r_primary.json().get("name", "Calendario principal")
        cal_warning = "No hay Calendar ID configurado — se usará el calendario principal."

    notify = cfg.get("notify_emails", "")
    return {
        "ok": True,
        "step": "all",
        "usuario": cfg.get("outlook_user_upn"),
        "calendario": cal_name or "—",
        "cal_warning": cal_warning,
        "calendarios_disponibles": calendarios_disponibles,
        "notify_emails": notify,
        "mensaje": (
            f"Token y buzón OK. Calendario: '{cal_name or '(principal)'}'. " + (cal_warning or "")
        ),
    }


@router.post("/test-outlook-event")
def test_outlook_event():
    cfg = get_merged_config()
    faltantes = []
    if not cfg.get("azure_client_id"):
        faltantes.append("azure_client_id")
    if not cfg.get("azure_client_secret"):
        faltantes.append("azure_client_secret")
    if not cfg.get("azure_tenant_id"):
        faltantes.append("azure_tenant_id")
    if not cfg.get("outlook_user_upn"):
        faltantes.append("outlook_user_upn (email del buzón)")
    if faltantes:
        return {"ok": False, "step": "config", "error": f"Faltan campos: {', '.join(faltantes)}"}

    event_id = None
    try:
        outlook = resolve_outlook(cfg)
        outlook.authenticate()
        now = datetime.now()
        start_dt = now + timedelta(minutes=5)
        end_dt = start_dt + timedelta(minutes=15)
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        subject = f"🧪 Prueba app mantenimiento ({stamp})"
        event_id = outlook.create_event(
            subject=subject,
            inicio_iso=start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            fin_iso=end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            attendees=[],
        )
        outlook.delete_event(event_id)
        return {
            "ok": True,
            "step": "all",
            "event_created": True,
            "event_deleted": True,
            "mensaje": "Evento de prueba creado y eliminado correctamente.",
        }
    except Exception as ex:
        return {
            "ok": False,
            "step": "create_delete",
            "event_id": event_id,
            "error": f"Falló la prueba crear/eliminar evento: {ex}",
        }


@router.get("/health")
def health():
    cfg = get_merged_config()
    return {
        "status": "ok",
        "requests_ok": _requests is not None,
        "msal_ok": ConfidentialClientApplication is not None,
        "config_exists": CONFIG_PATH.exists(),
        "glpi_url": cfg.get("glpi_url", ""),
        "last_glpi_sync_at": get_last_glpi_sync_at(),
    }
