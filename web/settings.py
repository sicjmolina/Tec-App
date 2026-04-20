"""
Rutas de datos y fusión de configuración: config.json + variables de entorno.

Las variables de entorno tienen prioridad sobre el archivo (útil para secretos).
Cargar un .env en la raíz del proyecto (junto a config.json) con python-dotenv.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from core.jsonutil import load_json

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"
LOG_PATH = BASE_DIR / "mant.log"
INVENTORY_PATH = BASE_DIR / "inventory_history.json"
CHECKLIST_PATH = BASE_DIR / "checklist.json"

# .env junto a config.json (BASE_DIR), no dentro de web/
load_dotenv(BASE_DIR / ".env")

# (clave_config_json, variable_entorno)
_ENV_CONFIG_MAP = [
    ("glpi_url", "GLPI_URL"),
    ("glpi_app_token", "GLPI_APP_TOKEN"),
    ("glpi_user_token", "GLPI_USER_TOKEN"),
    ("glpi_category_id", "GLPI_CATEGORY_ID"),
    ("glpi_field_id", "GLPI_FIELD_ID"),
    ("azure_client_id", "AZURE_CLIENT_ID"),
    ("azure_client_secret", "AZURE_CLIENT_SECRET"),
    ("azure_tenant_id", "AZURE_TENANT_ID"),
    ("outlook_calendar_id", "OUTLOOK_CALENDAR_ID"),
    ("outlook_user_upn", "OUTLOOK_USER_UPN"),
    ("notify_emails", "NOTIFY_EMAILS"),
]


def get_merged_config() -> dict:
    """Mezcla config.json con variables de entorno (env pisa archivo)."""
    file_cfg = load_json(CONFIG_PATH, {})
    merged = dict(file_cfg)
    for key, env_name in _ENV_CONFIG_MAP:
        val = os.getenv(env_name)
        if val is not None and str(val).strip() != "":
            merged[key] = val.strip()
    return merged
