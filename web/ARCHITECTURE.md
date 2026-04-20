# Arquitectura modular (base para escalar)

Esta versión mueve la app a una base modular para poder escalar por implementaciones sin reescribir endpoints.

## Cambios clave

- `app_factory.py`: crea la instancia FastAPI y centraliza wiring global.
- `api/router_registry.py`: registra routers de forma declarativa.
- `core/service_container.py`: contenedor simple de proveedores (GLPI/Outlook).
- `main.py`: entrypoint mínimo.
- `application/*_use_cases.py`: casos de uso por dominio (maintenance, inventory, renovation).
- `ports/repositories.py`: contratos de persistencia.
- `adapters/json_repositories.py`: implementación de repositorios JSON.

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

## Estado de fase 2 (implementado)

1. Casos de uso por dominio extraídos a capa `application`.
2. Persistencia JSON movida a repositorios adaptadores.
3. Routers simplificados para delegar negocio y mantener HTTP como capa delgada.

## Siguiente fase recomendada

1. Definir puertos explícitos para proveedores externos (GLPI/Outlook) y tipado más estricto.
2. Sustituir almacenamiento JSON por base de datos transaccional.
3. Separar dominios en servicios independientes detrás de un API gateway.
