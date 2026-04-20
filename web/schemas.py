from typing import Optional

from pydantic import BaseModel


class ConfigIn(BaseModel):
    glpi_url: str
    glpi_app_token: str
    glpi_user_token: str
    glpi_category_id: str = "22"
    glpi_field_id: str = "76670"
    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_tenant_id: str = ""
    outlook_calendar_id: str = ""
    outlook_user_upn: str = ""
    notify_emails: str = ""


class EquipoIn(BaseModel):
    id: object
    nombre: str
    fecha_limite: str
    hora_inicio: str = "08:00"
    incluido: bool = True
    destinatarios: str = ""


class ConfirmarIn(BaseModel):
    equipos: list[EquipoIn]
    modo_prueba: bool = True
    # Si > 0, en producción el servidor exige len(incluidos) == cuota_mes − tickets ya abiertos este mes.
    cuota_mes: int = 0


class InventoryMovimientoIn(BaseModel):
    asset_id: str
    asset_nombre: str
    tipo: str
    usuario_anterior: str = ""
    usuario_nuevo: str = ""
    estado_nuevo: str = ""
    motivo: str = ""
    responsable: str = ""
    ticket_id: str = ""
    fecha: str = ""
    modo_prueba: bool = True


class RenovacionEquipoExcelIn(BaseModel):
    id: str = ""
    nombre: str = ""
    estado: str = ""
    usuario: str = ""
    users_id: Optional[int] = None
    serial: str = ""
    fabricante: str = ""
    modelo: str = ""
    score: float = 0
    specs_fmt: str = ""
    ram_mb: int = 0
    disco_gb: int = 0
    tipo_disco: str = ""
    cpu: str = ""


class RenovacionParExcelIn(BaseModel):
    activo: RenovacionEquipoExcelIn
    reemplazo: Optional[RenovacionEquipoExcelIn] = None
    mejora_ram: int = 0
    mejora_disco: int = 0
    mejora_ssd: bool = False
    ganancia_score: float = 0


class RenovacionExcelCustomIn(BaseModel):
    total_activos: int = 0
    total_inactivos: int = 0
    debiles: int = 0
    candidatos: int = 0
    pares: list[RenovacionParExcelIn] = []
    todos: list[RenovacionEquipoExcelIn] = []


class RenovacionConfirmarIn(BaseModel):
    """Aplica en GLPI el traspaso: equipo reemplazo → usuario + estado activo; equipo débil → sin usuario + inactivo."""

    pares: list[RenovacionParExcelIn]
    modo_prueba: bool = True
    responsable: str = ""
    estado_reemplazo: str = "Activo"
    estado_debil: str = "Inactivo"


class ChecklistItemIn(BaseModel):
    id: str
    categoria: str
    texto: str


class CompletarIn(BaseModel):
    ticket_id: int
    computer_id: object
    nombre: str
    items_ok: list[str]
    notas: str = ""
    modo_prueba: bool = True
