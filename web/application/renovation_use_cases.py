from datetime import date

from fastapi import HTTPException

from core.glpi_errors import glpi_http_error
from core.http_client import requests_lib as _requests
from core.state_meta import record_last_glpi_sync
from schemas import RenovacionConfirmarIn
from settings import get_merged_config


class RenovationUseCases:
    def diagnostico(self, glpi_factory):
        cfg = get_merged_config()
        if not cfg.get("glpi_url"):
            raise HTTPException(400, "Configura la URL de GLPI primero.")
        if _requests is None:
            raise HTTPException(500, "Instala requests: pip install requests")
        g = glpi_factory(cfg)
        extra = {}
        raw = []
        try:
            g.login()
            raw = g._get_all("Computer", {"is_deleted": "0", "is_template": "0", "range": "0-2"})
            if raw:
                c0 = raw[0]
                extra = {
                    "equipo_ejemplo_id": c0.get("id"),
                    "equipo_ejemplo_nombre": c0.get("name"),
                    "states_id": c0.get("states_id"),
                    "users_id": c0.get("users_id"),
                    "state_name_resuelto": g.get_state_name_by_id(c0.get("states_id")) if c0.get("states_id") else "",
                    "user_name_resuelto": g.get_user_name_by_id(c0.get("users_id")) if c0.get("users_id") else "",
                    "item_device_memory_sample": g.get_linked_items(c0, "Item_DeviceMemory")[:3],
                    "item_device_harddrive_sample": g.get_linked_items(c0, "Item_DeviceHardDrive")[:3],
                    "item_device_processor_sample": g.get_linked_items(c0, "Item_DeviceProcessor")[:3],
                }
        except Exception as ex:
            glpi_http_error(ex, "diagnóstico de renovación")
        finally:
            g.logout()
        record_last_glpi_sync()
        return {"muestra": raw[:3], "total_campos": [list(c.keys()) for c in raw[:3]], "diagnostico_specs": extra}

    def analizar(self, modo_prueba: bool, glpi_factory, parse_glpi_full, analizar_renovacion, datos_prueba):
        if modo_prueba:
            return analizar_renovacion([{**e} for e in datos_prueba])
        cfg = get_merged_config()
        if not cfg.get("glpi_url"):
            raise HTTPException(400, "Configura la URL de GLPI primero.")
        if _requests is None:
            raise HTTPException(500, "Instala requests: pip install requests")
        g = glpi_factory(cfg)
        try:
            g.login()
            raw = g.get_computers_full()
            equipos = parse_glpi_full(g, raw)
        except Exception as ex:
            glpi_http_error(ex, "cargar equipos para análisis de renovación")
        finally:
            g.logout()
        record_last_glpi_sync()
        if not equipos:
            raise HTTPException(502, "GLPI no devolvió equipos con especificaciones.")
        return analizar_renovacion(equipos)

    def confirmar(self, payload: RenovacionConfirmarIn, glpi_factory, aplicar_par):
        to_apply = [p for p in payload.pares if p.reemplazo is not None]
        if not to_apply:
            raise HTTPException(400, "No hay pares con equipo de reemplazo para aplicar.")
        for i, p in enumerate(to_apply):
            rep = p.reemplazo
            if rep is None:
                raise HTTPException(400, f"Par {i + 1}: falta equipo de reemplazo.")
            if not str(p.activo.id).strip() or not str(rep.id).strip():
                raise HTTPException(400, f"Par {i + 1}: faltan IDs de equipos.")
        if payload.modo_prueba:
            aplicados_sim = []
            for p in to_apply:
                rep = p.reemplazo
                assert rep is not None
                aplicados_sim.append({"activo_id": str(p.activo.id), "activo_nombre": p.activo.nombre, "reemplazo_id": str(rep.id), "reemplazo_nombre": rep.nombre, "detalle": "Simulación: no se modificó GLPI."})
            return {"ok": True, "modo_prueba": True, "aplicados": aplicados_sim, "errores": []}
        cfg = get_merged_config()
        if not cfg.get("glpi_url"):
            raise HTTPException(400, "Configura la URL de GLPI primero.")
        if _requests is None:
            raise HTTPException(500, "Instala requests: pip install requests")
        g = glpi_factory(cfg)
        aplicados = []
        errores: list[str] = []
        fecha_iso = date.today().isoformat()
        try:
            g.login()
            activo_sid = g.find_state_id_by_name(payload.estado_reemplazo.strip())
            debil_sid = g.find_state_id_by_name(payload.estado_debil.strip())
            if not activo_sid:
                raise HTTPException(400, f"No existe un estado «{payload.estado_reemplazo}» en GLPI.")
            if not debil_sid:
                raise HTTPException(400, f"No existe un estado «{payload.estado_debil}» en GLPI.")
            for p in to_apply:
                rep = p.reemplazo
                assert rep is not None
                try:
                    aplicar_par(g, p, estado_reemplazo_id=int(activo_sid), estado_debil_id=int(debil_sid), fecha_iso=fecha_iso, responsable=payload.responsable)
                    aplicados.append({"activo_id": str(p.activo.id), "activo_nombre": p.activo.nombre, "reemplazo_id": str(rep.id), "reemplazo_nombre": rep.nombre, "detalle": "Actualizado en GLPI."})
                except HTTPException:
                    raise
                except Exception as ex:
                    nombre = p.activo.nombre or p.activo.id
                    errores.append(f"{nombre}: {ex}")
        except HTTPException:
            raise
        except Exception as ex:
            glpi_http_error(ex, "confirmar renovación en GLPI")
        finally:
            g.logout()
        record_last_glpi_sync()
        return {"ok": len(errores) == 0, "modo_prueba": False, "aplicados": aplicados, "errores": errores}
