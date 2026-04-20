import logging

from fastapi import APIRouter

from core.constants import PLACEHOLDER, SECRET_FIELDS
from core.jsonutil import load_json, save_json
from schemas import ConfigIn
from settings import CONFIG_PATH, get_merged_config

log = logging.getLogger("mant")

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
def get_config():
    cfg = get_merged_config()
    result = {}
    for k, v in cfg.items():
        if k in SECRET_FIELDS:
            result[k] = PLACEHOLDER if v else ""
        else:
            result[k] = v
    return result


@router.post("/config")
def post_config(data: ConfigIn):
    file_cfg = load_json(CONFIG_PATH, {})
    current_merged = get_merged_config()
    new_cfg = data.model_dump()

    for field in SECRET_FIELDS:
        incoming = new_cfg.get(field, "")
        if incoming == PLACEHOLDER or incoming == "":
            new_cfg[field] = current_merged.get(field, file_cfg.get(field, ""))

    save_json(CONFIG_PATH, new_cfg)
    log.info("Config actualizada")
    return {"ok": True}
