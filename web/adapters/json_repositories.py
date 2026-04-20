from core.jsonutil import load_json, save_json
from settings import INVENTORY_PATH, STATE_PATH


class JsonMaintenanceStateRepository:
    def load_state(self) -> dict:
        return load_json(STATE_PATH, {})

    def save_state(self, state: dict) -> None:
        save_json(STATE_PATH, state)


class JsonInventoryRepository:
    def load_inventory(self) -> dict:
        data = load_json(INVENTORY_PATH, {"movimientos": [], "activos": {}})
        if not isinstance(data, dict):
            return {"movimientos": [], "activos": {}}
        if "movimientos" not in data or not isinstance(data["movimientos"], list):
            data["movimientos"] = []
        if "activos" not in data or not isinstance(data["activos"], dict):
            data["activos"] = {}
        return data

    def save_inventory(self, data: dict) -> None:
        save_json(INVENTORY_PATH, data)
