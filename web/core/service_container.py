from collections.abc import Callable
from typing import Any

from services.glpi import GLPIClient
from services.outlook import OutlookClient

ProviderFactory = Callable[[dict[str, Any]], Any]

_providers: dict[str, ProviderFactory] = {
    "glpi": lambda cfg: GLPIClient(cfg),
    "outlook": lambda cfg: OutlookClient(cfg),
}


def register_provider(name: str, factory: ProviderFactory) -> None:
    _providers[name] = factory


def resolve(name: str, cfg: dict[str, Any]) -> Any:
    factory = _providers.get(name)
    if factory is None:
        raise ValueError(f"Proveedor no registrado: {name}")
    return factory(cfg)


def resolve_glpi(cfg: dict[str, Any]) -> GLPIClient:
    return resolve("glpi", cfg)


def resolve_outlook(cfg: dict[str, Any]) -> OutlookClient:
    return resolve("outlook", cfg)
