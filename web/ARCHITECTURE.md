# Arquitectura modular (base para escalar)

Esta versión mueve la app a una base modular para poder escalar por implementaciones sin reescribir endpoints.

## Cambios clave

- `app_factory.py`: crea la instancia FastAPI y centraliza wiring global.
- `api/router_registry.py`: registra routers de forma declarativa.
- `core/service_container.py`: contenedor simple de proveedores (GLPI/Outlook).
- `main.py`: entrypoint mínimo.

## Cómo cambiar implementaciones

El contenedor permite reemplazar clientes concretos por otros:

```python
from core.service_container import register_provider

class MiGLPI:
    def __init__(self, cfg: dict):
        ...

register_provider("glpi", lambda cfg: MiGLPI(cfg))
```

Los routers ya no instancian directamente `GLPIClient`/`OutlookClient`; resuelven proveedores mediante el contenedor.

## Siguiente fase recomendada

1. Extraer casos de uso por dominio (`maintenance`, `inventory`, `renovation`).
2. Mover acceso a estado JSON a repositorios por puerto.
3. Añadir capa `adapters` (glpi, outlook, storage) con interfaces explícitas.
4. Separar procesos en servicios independientes detrás de un API gateway.
