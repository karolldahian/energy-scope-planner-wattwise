"""Validaciones y analisis de mediciones electricas registradas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True, slots=True)
class Medicion:
    """Punto de medicion con potencia activa declarada."""

    fecha_hora: datetime
    tension_v: float
    corriente_a: float
    factor_potencia: float
    potencia_activa_kw: float


@dataclass(frozen=True, slots=True)
class ResumenMediciones:
    """Resumen de un periodo muestreado, no de toda la instalacion."""

    registros: tuple[Medicion, ...]
    potencia_maxima_kw: float
    potencia_promedio_kw: float
    tension_minima_v: float
    tension_maxima_v: float
    energia_estimada_kwh: float | None
    duracion_horas: float


def _numero(valor: object, nombre: str) -> float:
    """Exige valores numericos finitos no negativos."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"{nombre} debe ser numerico.")

    numero = float(valor)

    if not isfinite(numero) or numero < 0:
        raise ValueError(f"{nombre} debe ser finito y no negativo.")

    return numero


def validar_medicion(fila: dict[str, object]) -> Medicion:
    """Comprueba fecha y variables medidas sin inferir conexiones."""
    fecha = fila.get("fecha_hora")

    if not isinstance(fecha, str):
        raise ValueError("fecha_hora debe ser texto ISO 8601.")

    try:
        instante = datetime.strptime(
            fecha.strip(),
            "%Y-%m-%d %H:%M:%S",
        )
    except ValueError as error:
        raise ValueError("fecha_hora requiere AAAA-MM-DD HH:MM:SS.") from error

    fp = _numero(
        fila.get("factor_potencia"),
        "factor_potencia",
    )

    if fp > 1:
        raise ValueError("factor_potencia debe estar entre 0 y 1.")

    return Medicion(
        fecha_hora=instante,
        tension_v=_numero(
            fila.get("tension_v"),
            "tension_v",
        ),
        corriente_a=_numero(
            fila.get("corriente_a"),
            "corriente_a",
        ),
        factor_potencia=fp,
        potencia_activa_kw=_numero(
            fila.get("potencia_activa_kw"),
            "potencia_activa_kw",
        ),
    )


def analizar_mediciones(
    filas: list[dict[str, object]],
) -> ResumenMediciones:
    """Integra potencia por trapecios entre muestras consecutivas."""
    if not filas:
        raise ValueError("No hay mediciones para analizar.")

    if len(filas) > 100_000:
        raise ValueError("Se supera el limite de 100000 mediciones.")

    registros: list[Medicion] = []

    for numero, fila in enumerate(filas, start=2):
        try:
            registros.append(validar_medicion(fila))
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"Fila {numero}: {error}") from error

    energia = 0.0

    for anterior, actual in zip(
        registros,
        registros[1:],
        strict=False,
    ):
        horas = (actual.fecha_hora - anterior.fecha_hora).total_seconds() / 3600

        if horas <= 0:
            raise ValueError("Las fechas deben ser estrictamente crecientes.")

        if horas > 1:
            raise ValueError(
                "Hay intervalos mayores a 60 minutos; no se estima energia sobre esos vacios."
            )

        energia += (anterior.potencia_activa_kw + actual.potencia_activa_kw) * horas / 2

    if not isfinite(energia):
        raise ValueError("La energia calculada excede el rango numerico.")

    duracion = (registros[-1].fecha_hora - registros[0].fecha_hora).total_seconds() / 3600

    return ResumenMediciones(
        registros=tuple(registros),
        potencia_maxima_kw=max(m.potencia_activa_kw for m in registros),
        potencia_promedio_kw=(sum(m.potencia_activa_kw for m in registros) / len(registros)),
        tension_minima_v=min(m.tension_v for m in registros),
        tension_maxima_v=max(m.tension_v for m in registros),
        energia_estimada_kwh=(energia if len(registros) >= 2 else None),
        duracion_horas=duracion,
    )
