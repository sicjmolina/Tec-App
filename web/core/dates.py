import calendar as cal_module
from datetime import date

from core.constants import DIAS_ES, MESES_ES


def mes_key(d: date = None):
    d = d or date.today()
    return f"{d.year}-{d.month:02d}"


def mes_anterior_key():
    hoy = date.today()
    if hoy.month == 1:
        return f"{hoy.year - 1}-12"
    return f"{hoy.year}-{hoy.month - 1:02d}"


def dias_habiles(year: int, month: int):
    _, ultimo = cal_module.monthrange(year, month)
    return [
        date(year, month, d)
        for d in range(1, ultimo + 1)
        if date(year, month, d).weekday() < 5
    ]


def asignar_fechas_habiles(equipos: list, year=None, month=None):
    hoy = date.today()
    y, m = (year or hoy.year), (month or hoy.month)
    dias = dias_habiles(y, m)
    dias = [d for d in dias if d >= hoy] or dias
    total = len(equipos)
    if total == 0:
        return []
    intervalo = max(1, len(dias) // total)
    resultado = []
    for i, eq in enumerate(equipos):
        idx = min(i * intervalo + intervalo // 2, len(dias) - 1)
        resultado.append({**eq, "fecha_limite": dias[idx].isoformat()})
    return resultado


def fmt_fecha_larga(d: date):
    return f"{DIAS_ES[d.weekday()]}, {d.day:02d} de {MESES_ES[d.month].lower()}"
