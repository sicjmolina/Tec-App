from fastapi import FastAPI

from routers import checklist, config, inventory, maintenance, renovation


def include_api_routers(app: FastAPI) -> None:
    app.include_router(config.router)
    app.include_router(maintenance.router)
    app.include_router(checklist.router)
    app.include_router(inventory.router)
    app.include_router(renovation.router)
