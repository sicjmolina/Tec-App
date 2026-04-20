import calendar as cal_module
import logging
import time
from datetime import date, datetime, timedelta

from fastapi import HTTPException

from core.checklist_util import load_checklist
from core.constants import MESES_ES
from core.dates import asignar_fechas_habiles, fmt_fecha_larga, mes_anterior_key, mes_key
from core.glpi_errors import glpi_http_error
from core.http_client import requests_lib as _requests
from core.state_meta import get_last_glpi_sync_at, merge_meta_into_state, record_last_glpi_sync
from ports.repositories import MaintenanceStateRepository
from schemas import CompletarIn, ConfirmarIn
from services.email_templates import build_email_html
from settings import CONFIG_PATH, get_merged_config

log = logging.getLogger("mant")


class MaintenanceUseCases:
    def __init__(self, state_repo: MaintenanceStateRepository):
        self.state_repo = state_repo

    def procesar_tickets_ant(self, glpi_list: list, state_list: list) -> dict:
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

    def mes_actual_done(self) -> bool:
        state = self.state_repo.load_state()
        return bool(state.get(mes_key(), {}).get("completado"))

    def datos_prueba(self):
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
        tickets_ant = self.procesar_tickets_ant(tickets_ant_raw, [])
        return {
            "total": 60,
            "cuota": 5,
            "ya_tienen": 0,
            "candidatos": candidatos,
            "reserva": reserva,
            "tickets_mes": [],
            "tickets_ant": tickets_ant,
            "mes_actual_done": self.mes_actual_done(),
            "last_glpi_sync_at": get_last_glpi_sync_at(),
        }

    def cargar_equipos(self, modo_prueba: bool, glpi_factory):
        if modo_prueba:
            return self.datos_prueba()
        cfg = get_merged_config()
        if not cfg.get("glpi_url"):
            raise HTTPException(400, "Configura la URL de GLPI primero.")
        if _requests is None:
            raise HTTPException(500, "Instala requests: pip install requests")
        g = glpi_factory(cfg)
        try:
            g.login()
            computers = g.get_computers()
            if not computers:
                raise HTTPException(502, "GLPI no devolvió equipos. Verifica el App-Token y User-Token.")
            candidatos, total, cuota, ya_tienen, tickets_mes, reserva = g.select_candidates(computers)
            candidatos = asignar_fechas_habiles(candidatos)
            tickets_ant = []
            try:
                tickets_ant = g.get_tickets_mes_anterior()
            except Exception as ex:
                log.warning(f"No se pudo obtener mes anterior: {ex}")
            state = self.state_repo.load_state()
            state_ant = state.get(mes_anterior_key(), {}).get("equipos", [])
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
            "tickets_ant": self.procesar_tickets_ant(tickets_ant, state_ant),
            "mes_actual_done": self.mes_actual_done(),
            "last_glpi_sync_at": get_last_glpi_sync_at(),
        }

    def confirmar(self, data: ConfirmarIn, glpi_factory, outlook_factory):
        incluidos = [e for e in data.equipos if e.incluido]
        cfg = get_merged_config()
        creados = []
        errores = []
        if data.modo_prueba:
            if data.cuota_mes > 0 and len(incluidos) != data.cuota_mes:
                raise HTTPException(400, f"[Prueba] Debes incluir exactamente {data.cuota_mes} equipo(s). Ahora hay {len(incluidos)} marcado(s).")
            if data.cuota_mes <= 0 and not incluidos:
                raise HTTPException(400, "Selecciona al menos un equipo.")
            for i, eq in enumerate(incluidos):
                time.sleep(0.1)
                d = date.fromisoformat(eq.fecha_limite)
                creados.append({"nombre": eq.nombre, "fecha": fmt_fecha_larga(d), "ticket_id": 90000 + i, "evento_id": f"fake-event-{i}", "correo_ok": False})
        else:
            if _requests is None:
                raise HTTPException(500, "Instala requests")
            glpi = glpi_factory(cfg)
            outlook = outlook_factory(cfg)
            glpi.login()
            outlook.authenticate()
            try:
                if data.cuota_mes > 0:
                    _, tickets_mes_actuales = glpi.get_tickets_abiertos_mes()
                    con_ticket = len(tickets_mes_actuales)
                    requeridos = max(0, data.cuota_mes - con_ticket)
                    if requeridos == 0:
                        raise HTTPException(400, "La cuota del mes ya está cubierta. No hay equipos pendientes por confirmar.")
                    if len(incluidos) != requeridos:
                        raise HTTPException(400, f"Debes incluir exactamente {requeridos} equipo(s). Ahora hay {len(incluidos)} marcado(s).")
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
                        dest_eq = [e.strip() for e in eq.destinatarios.split(",") if e.strip()] if eq.destinatarios else []
                        todos_destinatarios = list(set(outlook.notify_emails + dest_eq))
                        evento_id = outlook.create_event(f"Mantenimiento Preventivo: {eq.nombre}", inicio_iso, fin_iso, attendees=todos_destinatarios)
                        correo_ok = False
                        if todos_destinatarios:
                            try:
                                html = build_email_html(nombre=eq.nombre, fecha_larga=fecha_larga, hora_inicio=eq.hora_inicio, ticket_id=ticket_id, glpi_url=cfg.get("glpi_url", "").replace("/apirest.php", ""))
                                outlook.send_email(destinatarios=todos_destinatarios, subject=f"🖥️ Mantenimiento Preventivo programado: {eq.nombre}", body_html=html)
                                correo_ok = True
                            except Exception as ex_mail:
                                log.warning(f"Correo no enviado para {eq.nombre}: {ex_mail}")
                        creados.append({"nombre": eq.nombre, "fecha": fecha_larga, "ticket_id": ticket_id, "evento_id": evento_id, "correo_ok": correo_ok})
                    except Exception as ex:
                        errores.append(f"{eq.nombre}: {ex}")
            finally:
                glpi.logout()
        state = self.state_repo.load_state()
        key = mes_key()
        state[key] = {"completado": len(errores) == 0, "equipos": creados, "fecha_ejecucion": datetime.now().isoformat(), "modo_prueba": data.modo_prueba}
        merge_meta_into_state(state)
        self.state_repo.save_state(state)
        return {"creados": creados, "errores": errores, "ok": len(errores) == 0}

    def completar(self, data: CompletarIn, glpi_factory):
        hoy = date.today().isoformat()
        checklist = load_checklist()
        lineas = [f"Mantenimiento preventivo completado el {hoy}.", f"Items verificados: {len(data.items_ok)}/{len(checklist)}", ""]
        cat_actual = None
        for item in checklist:
            if item["categoria"] != cat_actual:
                cat_actual = item["categoria"]
                lineas.append(f"[{cat_actual}]")
            lineas.append(f"  {'✓' if item['id'] in data.items_ok else '✗'} {item['texto']}")
        if data.notas.strip():
            lineas += ["", "Notas del técnico:", data.notas.strip()]
        resolucion = "\n".join(lineas)
        if data.modo_prueba:
            return {"ok": True, "ticket_cerrado": True, "fecha_actualizada": hoy, "modo_prueba": True}
        cfg = get_merged_config()
        if _requests is None:
            raise HTTPException(500, "Instala requests")
        g = glpi_factory(cfg)
        fecha_ok = False
        try:
            g.login()
            g.close_ticket(int(data.ticket_id), resolucion)
            cid = data.computer_id or g.find_computer_by_name(data.nombre)
            if cid:
                try:
                    g.update_computer_fecha(cid, hoy)
                    fecha_ok = True
                except Exception as ex:
                    log.warning(f"No se pudo actualizar fecha del equipo: {ex}")
        finally:
            g.logout()
        state = self.state_repo.load_state()
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
            self.state_repo.save_state(state)
        return {"ok": True, "ticket_cerrado": True, "fecha_actualizada": hoy if fecha_ok else None, "modo_prueba": False}

    def get_estado(self):
        state = self.state_repo.load_state()
        key = mes_key()
        hoy = date.today()
        return {"mes_key": key, "mes_label": f"{MESES_ES[hoy.month]} {hoy.year}", "completado": bool(state.get(key, {}).get("completado")), "equipos": state.get(key, {}).get("equipos", []), "last_glpi_sync_at": get_last_glpi_sync_at()}

    def completados_desde_state(self, year: int, month: int) -> dict[int, dict]:
        key = mes_key(date(year, month, 1))
        ultimo = cal_module.monthrange(year, month)[1]
        desde_s = f"{year}-{month:02d}-01"
        hasta_s = f"{year}-{month:02d}-{ultimo:02d}"
        out = {}
        for eq in self.state_repo.load_state().get(key, {}).get("equipos", []):
            if not eq.get("completado"):
                continue
            fc = (eq.get("fecha_completado") or "")[:10]
            if not fc or not (desde_s <= fc <= hasta_s):
                continue
            tid = eq.get("ticket_id")
            try:
                tid_i = int(tid)
            except (TypeError, ValueError):
                continue
            out[tid_i] = {"fecha_cierre": fc, "nombre": eq.get("nombre", "—")}
        return out

    def merge_realizados_con_state(self, realizados: list, comp_state: dict[int, dict]) -> None:
        seen = set()
        for r in realizados:
            tid = r.get("ticket_id")
            try:
                tidi = int(tid) if tid is not None else None
            except (TypeError, ValueError):
                tidi = None
            if tidi is not None:
                seen.add(tidi)
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
        realizados.sort(key=lambda x: (x.get("fecha_cierre") or "", str(x.get("nombre") or "").lower()))
