"""Constantes y datos estáticos del dominio."""

META_KEY = "_meta"

MESES_ES = [
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

STATUS_MAP = {
    1: "Nuevo",
    2: "En curso",
    3: "En espera",
    4: "Pendiente",
    5: "Resuelto",
    6: "Cerrado",
}

CHECKLIST_ITEMS = [
    {"id": "c01", "categoria": "Limpieza física", "texto": "Limpiar polvo de ventiladores, disipador de CPU y rejillas de ventilación con aire comprimido"},
    {"id": "c02", "categoria": "Limpieza física", "texto": "Limpiar el interior del gabinete (polvo acumulado en tarjetas, cables y ranuras)"},
    {"id": "c03", "categoria": "Limpieza física", "texto": "Limpiar teclado, mouse y pantalla con paño antiestático"},
    {"id": "c04", "categoria": "Hardware", "texto": "Verificar que todos los cables internos (SATA, alimentación, RAM) estén bien conectados"},
    {"id": "c05", "categoria": "Hardware", "texto": "Revisar estado físico de la RAM (sin golpes ni quemaduras); resentar si es necesario"},
    {"id": "c06", "categoria": "Hardware", "texto": "Verificar temperatura de CPU y GPU en reposo (debe ser < 55 °C)"},
    {"id": "c07", "categoria": "Hardware", "texto": "Comprobar funcionamiento de puertos USB, audio y red"},
    {"id": "c08", "categoria": "Almacenamiento", "texto": "Ejecutar análisis SMART del disco duro / SSD (sin sectores defectuosos críticos)"},
    {"id": "c09", "categoria": "Almacenamiento", "texto": "Verificar espacio libre en disco C: (mínimo 15 % libre)"},
    {"id": "c10", "categoria": "Sistema operativo", "texto": "Instalar actualizaciones de Windows pendientes (Windows Update)"},
    {"id": "c11", "categoria": "Sistema operativo", "texto": "Verificar que el antivirus esté activo y con definiciones al día"},
    {"id": "c12", "categoria": "Sistema operativo", "texto": "Ejecutar análisis rápido de antivirus"},
    {"id": "c13", "categoria": "Sistema operativo", "texto": "Eliminar archivos temporales y limpiar papelera de reciclaje"},
    {"id": "c14", "categoria": "Sistema operativo", "texto": "Revisar programas de inicio y deshabilitar los innecesarios"},
    {"id": "c15", "categoria": "Red y conectividad", "texto": "Confirmar conectividad de red (ping al gateway y a Internet)"},
    {"id": "c16", "categoria": "Red y conectividad", "texto": "Verificar que la IP / DNS estén configurados correctamente según política de IT"},
    {"id": "c17", "categoria": "Seguridad", "texto": "Confirmar que el equipo tiene contraseña de inicio de sesión activa"},
    {"id": "c18", "categoria": "Seguridad", "texto": "Verificar que el cifrado de disco (BitLocker u otro) esté habilitado si aplica"},
    {"id": "c19", "categoria": "Respaldo", "texto": "Confirmar que el último respaldo de datos del usuario se realizó correctamente"},
    {"id": "c20", "categoria": "Cierre", "texto": "Documentar observaciones encontradas y acciones realizadas (campo 'Notas' al final)"},
]

SECRET_FIELDS = frozenset({"glpi_app_token", "glpi_user_token", "azure_client_secret"})
PLACEHOLDER = "__saved__"
