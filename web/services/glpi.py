import calendar as cal_module
import logging
from datetime import date, datetime

from core.constants import STATUS_MAP
from core.http_client import requests_lib as _requests

log = logging.getLogger("mant")


def _estado_permite_mantenimiento_preventivo(nombre_estado: str) -> bool:
    """
    Inactivos, stock, reserva, baja u obsoletos no entran en mantenimiento preventivo.
    Sin nombre de estado o estados no reconocidos: se incluyen (evita falsos negativos).
    """
    s = (nombre_estado or "").strip().lower()
    if not s:
        return True
    if s in ("1", "2"):
        return s == "1"
    if "inactivo" in s or "stock" in s or "reserva" in s or "almacen" in s or "almacén" in s:
        return False
    if "baja" in s or "retir" in s or "obsole" in s or "desech" in s:
        return False
    return True


class GLPIClient:
    def __init__(self, cfg: dict):
        self.base = cfg.get("glpi_url", "").rstrip("/")
        self.app_token = cfg.get("glpi_app_token", "")
        self.user_token = cfg.get("glpi_user_token", "")
        self.category_id = int(cfg.get("glpi_category_id", 22))
        self.field_id = str(cfg.get("glpi_field_id", 76670))
        self.session = None

    def login(self):
        r = _requests.get(
            f"{self.base}/initSession",
            timeout=15,
            headers={
                "App-Token": self.app_token,
                "Authorization": f"user_token {self.user_token}",
            },
        )
        r.raise_for_status()
        self.session = r.json()["session_token"]

    def logout(self):
        if self.session:
            try:
                _requests.get(f"{self.base}/killSession", timeout=5, headers=self._h())
            except Exception:
                pass
            self.session = None

    def _h(self):
        return {
            "App-Token": self.app_token,
            "Session-Token": self.session,
            "Content-Type": "application/json",
        }

    def _get_all(self, endpoint: str, params: dict) -> list:
        """Pagina automáticamente hasta agotar resultados."""
        results = []
        page_size = 200
        start = 0
        while True:
            p = {**params, "range": f"{start}-{start + page_size - 1}"}
            r = _requests.get(f"{self.base}/{endpoint}", timeout=30, headers=self._h(), params=p)
            if r.status_code == 206:
                chunk = r.json()
                results.extend(chunk if isinstance(chunk, list) else [])
                start += page_size
                if len(chunk) < page_size:
                    break
            elif r.status_code == 200:
                chunk = r.json()
                results.extend(chunk if isinstance(chunk, list) else [])
                break
            else:
                break
        return results

    def get_computers(self) -> list:
        return self._get_all(
            "Computer",
            {
                "forcedisplay[0]": "1",
                "forcedisplay[1]": "2",
                "forcedisplay[2]": self.field_id,
                "forcedisplay[3]": "70",
                "forcedisplay[4]": "31",
                "is_deleted": "0",
                "is_template": "0",
            },
        )

    def state_id_to_name_map(self) -> dict:
        """states_id (str) → nombre (misma convención que búsquedas GLPI)."""
        out = {}
        for s in self._get_all("State", {"is_deleted": "0"}):
            sid = s.get("2") if s.get("2") is not None else s.get("id")
            if sid is None:
                continue
            name = str(s.get("1") or s.get("name") or "").strip()
            out[str(sid).strip()] = name
        return out

    def computer_type_id_to_name_map(self) -> dict:
        """computertypes_id (str) → nombre (Portátil, Escritorio, …)."""
        out = {}
        for t in self._get_all("ComputerType", {"is_deleted": "0"}):
            tid = t.get("2") if t.get("2") is not None else t.get("id")
            if tid is None:
                continue
            name = str(t.get("1") or t.get("name") or "").strip()
            out[str(tid).strip()] = name
        return out

    def users_id_to_display_map(self) -> dict:
        """users_id (str) → nombre para mostrar (campo completo / login), como en inventario."""
        raw = self._get_all(
            "User",
            {
                "is_deleted": "0",
                "forcedisplay[0]": "1",
                "forcedisplay[1]": "2",
                "forcedisplay[2]": "34",
            },
        )
        out = {}
        for u in raw:
            uid = u.get("2") if u.get("2") is not None else u.get("id")
            if uid is None:
                continue
            key = str(uid).strip()
            nombre = str(u.get("1") or u.get("name") or "").strip()
            display = str(u.get("34") or "").strip()
            out[key] = (display or nombre or key).strip() or key
        return out

    def get_computer(self, computer_id):
        r = _requests.get(
            f"{self.base}/Computer/{computer_id}",
            timeout=20,
            headers=self._h(),
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None

    def find_state_id_by_name(self, nombre_estado: str):
        """Busca un State por nombre y devuelve su ID."""
        nombre_estado = (nombre_estado or "").strip()
        if not nombre_estado:
            return None
        r = _requests.get(
            f"{self.base}/State",
            timeout=20,
            headers=self._h(),
            params={
                "searchText[name]": nombre_estado,
                "forcedisplay[0]": "1",
                "forcedisplay[1]": "2",
                "range": "0-20",
                "is_deleted": "0",
            },
        )
        if r.status_code not in (200, 206):
            return None
        data = r.json()
        if not isinstance(data, list):
            return None
        target = nombre_estado.upper()
        for s in data:
            name = str(s.get("1") or s.get("name") or "").strip().upper()
            if name == target:
                return s.get("2") or s.get("id")
        if len(data) > 0:
            return data[0].get("2") or data[0].get("id")
        return None

    def update_computer_fields(self, computer_id, users_id=None, states_id=None):
        """Actualiza usuario y/o estado del activo Computer en GLPI."""
        input_data = {}
        if users_id is not None and str(users_id).strip() != "":
            input_data["users_id"] = int(users_id)
        if states_id is not None and str(states_id).strip() != "":
            input_data["states_id"] = int(states_id)
        if not input_data:
            return
        r = _requests.put(
            f"{self.base}/Computer/{computer_id}",
            timeout=20,
            headers=self._h(),
            json={"input": input_data},
        )
        r.raise_for_status()

    def append_computer_comment(self, computer_id, line: str):
        """Agrega una línea al campo comentario del activo en GLPI."""
        current = self.get_computer(computer_id) or {}
        prev = str(current.get("comment") or "").strip()
        merged = f"{prev}\n{line}".strip() if prev else line
        r = _requests.put(
            f"{self.base}/Computer/{computer_id}",
            timeout=20,
            headers=self._h(),
            json={"input": {"comment": merged}},
        )
        r.raise_for_status()

    def get_tickets_abiertos_mes(self):
        hoy = date.today()
        mes_actual = f"{hoy.year}-{hoy.month:02d}"
        tickets_raw = self._get_all(
            "Ticket",
            {
                "searchText[name]": "Mantenimiento Preventivo",
                "criteria[0][field]": "22",
                "criteria[0][searchtype]": "equals",
                "criteria[0][value]": str(self.category_id),
                "criteria[1][field]": "12",
                "criteria[1][searchtype]": "lessthan",
                "criteria[1][value]": "6",
            },
        )
        nombres = set()
        tickets = []
        for t in tickets_raw:
            nombre_ticket = str(t.get("name", ""))
            fecha_apertura = str(t.get("date", ""))[:7]
            if fecha_apertura != mes_actual or ":" not in nombre_ticket:
                continue
            nombre = nombre_ticket.split(":", 1)[1].strip()
            status_id = int(t.get("status", 1))
            fecha_limite = str(t.get("time_to_resolve", ""))[:10] or "—"
            nombres.add(nombre.upper())
            tickets.append({
                "id": t.get("id"),
                "nombre": nombre,
                "status_id": status_id,
                "status_txt": STATUS_MAP.get(status_id, "?"),
                "fecha_limite": fecha_limite,
            })
        tickets.sort(key=lambda t: (t["status_id"] in [5, 6], t["nombre"]))
        return nombres, tickets

    def list_tickets_mantenimiento_categoria(self) -> list:
        """Tickets de mantenimiento preventivo (misma categoría ITIL que el resto de la app)."""
        return self._get_all(
            "Ticket",
            {
                "searchText[name]": "Mantenimiento Preventivo",
                "criteria[0][field]": "22",
                "criteria[0][searchtype]": "equals",
                "criteria[0][value]": str(self.category_id),
            },
        )

    def _ticket_row_reporte(self, t: dict) -> dict | None:
        name_full = str(t.get("name") or t.get("1") or "").strip()
        if not name_full:
            return None
        if ":" in name_full:
            equipo = name_full.split(":", 1)[1].strip()
        else:
            equipo = name_full.replace("Mantenimiento Preventivo", "").strip() or "—"
        tid = t.get("id")
        if tid is None:
            tid = t.get("2")
        try:
            raw_st = t.get("status") if t.get("status") is not None else t.get("12")
            status = int(raw_st) if raw_st is not None and str(raw_st).strip() != "" else 0
        except (TypeError, ValueError):
            status = 0

        def _fecha10(val) -> str:
            if not val:
                return ""
            s = str(val).strip()
            return s[:10] if len(s) >= 10 else s

        fa = _fecha10(t.get("date") or t.get("15"))
        fc = _fecha10(
            t.get("closedate")
            or t.get("solvedate")
            or t.get("19")
            or t.get("34")
        )
        lim = _fecha10(t.get("time_to_resolve") or t.get("18"))
        return {
            "ticket_id": tid,
            "titulo": name_full,
            "nombre": equipo,
            "fecha_apertura": fa,
            "fecha_limite": lim or "—",
            "fecha_cierre": fc,
            "status": status,
            "estado_txt": STATUS_MAP.get(status, str(status)),
        }

    def reporte_mantenimiento_mes(self, year: int, month: int) -> tuple[list, list]:
        """(reportados, realizados) según calendario año/mes.

        Reportados: fecha de apertura dentro del mes.
        Realizados: fecha de cierre/resolución dentro del mes y estado resuelto o cerrado.
        """
        ultimo = cal_module.monthrange(year, month)[1]
        desde_s = f"{year}-{month:02d}-01"
        hasta_s = f"{year}-{month:02d}-{ultimo:02d}"
        raw = self.list_tickets_mantenimiento_categoria()
        reportados: list = []
        realizados: list = []
        seen_real: set = set()
        for t in raw:
            row = self._ticket_row_reporte(t)
            if not row:
                continue
            fa = row["fecha_apertura"]
            if fa and desde_s <= fa <= hasta_s:
                reportados.append(row.copy())
            fc = row["fecha_cierre"]
            st = row["status"]
            tid = row["ticket_id"]
            if fc and desde_s <= fc <= hasta_s and st in (5, 6) and tid not in seen_real:
                seen_real.add(tid)
                realizados.append(row.copy())
        reportados.sort(key=lambda x: (x["fecha_apertura"], str(x["nombre"]).lower()))
        realizados.sort(key=lambda x: (x["fecha_cierre"], str(x["nombre"]).lower()))
        return reportados, realizados

    def select_candidates(self, computers: list, cuota: int = None):
        total = len(computers)
        if cuota is None:
            cuota = max(1, -(-total // 12))
        current_year = date.today().year
        ya_tienen_ticket, tickets_mes = self.get_tickets_abiertos_mes()
        users_map = self.users_id_to_display_map()
        state_map = self.state_id_to_name_map()
        state_name_fallback = {}
        plugin_fechas = self._plugin_ultima_fecha_map()

        candidatos = []
        ya_tienen_count = 0
        for eq in computers:
            cid = str(eq.get("2") or eq.get("id") or "").strip()
            raw = eq.get(self.field_id)
            if raw is None or str(raw).strip() in ("", "null", "None"):
                raw = plugin_fechas.get(cid) if cid else None
            try:
                fecha = (
                    datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
                    if raw and raw != "null"
                    else date(1990, 1, 1)
                )
            except Exception:
                fecha = date(1990, 1, 1)
            nombre = str(eq.get("1") or eq.get("name") or "Sin nombre").strip()
            if nombre.upper() in ya_tienen_ticket:
                ya_tienen_count += 1
                continue
            raw_sid = eq.get("states_id")
            if raw_sid is None or raw_sid == "":
                raw_sid = eq.get("31")
            sid_key = str(raw_sid).strip() if raw_sid is not None and str(raw_sid).strip() not in ("", "0") else ""
            estado_nombre = state_map.get(sid_key, "") if sid_key else ""
            if sid_key and not estado_nombre:
                if sid_key not in state_name_fallback:
                    state_name_fallback[sid_key] = self.get_state_name_by_id(sid_key) or ""
                estado_nombre = state_name_fallback[sid_key]
            if not _estado_permite_mantenimiento_preventivo(estado_nombre):
                continue
            raw_uid = eq.get("users_id")
            if raw_uid is None or raw_uid == "":
                raw_uid = eq.get("70")
            uid_s = str(raw_uid).strip() if raw_uid is not None and str(raw_uid).strip() != "" else ""
            if uid_s == "0":
                uid_s = ""
            if uid_s:
                usuario_asignado = users_map.get(uid_s) or ""
                if not usuario_asignado:
                    usuario_asignado = f"Usuario GLPI id {uid_s}"
            else:
                usuario_asignado = ""
            candidatos.append({
                "id": eq.get("2") or eq.get("id"),
                "nombre": nombre,
                "ultima_fecha": fecha.isoformat(),
                "usuario_asignado": usuario_asignado,
            })

        candidatos = [c for c in candidatos if date.fromisoformat(c["ultima_fecha"]).year < current_year]
        candidatos.sort(key=lambda x: x["ultima_fecha"])
        seleccion = candidatos[:cuota]
        reserva = candidatos[cuota:]
        return seleccion, total, cuota, ya_tienen_count, tickets_mes, reserva

    def ticket_exists(self, nombre: str) -> bool:
        hoy = date.today()
        desde = f"{hoy.year}-{hoy.month:02d}-01"
        r = _requests.get(
            f"{self.base}/Ticket",
            timeout=20,
            headers=self._h(),
            params={
                "searchText[name]": f"Mantenimiento Preventivo: {nombre}",
                "criteria[0][field]": "22",
                "criteria[0][searchtype]": "equals",
                "criteria[0][value]": str(self.category_id),
                "criteria[1][field]": "12",
                "criteria[1][searchtype]": "lessthan",
                "criteria[1][value]": "6",
                "criteria[2][field]": "15",
                "criteria[2][searchtype]": "morethan",
                "criteria[2][value]": desde,
                "range": "0-1",
            },
        )
        if r.status_code != 200:
            return False
        d = r.json()
        return isinstance(d, list) and len(d) > 0

    def create_ticket(self, nombre: str, fecha_iso: str) -> int:
        r = _requests.post(
            f"{self.base}/Ticket",
            headers=self._h(),
            json={
                "input": {
                    "name": f"Mantenimiento Preventivo: {nombre}",
                    "content": f"Mantenimiento preventivo programado.\nEquipo: {nombre}",
                    "itilcategories_id": self.category_id,
                    "type": 1,
                    "status": 1,
                    "time_to_resolve": f"{fecha_iso} 17:00:00",
                }
            },
        )
        r.raise_for_status()
        return r.json().get("id")

    def link_computer(self, ticket_id: int, computer_id):
        _requests.post(
            f"{self.base}/Item_Ticket",
            headers=self._h(),
            json={
                "input": {
                    "tickets_id": ticket_id,
                    "itemtype": "Computer",
                    "items_id": computer_id,
                }
            },
        )

    def close_ticket(self, ticket_id: int, resolucion: str) -> None:
        """Cierra un ticket (status=6) y escribe la solución."""
        _requests.put(
            f"{self.base}/Ticket/{ticket_id}",
            headers=self._h(),
            json={"input": {"status": 6, "solution": resolucion}},
        )
        try:
            _requests.post(
                f"{self.base}/ITILSolution",
                headers=self._h(),
                json={
                    "input": {
                        "itemtype": "Ticket",
                        "items_id": ticket_id,
                        "content": resolucion,
                        "status": 2,
                    }
                },
            )
        except Exception:
            pass

    _PF_ITEMTYPE = "PluginFieldsComputerfechadeultimomantenimiento"
    _PF_FIELD = "fechafield"

    def _plugin_ultima_fecha_map(self) -> dict[str, str]:
        """Mapa Computer.id → fecha YYYY-MM-DD leída del plugin Additional Fields.

        GET /Computer con forcedisplay a veces no incluye columnas del plugin; al cerrar
        tickets la fecha sí está en ``PluginFieldsComputerfechadeultimomantenimiento``.
        """
        out: dict[str, str] = {}
        try:
            for rec in self._get_all(self._PF_ITEMTYPE, {}):
                iid = rec.get("items_id")
                if iid is None or str(iid).strip() == "":
                    continue
                val = rec.get(self._PF_FIELD) or rec.get("fechafield")
                if val is None or str(val).strip() in ("", "null"):
                    continue
                s = str(val).strip()
                out[str(iid).strip()] = s[:10] if len(s) >= 10 else s
        except Exception as ex:
            log.warning("Plugin Fields: no se pudieron leer fechas de último mantenimiento: %s", ex)
        return out

    def update_computer_fecha(self, computer_id, fecha_iso: str) -> None:
        endpoint = self._PF_ITEMTYPE
        r = _requests.get(
            f"{self.base}/{endpoint}",
            timeout=15,
            headers=self._h(),
            params={"searchText[items_id]": str(computer_id), "range": "0-1"},
        )

        registro_id = None
        if r.status_code in (200, 206):
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                for rec in data:
                    if str(rec.get("items_id")) == str(computer_id):
                        registro_id = rec.get("id")
                        break

        if registro_id:
            r2 = _requests.put(
                f"{self.base}/{endpoint}/{registro_id}",
                headers=self._h(),
                json={"input": {self._PF_FIELD: fecha_iso}},
            )
            r2.raise_for_status()
            log.info(f"Additional Fields: registro {registro_id} actualizado → {fecha_iso}")
        else:
            r2 = _requests.post(
                f"{self.base}/{endpoint}",
                headers=self._h(),
                json={
                    "input": {
                        "items_id": computer_id,
                        "itemtype": "Computer",
                        "plugin_fields_containers_id": 5,
                        self._PF_FIELD: fecha_iso,
                    }
                },
            )
            r2.raise_for_status()
            log.info(f"Additional Fields: nuevo registro creado para Computer {computer_id} → {fecha_iso}")

    def find_computer_by_name(self, nombre: str):
        """Busca el ID de un Computer por nombre exacto."""
        r = _requests.get(
            f"{self.base}/Computer",
            timeout=20,
            headers=self._h(),
            params={
                "searchText[name]": nombre,
                "forcedisplay[0]": "1",
                "forcedisplay[1]": "2",
                "range": "0-5",
                "is_deleted": "0",
            },
        )
        if r.status_code not in (200, 206):
            return None
        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            return None
        for eq in data:
            if str(eq.get("1", "")).strip().upper() == nombre.strip().upper():
                return eq.get("2") or eq.get("id")
        return data[0].get("2") or data[0].get("id")

    def get_tickets_mes_anterior(self) -> list:
        hoy = date.today()
        y, m = (hoy.year - 1, 12) if hoy.month == 1 else (hoy.year, hoy.month - 1)
        desde = f"{y}-{m:02d}-01"
        hasta = f"{y}-{m:02d}-{cal_module.monthrange(y, m)[1]:02d}"
        return self._get_all(
            "Ticket",
            {
                "searchText[name]": "Mantenimiento Preventivo",
                "criteria[0][field]": "22",
                "criteria[0][searchtype]": "equals",
                "criteria[0][value]": str(self.category_id),
                "criteria[1][field]": "15",
                "criteria[1][searchtype]": "morethan",
                "criteria[1][value]": desde,
                "criteria[2][field]": "15",
                "criteria[2][searchtype]": "lessthan",
                "criteria[2][value]": hasta,
                "forcedisplay[0]": "1",
                "forcedisplay[1]": "12",
            },
        )

    def get_computers_full(self) -> list:
        return self._get_all(
            "Computer",
            {"is_deleted": "0", "is_template": "0"},
        )

    def _get_url(self, url: str):
        r = _requests.get(url, timeout=30, headers=self._h())
        if r.status_code not in (200, 206):
            return None
        try:
            return r.json()
        except Exception:
            return None

    def get_linked_items(self, computer: dict, rel_name: str) -> list:
        links = computer.get("links") or []
        href = None
        for link in links:
            if str(link.get("rel", "")).strip().lower() == rel_name.lower():
                href = link.get("href")
                break
        if not href:
            return []
        data = self._get_url(href)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if isinstance(data.get("data"), list):
                return data["data"]
            if isinstance(data.get("value"), list):
                return data["value"]
        return []

    def get_state_name_by_id(self, state_id):
        if not state_id:
            return ""
        data = self._get_url(f"{self.base}/State/{state_id}")
        if isinstance(data, dict):
            return str(data.get("name") or "").strip()
        return ""

    def get_user_name_by_id(self, user_id):
        if not user_id:
            return ""
        data = self._get_url(f"{self.base}/User/{user_id}")
        if isinstance(data, dict):
            name = str(data.get("name") or "").strip()
            real = str(data.get("realname") or "").strip()
            first = str(data.get("firstname") or "").strip()
            if real or first:
                full = f"{first} {real}".strip()
                return full or name
            return name
        return ""
