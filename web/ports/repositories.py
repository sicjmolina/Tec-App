from typing import Protocol


class MaintenanceStateRepository(Protocol):
    def load_state(self) -> dict:
        ...

    def save_state(self, state: dict) -> None:
        ...


class InventoryRepository(Protocol):
    def load_inventory(self) -> dict:
        ...

    def save_inventory(self, data: dict) -> None:
        ...
