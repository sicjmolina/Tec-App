from core.constants import CHECKLIST_ITEMS
from core.jsonutil import load_json
from settings import CHECKLIST_PATH


def load_checklist() -> list:
    if CHECKLIST_PATH.exists():
        try:
            data = load_json(CHECKLIST_PATH)
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass
    return CHECKLIST_ITEMS
