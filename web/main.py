"""
Mantenimientos Preventivos v2 — Sicolsa
Backend FastAPI — localhost
"""

import json
import calendar as cal_module
import logging
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

try:
    from sqlalchemy import create_engine, MetaData, Table, Column, Text, DateTime, select, delete
except ImportError:
    create_engine = None
    MetaData = None
    Table = None
    Column = None
    Text = None
    DateTime = None
    select = None
    delete = None

# ── Intentos de importar dependencias opcionales ─────────────────
try:
    import requests as _requests
except ImportError:
    _requests = None

try:
    from msal import ConfidentialClientApplication
except ImportError:
    ConfidentialClientApplication = None

# ── Rutas de datos ────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH  = BASE_DIR / "state.json"
LOG_PATH    = BASE_DIR / "mant.log"
INVENTORY_PATH = BASE_DIR / "inventory_history.json"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("mant")

# ── Almacenamiento (JSON local o DB) ─────────────────────────────
DB_ENABLED = bool(DATABASE_URL and create_engine is not None)
DB_ENGINE = None
DB_TABLE = None

if DB_ENABLED:
    try:
        DB_ENGINE = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
        meta = MetaData()
        DB_TABLE = Table(
            "app_kv",
            meta,
            Column("k", Text, primary_key=True),
            Column("v", Text, nullable=False),
            Column("updated_at", DateTime, nullable=False),
        )
        meta.create_all(DB_ENGINE)
        log.info("DB habilitada para configuración/estado/checklist/inventario.")
    except Exception as ex:
        DB_ENABLED = False
        DB_ENGINE = None
        DB_TABLE = None
        log.warning(f"No se pudo inicializar DB, se usará archivos JSON. Detalle: {ex}")


def _store_key(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR)).replace("\\", "/")
    except Exception:
        return path.name

# ── Helpers JSON ─────────────────────────────────────────────────
def load_json(path: Path, default=None):
    if DB_ENABLED and DB_ENGINE is not None and DB_TABLE is not None:
        key = _store_key(path)
        try:
            with DB_ENGINE.connect() as conn:
                row = conn.execute(
                    select(DB_TABLE.c.v).where(DB_TABLE.c.k == key)
                ).first()
            if row and row[0]:
                return json.loads(row[0])
        except Exception as ex:
            log.warning(f"load_json DB fallback a archivo ({key}): {ex}")

        # Migración automática: si existe archivo local, lo sube a DB.
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            save_json(path, data)
            return data
        return default if default is not None else {}

    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}

def save_json(path: Path, data):
    if DB_ENABLED and DB_ENGINE is not None and DB_TABLE is not None:
        key = _store_key(path)
        try:
            payload = json.dumps(data, ensure_ascii=False)
            now = datetime.now()
            with DB_ENGINE.begin() as conn:
                row = conn.execute(select(DB_TABLE.c.k).where(DB_TABLE.c.k == key)).first()
                if row:
                    conn.execute(
                        DB_TABLE.update()
                        .where(DB_TABLE.c.k == key)
                        .values(v=payload, updated_at=now)
                    )
                else:
                    conn.execute(DB_TABLE.insert().values(k=key, v=payload, updated_at=now))
            return
        except Exception as ex:
            log.warning(f"save_json DB fallback a archivo ({key}): {ex}")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def delete_json(path: Path):
    if DB_ENABLED and DB_ENGINE is not None and DB_TABLE is not None:
        key = _store_key(path)
        try:
            with DB_ENGINE.begin() as conn:
                conn.execute(delete(DB_TABLE).where(DB_TABLE.c.k == key))
            return
        except Exception as ex:
            log.warning(f"delete_json DB fallback a archivo ({key}): {ex}")
    if path.exists():
        path.unlink()

# ── Constantes ────────────────────────────────────────────────────
MESES_ES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
            "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
DIAS_ES  = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]

STATUS_MAP = {1:"Nuevo", 2:"En curso", 3:"En espera",
              4:"Pendiente", 5:"Resuelto", 6:"Cerrado"}

def mes_key(d: date = None):
    d = d or date.today()
    return f"{d.year}-{d.month:02d}"

def mes_anterior_key():
    hoy = date.today()
    if hoy.month == 1:
        return f"{hoy.year-1}-12"
    return f"{hoy.year}-{hoy.month-1:02d}"

def dias_habiles(year: int, month: int):
    _, ultimo = cal_module.monthrange(year, month)
    return [date(year, month, d)
            for d in range(1, ultimo + 1)
            if date(year, month, d).weekday() < 5]

def asignar_fechas_habiles(equipos: list, year=None, month=None):
    hoy = date.today()
    y, m = (year or hoy.year), (month or hoy.month)
    dias = dias_habiles(y, m)
    dias = [d for d in dias if d >= hoy] or dias
    total = len(equipos)
    if total == 0:
        return []
    intervalo = max(1, len(dias) // total)
    resultado = []
    for i, eq in enumerate(equipos):
        idx = min(i * intervalo + intervalo // 2, len(dias) - 1)
        resultado.append({**eq, "fecha_limite": dias[idx].isoformat()})
    return resultado

def fmt_fecha_larga(d: date):
    return f"{DIAS_ES[d.weekday()]}, {d.day:02d} de {MESES_ES[d.month].lower()}"


# ══════════════════════════════════════════════════════════════════
# GLPI Client
# ══════════════════════════════════════════════════════════════════
class GLPIClient:
    def __init__(self, cfg: dict):
        self.base        = cfg.get("glpi_url", "").rstrip("/")
        self.app_token   = cfg.get("glpi_app_token", "")
        self.user_token  = cfg.get("glpi_user_token", "")
        self.category_id = int(cfg.get("glpi_category_id", 22))
        self.field_id    = str(cfg.get("glpi_field_id", 76670))
        self.session     = None

    def login(self):
        r = _requests.get(f"{self.base}/initSession", timeout=15, headers={
            "App-Token": self.app_token,
            "Authorization": f"user_token {self.user_token}",
        })
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
            r = _requests.get(f"{self.base}/{endpoint}", timeout=30,
                              headers=self._h(), params=p)
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
        return self._get_all("Computer", {
            "forcedisplay[0]": "1",
            "forcedisplay[1]": "2",
            "forcedisplay[2]": self.field_id,
            "is_deleted": "0",
            "is_template": "0",
        })

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
        r = _requests.get(f"{self.base}/State", timeout=20, headers=self._h(), params={
            "searchText[name]": nombre_estado,
            "forcedisplay[0]": "1",
            "forcedisplay[1]": "2",
            "range": "0-20",
            "is_deleted": "0",
        })
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
        tickets_raw = self._get_all("Ticket", {
            "searchText[name]": "Mantenimiento Preventivo",
            "criteria[0][field]": "22",
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": str(self.category_id),
            "criteria[1][field]": "12",
            "criteria[1][searchtype]": "lessthan",
            "criteria[1][value]": "6",
        })
        nombres = set()
        tickets = []
        for t in tickets_raw:
            nombre_ticket  = str(t.get("name", ""))
            fecha_apertura = str(t.get("date", ""))[:7]
            if fecha_apertura != mes_actual or ":" not in nombre_ticket:
                continue
            nombre    = nombre_ticket.split(":", 1)[1].strip()
            status_id = int(t.get("status", 1))
            fecha_limite = str(t.get("time_to_resolve", ""))[:10] or "—"
            nombres.add(nombre.upper())
            tickets.append({
                "id":           t.get("id"),
                "nombre":       nombre,
                "status_id":    status_id,
                "status_txt":   STATUS_MAP.get(status_id, "?"),
                "fecha_limite": fecha_limite,
            })
        tickets.sort(key=lambda t: (t["status_id"] in [5, 6], t["nombre"]))
        return nombres, tickets

    def select_candidates(self, computers: list, cuota: int = None):
        total = len(computers)
        if cuota is None:
            cuota = max(1, -(-total // 12))
        current_year = date.today().year
        ya_tienen_ticket, tickets_mes = self.get_tickets_abiertos_mes()

        candidatos = []
        ya_tienen_count = 0
        for eq in computers:
            raw = eq.get(self.field_id)
            try:
                fecha = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date() \
                        if raw and raw != "null" else date(1990, 1, 1)
            except Exception:
                fecha = date(1990, 1, 1)
            nombre = str(eq.get("1") or eq.get("name") or "Sin nombre").strip()
            if nombre.upper() in ya_tienen_ticket:
                ya_tienen_count += 1
                continue
            candidatos.append({
                "id": eq.get("2") or eq.get("id"),
                "nombre": nombre,
                "ultima_fecha": fecha.isoformat(),
            })

        candidatos = [c for c in candidatos
                      if date.fromisoformat(c["ultima_fecha"]).year < current_year]
        candidatos.sort(key=lambda x: x["ultima_fecha"])
        return candidatos[:cuota], total, cuota, ya_tienen_count, tickets_mes

    def ticket_exists(self, nombre: str) -> bool:
        hoy   = date.today()
        desde = f"{hoy.year}-{hoy.month:02d}-01"
        r = _requests.get(f"{self.base}/Ticket", timeout=20, headers=self._h(), params={
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
        })
        if r.status_code != 200:
            return False
        d = r.json()
        return isinstance(d, list) and len(d) > 0

    def create_ticket(self, nombre: str, fecha_iso: str) -> int:
        r = _requests.post(f"{self.base}/Ticket", headers=self._h(), json={"input": {
            "name":              f"Mantenimiento Preventivo: {nombre}",
            "content":           f"Mantenimiento preventivo programado.\nEquipo: {nombre}",
            "itilcategories_id": self.category_id,
            "type": 1, "status": 1,
            "time_to_resolve":   f"{fecha_iso} 17:00:00",
        }})
        r.raise_for_status()
        return r.json().get("id")

    def link_computer(self, ticket_id: int, computer_id):
        _requests.post(f"{self.base}/Item_Ticket", headers=self._h(), json={"input": {
            "tickets_id": ticket_id,
            "itemtype":   "Computer",
            "items_id":   computer_id,
        }})

    def close_ticket(self, ticket_id: int, resolucion: str) -> None:
        """Cierra un ticket (status=6) y escribe la solución."""
        _requests.put(f"{self.base}/Ticket/{ticket_id}", headers=self._h(), json={"input": {
            "status":   6,
            "solution": resolucion,
        }})
        # Intenta agregar ITILSolution separado (algunos GLPI lo requieren)
        try:
            _requests.post(f"{self.base}/ITILSolution", headers=self._h(), json={"input": {
                "itemtype":  "Ticket",
                "items_id":  ticket_id,
                "content":   resolucion,
                "status":    2,  # accepted
            }})
        except Exception:
            pass

    # Nombre del itemtype del plugin Additional Fields (se deduce de la tabla)
    _PF_ITEMTYPE = "PluginFieldsComputerfechadeultimomantenimiento"
    _PF_FIELD    = "fechafield"

    def update_computer_fecha(self, computer_id, fecha_iso: str) -> None:
        """
        Actualiza la fecha de último mantenimiento en el campo del plugin
        Additional Fields.  La tabla es:
          glpi_plugin_fields_computerfechadeultimomantenimientos
        El endpoint REST es:
          PluginFieldsComputerfechadeultimomantenimiento
        """
        endpoint = self._PF_ITEMTYPE

        # 1. Buscar el registro existente para este computer
        r = _requests.get(f"{self.base}/{endpoint}", timeout=15, headers=self._h(), params={
            "searchText[items_id]": str(computer_id),
            "range": "0-1",
        })

        registro_id = None
        if r.status_code in (200, 206):
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                # Filtrar por items_id exacto (la búsqueda puede devolver parciales)
                for rec in data:
                    if str(rec.get("items_id")) == str(computer_id):
                        registro_id = rec.get("id")
                        break

        if registro_id:
            # 2a. Actualizar registro existente
            r2 = _requests.put(
                f"{self.base}/{endpoint}/{registro_id}",
                headers=self._h(),
                json={"input": {self._PF_FIELD: fecha_iso}},
            )
            r2.raise_for_status()
            log.info(f"Additional Fields: registro {registro_id} actualizado → {fecha_iso}")
        else:
            # 2b. Crear nuevo registro (el equipo aún no tenía fecha)
            r2 = _requests.post(
                f"{self.base}/{endpoint}",
                headers=self._h(),
                json={"input": {
                    "items_id":                      computer_id,
                    "itemtype":                      "Computer",
                    "plugin_fields_containers_id":   5,
                    self._PF_FIELD:                  fecha_iso,
                }},
            )
            r2.raise_for_status()
            log.info(f"Additional Fields: nuevo registro creado para Computer {computer_id} → {fecha_iso}")

    def find_computer_by_name(self, nombre: str):
        """Busca el ID de un Computer por nombre exacto."""
        r = _requests.get(f"{self.base}/Computer", timeout=20, headers=self._h(), params={
            "searchText[name]": nombre,
            "forcedisplay[0]": "1",
            "forcedisplay[1]": "2",
            "range": "0-5",
            "is_deleted": "0",
        })
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
        return self._get_all("Ticket", {
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
        })


# ══════════════════════════════════════════════════════════════════
# Outlook Client
# ══════════════════════════════════════════════════════════════════
class OutlookClient:
    def __init__(self, cfg: dict):
        self.client_id     = cfg.get("azure_client_id", "")
        self.client_secret = cfg.get("azure_client_secret", "")
        self.tenant_id     = cfg.get("azure_tenant_id", "")
        self.calendar_id   = cfg.get("outlook_calendar_id", "")
        self.user_upn      = cfg.get("outlook_user_upn", "")
        self.notify_emails = [
            e.strip() for e in cfg.get("notify_emails", "").split(",")
            if e.strip()
        ]
        self.token = None

    def _graph_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"}

    def _user_path(self) -> str:
        """Devuelve 'users/{upn}' o 'me' según config.
        Para app-only tokens (client_credentials) SIEMPRE se debe usar users/{upn}.
        """
        if self.user_upn and self.user_upn.lower() != "me":
            return f"users/{self.user_upn}"
        return "me"

    def authenticate(self):
        if not ConfidentialClientApplication:
            raise RuntimeError("Instala msal: pip install msal")
        if not self.client_id:
            raise RuntimeError("Falta azure_client_id en la configuración.")
        if not self.client_secret:
            raise RuntimeError("Falta azure_client_secret en la configuración.")
        if not self.tenant_id:
            raise RuntimeError("Falta azure_tenant_id en la configuración.")
        if not self.user_upn or self.user_upn.lower() == "me":
            raise RuntimeError(
                "Con tokens de aplicación (client_credentials) debes indicar el UPN/email "
                "del usuario en 'UPN del buzón' (campo outlook_user_upn). "
                "Ejemplo: usuario@sicolsa.com"
            )

        msal_app = ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )
        result = msal_app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise RuntimeError(
                f"Autenticación Azure fallida: {result.get('error_description', result.get('error', 'desconocido'))}"
            )
        self.token = result["access_token"]
        log.info("Outlook: token obtenido correctamente")

    def create_event(self, subject: str, inicio_iso: str, fin_iso: str,
                     attendees: list[str] | None = None) -> str:
        """
        Crea un evento en el calendario del usuario (user_upn).
        Si calendar_id está vacío usa el calendario principal (/calendar/events).
        attendees: lista de emails a invitar como asistentes.
        """
        base = f"https://graph.microsoft.com/v1.0/{self._user_path()}"
        url = (f"{base}/calendars/{self.calendar_id}/events"
               if self.calendar_id else f"{base}/calendar/events")

        body: dict = {
            "subject": subject,
            "start":   {"dateTime": inicio_iso, "timeZone": "America/Bogota"},
            "end":     {"dateTime": fin_iso,    "timeZone": "America/Bogota"},
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 30,
        }

        # Agregar asistentes si se especificaron
        all_attendees = list(set((attendees or []) + self.notify_emails))
        if all_attendees:
            body["attendees"] = [
                {"emailAddress": {"address": email}, "type": "required"}
                for email in all_attendees
                if email
            ]

        r = _requests.post(url, headers=self._graph_headers(), json=body)
        if not r.ok:
            log.error(f"Outlook create_event error {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
        log.info(f"Outlook: evento creado '{subject}'")
        return r.json().get("id")

    def send_email(self, destinatarios: list[str], subject: str,
                   body_html: str) -> None:
        """
        Envía un correo desde el buzón user_upn usando Graph API sendMail.
        Requiere permiso: Mail.Send (application).
        """
        if not destinatarios:
            return
        url = f"https://graph.microsoft.com/v1.0/{self._user_path()}/sendMail"
        payload = {
            "message": {
                "subject": subject,
                "body":    {"contentType": "HTML", "content": body_html},
                "toRecipients": [
                    {"emailAddress": {"address": e}} for e in destinatarios if e
                ],
            },
            "saveToSentItems": True,
        }
        r = _requests.post(url, headers=self._graph_headers(), json=payload)
        if not r.ok:
            log.error(f"Outlook send_email error {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
        log.info(f"Correo enviado a {destinatarios} — '{subject}'")

    def delete_event(self, event_id: str) -> None:
        """Elimina un evento por ID del calendario configurado."""
        if not event_id:
            raise ValueError("event_id vacío")
        base = f"https://graph.microsoft.com/v1.0/{self._user_path()}"
        url = (f"{base}/calendars/{self.calendar_id}/events/{event_id}"
               if self.calendar_id else f"{base}/events/{event_id}")
        r = _requests.delete(url, headers=self._graph_headers())
        if not r.ok:
            log.error(f"Outlook delete_event error {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
        log.info(f"Outlook: evento eliminado '{event_id}'")


# ══════════════════════════════════════════════════════════════════
# FastAPI app
# ══════════════════════════════════════════════════════════════════
app = FastAPI(title="Mantenimientos Preventivos — Sicolsa", version="2.0.0")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Convierte cualquier excepción no capturada en JSON legible."""
    # Extraer mensaje amigable de errores HTTP de requests
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
        msg = f"No se pudo conectar al servidor. Verifica la URL y la red."
    elif _requests and isinstance(exc, _requests.exceptions.Timeout):
        msg = f"Tiempo de espera agotado al conectar con el servidor."

    log.error(f"Error no capturado en {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": msg})


# Servir archivos estáticos
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ── Schemas ──────────────────────────────────────────────────────
class ConfigIn(BaseModel):
    glpi_url:             str
    glpi_app_token:       str
    glpi_user_token:      str
    glpi_category_id:     str = "22"
    glpi_field_id:        str = "76670"
    azure_client_id:      str = ""
    azure_client_secret:  str = ""
    azure_tenant_id:      str = ""
    outlook_calendar_id:  str = ""
    outlook_user_upn:     str = ""   # email/UPN del buzón que crea los eventos
    notify_emails:        str = ""   # emails separados por coma para notificar


class EquipoIn(BaseModel):
    id:             object
    nombre:         str
    fecha_limite:   str          # ISO date YYYY-MM-DD
    hora_inicio:    str = "08:00"
    incluido:       bool = True
    destinatarios:  str = ""     # emails separados por coma, específicos de este equipo


class ConfirmarIn(BaseModel):
    equipos:     list[EquipoIn]
    modo_prueba: bool = True


class InventoryMovimientoIn(BaseModel):
    asset_id:          str
    asset_nombre:      str
    tipo:              str   # asignacion | reasignacion | baja | desactivacion | reactivacion | observacion
    usuario_anterior:  str = ""
    usuario_nuevo:     str = ""
    estado_nuevo:      str = ""
    motivo:            str = ""
    responsable:       str = ""
    ticket_id:         str = ""
    fecha:             str = ""   # YYYY-MM-DD opcional
    modo_prueba:       bool = True


# Campos que contienen secretos — nunca se devuelven en GET, y en POST
# solo se sobreescriben si el usuario envió un valor no vacío.
_SECRET_FIELDS = {"glpi_app_token", "glpi_user_token", "azure_client_secret"}
_PLACEHOLDER   = "__saved__"   # indica "ya tiene valor, no cambiar"


# ── Endpoints de configuración ───────────────────────────────────
@app.get("/api/config")
def get_config():
    cfg = load_json(CONFIG_PATH)
    result = {}
    for k, v in cfg.items():
        if k in _SECRET_FIELDS:
            # Si tiene valor guardado devuelve el placeholder; si está vacío, vacío
            result[k] = _PLACEHOLDER if v else ""
        else:
            result[k] = v
    return result


@app.post("/api/config")
def post_config(data: ConfigIn):
    current = load_json(CONFIG_PATH, {})
    new_cfg = data.model_dump()

    # Para campos secretos: si el frontend envió el placeholder o vacío,
    # conservar el valor que ya estaba guardado.
    for field in _SECRET_FIELDS:
        incoming = new_cfg.get(field, "")
        if incoming == _PLACEHOLDER or incoming == "":
            new_cfg[field] = current.get(field, "")

    save_json(CONFIG_PATH, new_cfg)
    log.info("Config actualizada")
    return {"ok": True}


# ── Endpoint: cargar equipos ─────────────────────────────────────
def _glpi_http_error(exc: Exception, accion: str = "conectar con GLPI") -> None:
    """Convierte un error HTTP de requests en HTTPException con mensaje legible."""
    if _requests and isinstance(exc, _requests.exceptions.HTTPError):
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


@app.get("/api/cargar")
def cargar_equipos(modo_prueba: bool = True):
    """
    Retorna candidatos para el mes actual, tickets ya creados
    y tickets del mes anterior.
    """
    if modo_prueba:
        return _datos_prueba()

    cfg = load_json(CONFIG_PATH)
    if not cfg.get("glpi_url"):
        raise HTTPException(400, "Configura la URL de GLPI primero.")
    if _requests is None:
        raise HTTPException(500, "Instala requests: pip install requests")

    g = GLPIClient(cfg)
    try:
        log.info("Iniciando sesión en GLPI")
        try:
            g.login()
        except Exception as ex:
            _glpi_http_error(ex, "iniciar sesión en GLPI")

        computers = g.get_computers()
        if not computers:
            raise HTTPException(502, "GLPI no devolvió equipos. Verifica el App-Token y User-Token.")

        log.info(f"Computadores obtenidos: {len(computers)}")
        candidatos, total, cuota, ya_tienen, tickets_mes = \
            g.select_candidates(computers)

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

    return {
        "total":           total,
        "cuota":           cuota,
        "ya_tienen":       ya_tienen,
        "candidatos":      candidatos,
        "tickets_mes":     tickets_mes,
        "tickets_ant":     _procesar_tickets_ant(tickets_ant, state_ant),
        "mes_actual_done": _mes_actual_done(),
    }


def _datos_prueba():
    candidatos = [
        {"id": 9001, "nombre": "PC-PRUEBA-01", "ultima_fecha": "2024-01-01"},
        {"id": 9002, "nombre": "PC-PRUEBA-02", "ultima_fecha": "2024-02-01"},
        {"id": 9003, "nombre": "PC-PRUEBA-03", "ultima_fecha": "2024-03-01"},
        {"id": 9004, "nombre": "PC-PRUEBA-04", "ultima_fecha": "2024-04-01"},
        {"id": 9005, "nombre": "PC-PRUEBA-05", "ultima_fecha": "2024-05-01"},
    ]
    candidatos = asignar_fechas_habiles(candidatos)
    tickets_ant_raw = [
        {"1": "Mantenimiento Preventivo: ESPECTOMETRO",    "12": 6},
        {"1": "Mantenimiento Preventivo: SADMINISTRACION", "12": 1},
        {"1": "Mantenimiento Preventivo: SALMACEN",        "12": 5},
    ]
    tickets_ant = _procesar_tickets_ant(tickets_ant_raw, [])
    return {
        "total": 60, "cuota": 5, "ya_tienen": 0,
        "candidatos":  candidatos,
        "tickets_mes": [],
        "tickets_ant": tickets_ant,
        "mes_actual_done": _mes_actual_done(),
    }


def _procesar_tickets_ant(glpi_list: list, state_list: list) -> dict:
    todos = {}
    for t in state_list:
        todos[t["nombre"]] = {
            "nombre":      t["nombre"],
            "fecha":       t.get("fecha", ""),
            "ticket_id":   t.get("ticket_id"),
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
                "nombre": nombre, "fecha": "",
                "ticket_id": None, "status_glpi": s,
            }
    completados = [v for v in todos.values() if v.get("status_glpi") in [5, 6]]
    pendientes  = [v for v in todos.values() if v not in completados]
    return {
        "items":       list(todos.values()),
        "completados": len(completados),
        "pendientes":  len(pendientes),
    }


def _mes_actual_done() -> bool:
    state = load_json(STATE_PATH, {})
    return bool(state.get(mes_key(), {}).get("completado"))


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


def _fmt_asset(comp: dict, local_asset: dict | None = None):
    local_asset = local_asset or {}
    asset_id = str(comp.get("id") or comp.get("2") or local_asset.get("asset_id") or "")
    nombre = str(comp.get("name") or comp.get("1") or local_asset.get("nombre") or "Sin nombre")
    usuario_glpi = str(comp.get("users_id") or comp.get("70") or "").strip()
    estado_glpi = str(comp.get("states_id") or comp.get("31") or "").strip()
    serial = str(comp.get("serial") or comp.get("10") or "").strip()
    ultima = str(comp.get("date_mod") or comp.get("19") or local_asset.get("ultima_actualizacion") or "")
    return {
        "asset_id": asset_id,
        "nombre": nombre,
        "serial": serial,
        "usuario_actual": local_asset.get("usuario_actual") or usuario_glpi,
        "estado_actual": local_asset.get("estado_actual") or estado_glpi,
        "baja": bool(local_asset.get("baja", False)),
        "ultima_actualizacion": local_asset.get("ultima_actualizacion") or ultima,
    }


# ── Endpoint: confirmar (crear tickets y eventos) ────────────────
@app.post("/api/confirmar")
def confirmar(data: ConfirmarIn):
    incluidos = [e for e in data.equipos if e.incluido]
    if not incluidos:
        raise HTTPException(400, "Selecciona al menos un equipo.")

    cfg = load_json(CONFIG_PATH)

    creados   = []
    errores   = []

    if data.modo_prueba:
        import time
        for i, eq in enumerate(incluidos):
            time.sleep(0.1)
            d = date.fromisoformat(eq.fecha_limite)
            creados.append({
                "nombre":    eq.nombre,
                "fecha":     fmt_fecha_larga(d),
                "ticket_id": 90000 + i,
                "evento_id": f"fake-event-{i}",
                "correo_ok": False,
            })
        log.info(f"[PRUEBA] {len(creados)} tickets simulados")
    else:
        if _requests is None:
            raise HTTPException(500, "Instala requests")

        glpi    = GLPIClient(cfg)
        outlook = OutlookClient(cfg)

        log.info("Conectando GLPI + Outlook para confirmar")
        glpi.login()
        outlook.authenticate()

        try:
            for eq in incluidos:
                try:
                    d     = date.fromisoformat(eq.fecha_limite)
                    h, mn = eq.hora_inicio.split(":")
                    h_fin = str((int(h) + 1) % 24).zfill(2)
                    inicio_iso = f"{eq.fecha_limite}T{h.zfill(2)}:{mn}:00"
                    fin_iso    = f"{eq.fecha_limite}T{h_fin}:{mn}:00"
                    fecha_larga = fmt_fecha_larga(d)

                    # Crear ticket en GLPI
                    if not glpi.ticket_exists(eq.nombre):
                        ticket_id = glpi.create_ticket(eq.nombre, eq.fecha_limite)
                        glpi.link_computer(ticket_id, eq.id)
                    else:
                        ticket_id = None

                    # Destinatarios: globales (config) + específicos del equipo
                    dest_eq = [
                        e.strip() for e in eq.destinatarios.split(",")
                        if e.strip()
                    ] if eq.destinatarios else []
                    todos_destinatarios = list(set(outlook.notify_emails + dest_eq))

                    # Crear evento en Outlook
                    evento_id = outlook.create_event(
                        f"Mantenimiento Preventivo: {eq.nombre}",
                        inicio_iso, fin_iso,
                        attendees=todos_destinatarios,
                    )

                    # Enviar correo de notificación
                    correo_ok = False
                    if todos_destinatarios:
                        try:
                            html = _build_email_html(
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
                        "nombre":    eq.nombre,
                        "fecha":     fecha_larga,
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

    # Guardar estado
    state = load_json(STATE_PATH, {})
    key   = mes_key()
    state[key] = {
        "completado":       len(errores) == 0,
        "equipos":          creados,
        "fecha_ejecucion":  datetime.now().isoformat(),
        "modo_prueba":      data.modo_prueba,
    }
    save_json(STATE_PATH, state)

    return {
        "creados":  creados,
        "errores":  errores,
        "ok":       len(errores) == 0,
    }


# ── Checklist de mantenimiento preventivo ────────────────────────
CHECKLIST_ITEMS = [
    {"id": "c01", "categoria": "Limpieza física",    "texto": "Limpiar polvo de ventiladores, disipador de CPU y rejillas de ventilación con aire comprimido"},
    {"id": "c02", "categoria": "Limpieza física",    "texto": "Limpiar el interior del gabinete (polvo acumulado en tarjetas, cables y ranuras)"},
    {"id": "c03", "categoria": "Limpieza física",    "texto": "Limpiar teclado, mouse y pantalla con paño antiestático"},
    {"id": "c04", "categoria": "Hardware",           "texto": "Verificar que todos los cables internos (SATA, alimentación, RAM) estén bien conectados"},
    {"id": "c05", "categoria": "Hardware",           "texto": "Revisar estado físico de la RAM (sin golpes ni quemaduras); resentar si es necesario"},
    {"id": "c06", "categoria": "Hardware",           "texto": "Verificar temperatura de CPU y GPU en reposo (debe ser < 55 °C)"},
    {"id": "c07", "categoria": "Hardware",           "texto": "Comprobar funcionamiento de puertos USB, audio y red"},
    {"id": "c08", "categoria": "Almacenamiento",     "texto": "Ejecutar análisis SMART del disco duro / SSD (sin sectores defectuosos críticos)"},
    {"id": "c09", "categoria": "Almacenamiento",     "texto": "Verificar espacio libre en disco C: (mínimo 15 % libre)"},
    {"id": "c10", "categoria": "Sistema operativo",  "texto": "Instalar actualizaciones de Windows pendientes (Windows Update)"},
    {"id": "c11", "categoria": "Sistema operativo",  "texto": "Verificar que el antivirus esté activo y con definiciones al día"},
    {"id": "c12", "categoria": "Sistema operativo",  "texto": "Ejecutar análisis rápido de antivirus"},
    {"id": "c13", "categoria": "Sistema operativo",  "texto": "Eliminar archivos temporales y limpiar papelera de reciclaje"},
    {"id": "c14", "categoria": "Sistema operativo",  "texto": "Revisar programas de inicio y deshabilitar los innecesarios"},
    {"id": "c15", "categoria": "Red y conectividad", "texto": "Confirmar conectividad de red (ping al gateway y a Internet)"},
    {"id": "c16", "categoria": "Red y conectividad", "texto": "Verificar que la IP / DNS estén configurados correctamente según política de IT"},
    {"id": "c17", "categoria": "Seguridad",          "texto": "Confirmar que el equipo tiene contraseña de inicio de sesión activa"},
    {"id": "c18", "categoria": "Seguridad",          "texto": "Verificar que el cifrado de disco (BitLocker u otro) esté habilitado si aplica"},
    {"id": "c19", "categoria": "Respaldo",           "texto": "Confirmar que el último respaldo de datos del usuario se realizó correctamente"},
    {"id": "c20", "categoria": "Cierre",             "texto": "Documentar observaciones encontradas y acciones realizadas (campo 'Notas' al final)"},
]

CHECKLIST_PATH = BASE_DIR / "checklist.json"


def _load_checklist() -> list:
    """Devuelve el checklist personalizado si existe, si no el predeterminado."""
    try:
        data = load_json(CHECKLIST_PATH, None)
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception:
        pass
    return CHECKLIST_ITEMS


class ChecklistItemIn(BaseModel):
    id:        str
    categoria: str
    texto:     str


@app.get("/api/checklist")
def get_checklist():
    return _load_checklist()


@app.post("/api/checklist")
def save_checklist(items: list[ChecklistItemIn]):
    """Guarda el checklist personalizado en checklist.json."""
    if not items:
        raise HTTPException(400, "El checklist no puede estar vacío.")
    data = [i.model_dump() for i in items]
    save_json(CHECKLIST_PATH, data)
    log.info(f"Checklist personalizado guardado: {len(data)} items")
    return {"ok": True, "total": len(data)}


@app.post("/api/checklist/reset")
def reset_checklist():
    """Elimina el checklist personalizado y vuelve al predeterminado."""
    delete_json(CHECKLIST_PATH)
    log.info("Checklist restaurado al predeterminado")
    return {"ok": True, "items": CHECKLIST_ITEMS}


# ── Schemas para completar ────────────────────────────────────────
class CompletarIn(BaseModel):
    ticket_id:   int
    computer_id: object          # puede ser int o str
    nombre:      str
    items_ok:    list[str]       # IDs de ítems marcados
    notas:       str = ""
    modo_prueba: bool = True


@app.post("/api/completar")
def completar_mantenimiento(data: CompletarIn):
    """
    Marca el mantenimiento como completado:
    - Cierra el ticket en GLPI (status 6)
    - Actualiza la fecha de último mantenimiento en el equipo
    """
    hoy      = date.today().isoformat()
    checklist = _load_checklist()
    total_ok = len(data.items_ok)
    total_ch = len(checklist)

    # Construir texto de solución con checklist
    lineas = [f"Mantenimiento preventivo completado el {hoy}.",
              f"Items verificados: {total_ok}/{total_ch}",
              ""]
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

    if data.modo_prueba:
        log.info(f"[PRUEBA] Completar mantenimiento '{data.nombre}' ticket #{data.ticket_id}")
        return {
            "ok":             True,
            "ticket_cerrado": True,
            "fecha_actualizada": hoy,
            "modo_prueba":    True,
        }

    cfg = load_json(CONFIG_PATH)
    if _requests is None:
        raise HTTPException(500, "Instala requests")

    g = GLPIClient(cfg)
    try:
        g.login()

        # 1. Cerrar ticket
        g.close_ticket(int(data.ticket_id), resolucion)
        log.info(f"Ticket #{data.ticket_id} cerrado — {data.nombre}")

        # 2. Resolver computer_id si no vino
        cid = data.computer_id
        if not cid:
            cid = g.find_computer_by_name(data.nombre)

        # 3. Actualizar campo fecha
        fecha_ok = False
        if cid:
            try:
                g.update_computer_fecha(cid, hoy)
                log.info(f"Fecha de mant. actualizada en Computer #{cid} → {hoy}")
                fecha_ok = True
            except Exception as ex:
                log.warning(f"No se pudo actualizar fecha del equipo: {ex}")

    finally:
        g.logout()

    # Actualizar state.json local
    state = load_json(STATE_PATH, {})
    key   = mes_key()
    equipos = state.get(key, {}).get("equipos", [])
    for eq in equipos:
        if eq.get("nombre") == data.nombre:
            eq["completado"] = True
            eq["fecha_completado"] = hoy
            break
    if key in state:
        state[key]["equipos"] = equipos
        save_json(STATE_PATH, state)

    return {
        "ok":               True,
        "ticket_cerrado":   True,
        "fecha_actualizada": hoy if fecha_ok else None,
        "modo_prueba":      False,
    }


# ── Endpoint: estado del mes ──────────────────────────────────────
@app.get("/api/estado")
def get_estado():
    state = load_json(STATE_PATH, {})
    key   = mes_key()
    hoy   = date.today()
    return {
        "mes_key":   key,
        "mes_label": f"{MESES_ES[hoy.month]} {hoy.year}",
        "completado": bool(state.get(key, {}).get("completado")),
        "equipos":    state.get(key, {}).get("equipos", []),
    }


# ── Inventario de activos ─────────────────────────────────────────
@app.get("/api/inventario/activos")
def get_inventario_activos(modo_prueba: bool = True):
    inv = _load_inventory()
    activos_local = inv.get("activos", {})

    if modo_prueba:
        base = [
            {"id": "9001", "name": "PC-PRUEBA-01", "serial": "SN-PRUEBA-01"},
            {"id": "9002", "name": "PC-PRUEBA-02", "serial": "SN-PRUEBA-02"},
            {"id": "9003", "name": "PC-PRUEBA-03", "serial": "SN-PRUEBA-03"},
        ]
        activos = [_fmt_asset(c, activos_local.get(str(c["id"]), {})) for c in base]
    else:
        cfg = load_json(CONFIG_PATH)
        if not cfg.get("glpi_url"):
            raise HTTPException(400, "Configura la URL de GLPI primero.")
        if _requests is None:
            raise HTTPException(500, "Instala requests: pip install requests")

        g = GLPIClient(cfg)
        try:
            g.login()
            raw = g._get_all("Computer", {
                "is_deleted": "0",
                "is_template": "0",
            })
        except Exception as ex:
            _glpi_http_error(ex, "cargar activos de inventario")
        finally:
            g.logout()

        activos = []
        for c in raw:
            asset_id = str(c.get("id") or c.get("2") or "")
            activos.append(_fmt_asset(c, activos_local.get(asset_id, {})))

    activos.sort(key=lambda a: (a.get("baja", False), a.get("nombre", "")))
    return {"items": activos, "total": len(activos)}


@app.get("/api/inventario/usuarios")
def get_inventario_usuarios(modo_prueba: bool = True):
    if modo_prueba:
        items = [
            {"id": "60", "nombre": "j.perez"},
            {"id": "72", "nombre": "m.garcia"},
            {"id": "81", "nombre": "a.lopez"},
        ]
        return {"items": items, "total": len(items)}

    cfg = load_json(CONFIG_PATH)
    if not cfg.get("glpi_url"):
        raise HTTPException(400, "Configura la URL de GLPI primero.")
    if _requests is None:
        raise HTTPException(500, "Instala requests: pip install requests")

    g = GLPIClient(cfg)
    try:
        g.login()
        raw = g._get_all("User", {
            "is_deleted": "0",
            "is_active": "1",
            "forcedisplay[0]": "1",
            "forcedisplay[1]": "2",
            "forcedisplay[2]": "34",
        })
    except Exception as ex:
        _glpi_http_error(ex, "cargar usuarios de GLPI")
    finally:
        g.logout()

    items = []
    for u in raw:
        uid = str(u.get("2") or u.get("id") or "").strip()
        nombre = str(u.get("1") or u.get("name") or "").strip()
        if not uid or not nombre:
            continue
        display = str(u.get("34") or "").strip()
        items.append({
            "id": uid,
            "nombre": display or nombre,
        })

    uniq = {}
    for u in items:
        uniq[u["id"]] = u
    sorted_items = sorted(uniq.values(), key=lambda x: x["nombre"].lower())
    return {"items": sorted_items, "total": len(sorted_items)}


@app.get("/api/inventario/historial")
def get_inventario_historial(asset_id: Optional[str] = None):
    inv = _load_inventory()
    movs = inv.get("movimientos", [])
    if asset_id:
        movs = [m for m in movs if str(m.get("asset_id")) == str(asset_id)]
    movs.sort(key=lambda m: (m.get("fecha", ""), m.get("created_at", "")), reverse=True)
    return {"items": movs, "total": len(movs)}


@app.post("/api/inventario/movimiento")
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
        cfg = load_json(CONFIG_PATH)
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

        g = GLPIClient(cfg)
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
                        "Crea ese estado o selecciona uno existente."
                    )
            g.update_computer_fields(
                computer_id=asset_id,
                users_id=usuario_id,
                states_id=state_id,
            )

            # Trazabilidad del movimiento en el comentario del activo en GLPI.
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
            _glpi_http_error(ex, "actualizar el activo en GLPI")
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
    actual = activos.get(asset_id, {
        "asset_id": asset_id,
        "nombre": data.asset_nombre.strip(),
        "usuario_actual": "",
        "estado_actual": "",
        "baja": False,
        "ultima_actualizacion": created_at,
    })
    actual["nombre"] = data.asset_nombre.strip()
    actual["ultima_actualizacion"] = created_at

    if data.tipo in {"asignacion", "reasignacion"}:
        actual["usuario_actual"] = data.usuario_nuevo.strip()
    if data.tipo == "baja":
        actual["baja"] = True
        actual["estado_actual"] = data.estado_nuevo.strip() or "Baja"
    elif data.tipo == "desactivacion":
        # Equipo fuera de uso, pero NO dado de baja.
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


# ── Helper: plantilla email HTML ─────────────────────────────────
def _build_email_html(nombre: str, fecha_larga: str, hora_inicio: str,
                      ticket_id, glpi_url: str) -> str:
    hora_parts = hora_inicio.split(":")
    h_fin = str((int(hora_parts[0]) + 1) % 24).zfill(2)
    hora_rango = f"{hora_inicio} – {h_fin}:{hora_parts[1] if len(hora_parts) > 1 else '00'}"
    ticket_link = ""
    if ticket_id and glpi_url:
        url = f"{glpi_url}/front/ticket.form.php?id={ticket_id}"
        ticket_link = f'<p style="margin:8px 0"><a href="{url}" style="color:#00d4ff">Ver ticket #{ticket_id} en GLPI →</a></p>'

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 0">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#111827;border-radius:12px;overflow:hidden;border:1px solid #1e2d45">
        <!-- Header -->
        <tr>
          <td style="background:#0a0e1a;padding:24px 32px;border-bottom:1px solid #1e2d45">
            <p style="margin:0;font-size:11px;color:#00d4ff;letter-spacing:.08em;font-family:Consolas,monospace">
              — SICOLSA — IT
            </p>
            <h1 style="margin:6px 0 0;font-size:20px;color:#ffffff;font-weight:700">
              🖥️ Mantenimiento Preventivo Programado
            </h1>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:28px 32px">
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#1a2235;border-radius:8px;border:1px solid #1e2d45">
              <tr>
                <td style="padding:20px 24px">
                  <p style="margin:0 0 4px;font-size:10px;color:#64748b;font-family:Consolas,monospace;letter-spacing:.06em">EQUIPO</p>
                  <p style="margin:0;font-size:22px;font-weight:700;color:#ffffff">{nombre}</p>
                </td>
              </tr>
              <tr><td style="height:1px;background:#1e2d45"></td></tr>
              <tr>
                <td style="padding:16px 24px">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td width="50%" style="padding-right:12px">
                        <p style="margin:0 0 4px;font-size:10px;color:#64748b;font-family:Consolas,monospace">FECHA</p>
                        <p style="margin:0;font-size:14px;color:#e2e8f0;font-weight:600">{fecha_larga.capitalize()}</p>
                      </td>
                      <td width="50%">
                        <p style="margin:0 0 4px;font-size:10px;color:#64748b;font-family:Consolas,monospace">HORA</p>
                        <p style="margin:0;font-size:14px;color:#e2e8f0;font-weight:600">{hora_rango}</p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
              {f'<tr><td style="height:1px;background:#1e2d45"></td></tr><tr><td style="padding:14px 24px">{ticket_link}</td></tr>' if ticket_link else ""}
            </table>
            <p style="margin:20px 0 0;font-size:13px;color:#64748b;line-height:1.6">
              Este es un aviso automático generado por la app de
              <strong style="color:#e2e8f0">Mantenimientos Preventivos — Sicolsa</strong>.
              El evento ya fue creado en el calendario de Outlook.
            </p>
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="background:#0a0e1a;padding:16px 32px;border-top:1px solid #1e2d45">
            <p style="margin:0;font-size:11px;color:#64748b;font-family:Consolas,monospace">
              Sicolsa IT · Mantenimientos Preventivos v2
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ── Endpoint: test de conexión Outlook ────────────────────────────
@app.get("/api/test-outlook")
def test_outlook():
    """
    Verifica las credenciales Azure/Outlook en varios pasos y devuelve
    un diagnóstico detallado para saber exactamente qué falla.
    """
    cfg = load_json(CONFIG_PATH)

    faltantes = []
    if not cfg.get("azure_client_id"):     faltantes.append("azure_client_id")
    if not cfg.get("azure_client_secret"): faltantes.append("azure_client_secret")
    if not cfg.get("azure_tenant_id"):     faltantes.append("azure_tenant_id")
    if not cfg.get("outlook_user_upn"):    faltantes.append("outlook_user_upn (email del buzón)")
    if faltantes:
        return {"ok": False, "step": "config",
                "error": f"Faltan campos: {', '.join(faltantes)}"}

    # ── Paso 1: obtener token ─────────────────────────────────────
    try:
        outlook = OutlookClient(cfg)
        outlook.authenticate()
    except Exception as ex:
        return {"ok": False, "step": "auth",
                "error": f"Error obteniendo token Azure: {ex}"}

    user_path = outlook._user_path()
    h = outlook._graph_headers()

    # ── Paso 2: listar calendarios disponibles (no requiere leer /users/{upn}) ──
    r_cals = _requests.get(
        f"https://graph.microsoft.com/v1.0/{user_path}/calendars",
        headers=h, timeout=15)

    if not r_cals.ok:
        code = r_cals.status_code
        if code == 403:
            return {
                "ok": False, "step": "calendar_access",
                "error": (
                    f"Token OK, pero Graph denegó acceso a calendarios de {cfg.get('outlook_user_upn')} (403). "
                    "Verifica ApplicationAccessPolicy en Exchange Online para esta app y buzón."
                ),
            }
        return {"ok": False, "step": "calendar_access",
                "error": f"No se pudo listar calendarios ({code}): {r_cals.text[:200]}"}

    calendarios_disponibles = []
    for c in r_cals.json().get("value", []):
        calendarios_disponibles.append({"id": c.get("id"), "name": c.get("name")})

    # ── Paso 4: verificar el calendario configurado ───────────────
    cal_id = cfg.get("outlook_calendar_id", "").strip()
    cal_name = None
    cal_warning = None

    if cal_id:
        r_cal = _requests.get(
            f"https://graph.microsoft.com/v1.0/{user_path}/calendars/{cal_id}",
            headers=h, timeout=15)
        if r_cal.ok:
            cal_name = r_cal.json().get("name", "—")
        else:
            cal_warning = (
                f"El Calendar ID guardado no es accesible ({r_cal.status_code}). "
                "Usa uno de los calendarios disponibles listados abajo, "
                "o deja el campo Calendar ID vacío para usar el calendario principal."
            )
    else:
        # Sin calendar_id → usar el principal (siempre funciona)
        r_primary = _requests.get(
            f"https://graph.microsoft.com/v1.0/{user_path}/calendar",
            headers=h, timeout=15)
        if r_primary.ok:
            cal_name = r_primary.json().get("name", "Calendario principal")
        cal_warning = "No hay Calendar ID configurado — se usará el calendario principal."

    notify = cfg.get("notify_emails", "")
    return {
        "ok":                    True,
        "step":                  "all",
        "usuario":               cfg.get("outlook_user_upn"),
        "calendario":            cal_name or "—",
        "cal_warning":           cal_warning,
        "calendarios_disponibles": calendarios_disponibles,
        "notify_emails":         notify,
        "mensaje": (
            f"Token y buzón OK. Calendario: '{cal_name or '(principal)'}'. "
            + (cal_warning or "")
        ),
    }


@app.post("/api/test-outlook-event")
def test_outlook_event():
    """
    Crea un evento real corto y lo elimina inmediatamente para validar
    permisos end-to-end de escritura en el calendario.
    """
    cfg = load_json(CONFIG_PATH)

    faltantes = []
    if not cfg.get("azure_client_id"):     faltantes.append("azure_client_id")
    if not cfg.get("azure_client_secret"): faltantes.append("azure_client_secret")
    if not cfg.get("azure_tenant_id"):     faltantes.append("azure_tenant_id")
    if not cfg.get("outlook_user_upn"):    faltantes.append("outlook_user_upn (email del buzón)")
    if faltantes:
        return {"ok": False, "step": "config",
                "error": f"Faltan campos: {', '.join(faltantes)}"}

    event_id = None
    try:
        outlook = OutlookClient(cfg)
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


# ── Health check ──────────────────────────────────────────────────
@app.get("/api/health")
def health():
    cfg = load_json(CONFIG_PATH)
    return {
        "status":           "ok",
        "requests_ok":      _requests is not None,
        "msal_ok":          ConfidentialClientApplication is not None,
        "db_enabled":       DB_ENABLED,
        "db_backend":       "postgres" if DB_ENABLED else "json_files",
        "config_exists":    CONFIG_PATH.exists(),
        "glpi_url":         cfg.get("glpi_url", ""),
    }


# ── Arranque ─────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
