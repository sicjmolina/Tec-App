import logging

from fastapi import APIRouter
from fastapi import HTTPException

from core.checklist_util import load_checklist
from core.constants import CHECKLIST_ITEMS
from core.jsonutil import save_json
from schemas import ChecklistItemIn
from settings import CHECKLIST_PATH

log = logging.getLogger("mant")

router = APIRouter(prefix="/api", tags=["checklist"])


@router.get("/checklist")
def get_checklist():
    return load_checklist()


@router.post("/checklist")
def save_checklist(items: list[ChecklistItemIn]):
    if not items:
        raise HTTPException(400, "El checklist no puede estar vacío.")
    data = [i.model_dump() for i in items]
    save_json(CHECKLIST_PATH, data)
    log.info(f"Checklist personalizado guardado: {len(data)} items")
    return {"ok": True, "total": len(data)}


@router.post("/checklist/reset")
def reset_checklist():
    if CHECKLIST_PATH.exists():
        CHECKLIST_PATH.unlink()
    log.info("Checklist restaurado al predeterminado")
    return {"ok": True, "items": CHECKLIST_ITEMS}
