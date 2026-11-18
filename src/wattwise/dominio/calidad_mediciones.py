"""Audita cobertura y continuidad temporal sin alterar las mediciones."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from statistics import median

VARIABLES_ELECTRICAS = (
    "p_total_kw",
    "p_l1_kw",
    "p_l2_kw",
    "p_l3_kw",
    "i_total_a",
    "i_l1_a",
    "i_l2_a",
    "i_l3_a",
    "v_total_v",
    "v_l1_v",
    "v_l2_v",
    "v_l3_v",
    "fp_total",
)


@dataclass(frozen=True, slots=True)
class CalidadVariable:
    """Cantidad de datos utilizables y ausentes de una variable."""

    variable: str
    validos: int
    faltantes: int
    cobertura_pct: float


@dataclass(frozen=True, slots=True)
class CalidadTemporal:
    """Resumen de completitud y continuidad sin estimaciones electricas."""

    total_registros: int
    primera_fecha: datetime
    ultima_fecha: datetime
    fechas_distintas: int
    timestamps_duplicados: int
    intervalo_mediano_min: float | None
    huecos_largos: int
    variables: tuple[CalidadVariable, ...]
    advertencias: tuple[str, ...]


def _valor_valido(valor: object) -> bool:
    """Preserva cero, excluye None, booleanos y magnitudes no finitas."""
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and isfinite(valor)


def _fechas_validas(registros: list[dict[str, object]]) -> list[datetime]:
    """Exige fechas locales bien definidas antes de evaluar continuidad."""
    fechas = [registro.get("fecha_hora") for registro in registros]
    if not all(isinstance(fecha, datetime) and fecha.tzinfo is None for fecha in fechas):
        raise ValueError("Las fechas deben ser datetimes locales validos.")
    return fechas


def _continuidad(fechas: list[datetime]) -> tuple[list[datetime], int, float | None, int]:
    """Describe duplicados e intervalos sin rellenar muestras inexistentes."""
    distintas = sorted(set(fechas))
    duplicados = sum(cantidad - 1 for cantidad in Counter(fechas).values() if cantidad > 1)
    diferencias = [
        (posterior - anterior).total_seconds() / 60
        for anterior, posterior in zip(distintas, distintas[1:], strict=False)
    ]
    intervalo = median(diferencias) if diferencias else None
    huecos = sum(diferencia > 3 * intervalo for diferencia in diferencias) if intervalo else 0
    return distintas, duplicados, intervalo, huecos


def _cobertura(registros: list[dict[str, object]]) -> tuple[CalidadVariable, ...]:
    """Cuenta ceros como válidos y None como faltante."""
    variables = []
    for nombre in VARIABLES_ELECTRICAS:
        validos = sum(_valor_valido(registro.get(nombre)) for registro in registros)
        if validos:
            variables.append(
                CalidadVariable(
                    nombre,
                    validos,
                    len(registros) - validos,
                    100 * validos / len(registros),
                )
            )
    return tuple(variables)


def _advertencias(
    duplicados: int,
    huecos: int,
    distintas: list[datetime],
    variables: tuple[CalidadVariable, ...],
) -> tuple[str, ...]:
    """Explica límites de calidad sin declarar fallas eléctricas."""
    avisos = []
    if duplicados:
        avisos.append("Hay fechas duplicadas; revisar antes de integrar energia.")
    if huecos:
        avisos.append("Hay intervalos mayores que tres veces el intervalo mediano.")
    if any(variable.faltantes for variable in variables):
        avisos.append("Existen valores faltantes; no se han rellenado ni interpolado.")
    if len(distintas) < 2:
        avisos.append("Un unico instante no permite evaluar continuidad temporal.")
    return tuple(avisos)


def auditar_mediciones(registros: list[dict[str, object]]) -> CalidadTemporal:
    """Audita un grupo ya filtrado sin mezclar ni agrupar puntos de medicion."""
    if not registros:
        raise ValueError("No hay registros para auditar.")
    fechas = _fechas_validas(registros)
    distintas, duplicados, intervalo, huecos = _continuidad(fechas)
    variables = _cobertura(registros)
    return CalidadTemporal(
        total_registros=len(registros),
        primera_fecha=distintas[0],
        ultima_fecha=distintas[-1],
        fechas_distintas=len(distintas),
        timestamps_duplicados=duplicados,
        intervalo_mediano_min=intervalo,
        huecos_largos=huecos,
        variables=variables,
        advertencias=_advertencias(duplicados, huecos, distintas, variables),
    )
