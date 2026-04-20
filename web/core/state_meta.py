"""Metadatos persistidos en state.json (p. ej. última sincronización GLPI)."""

from datetime import datetime

from core.constants import META_KEY
from core.jsonutil import load_json, save_json
from settings import STATE_PATH


def record_last_glpi_sync():
    state = load_json(STATE_PATH, {})
    meta = state.get(META_KEY) or {}
    meta["last_glpi_sync_at"] = datetime.now().isoformat()
    state[META_KEY] = meta
    save_json(STATE_PATH, state)


def get_last_glpi_sync_at() -> str | None:
    state = load_json(STATE_PATH, {})
    meta = state.get(META_KEY) or {}
    v = meta.get("last_glpi_sync_at")
    return str(v).strip() if v else None


def merge_meta_into_state(state: dict) -> dict:
    """Copia _meta del archivo actual para no perderlo al guardar otros campos."""
    prev = load_json(STATE_PATH, {})
    meta = prev.get(META_KEY)
    if meta is not None:
        state[META_KEY] = meta
    return state
