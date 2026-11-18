"""Estima energia por punto sin puentear huecos ni sumar mediciones ajenas."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import isfinite


@dataclass(frozen=True, slots=True)
class IntervaloEnergia:
    """Tramo de integracion de potencia activa, posiblemente dividido por dia."""

    inicio: datetime
    fin: datetime
    importada_kwh: float
    exportada_kwh: float


@dataclass(frozen=True, slots=True)
class DiaEnergia:
    """Energia aproximada asociada al dia natural de cada tramo."""

    fecha: date
    importada_kwh: float
    exportada_kwh: float
    neta_kwh: float


@dataclass(frozen=True, slots=True)
class ResultadoEnergia:
    """Resumen trazable de una integracion trapezoidal condicionada."""

    importada_kwh: float
    exportada_kwh: float
    neta_kwh: float
    horas_integradas: float
    tramos_validos: int
    tramos_descartados: int
    fechas_duplicadas: int
    intervalos: tuple[IntervaloEnergia, ...]
    por_dia: tuple[DiaEnergia, ...]


def _potencia(valor: object) -> float | None:
    """Acepta magnitudes reales finitas y no convierte ausencias en cero."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    if not isfinite(valor):
        return None
    return float(valor)


def _identidad(registro: dict[str, object]) -> tuple[str, str, str]:
    """Aisla los registros segun frontera, area y punto declarados."""
    return tuple(
        str(registro.get(campo) or "Sin especificar")
        for campo in ("frontera", "area", "punto_medicion")
    )


def _integrar_signos(inicio_kw: float, fin_kw: float, horas: float) -> tuple[float, float]:
    """Separa energia importada y exportada aun si la curva cruza por cero."""
    if inicio_kw >= 0 and fin_kw >= 0:
        return (inicio_kw + fin_kw) * horas / 2, 0.0
    if inicio_kw <= 0 and fin_kw <= 0:
        return 0.0, -(inicio_kw + fin_kw) * horas / 2
    proporcion = abs(inicio_kw) / (abs(inicio_kw) + abs(fin_kw))
    primera = abs(inicio_kw) * horas * proporcion / 2
    segunda = abs(fin_kw) * horas * (1 - proporcion) / 2
    if inicio_kw > 0:
        return primera, segunda
    return segunda, primera


def _separar_dias(
    inicio: datetime,
    fin: datetime,
    potencia_inicial: float,
    potencia_final: float,
) -> list[IntervaloEnergia]:
    """Divide en medianoche e interpola solo dentro de un intervalo admitido."""
    resultado: list[IntervaloEnergia] = []
    total_segundos = (fin - inicio).total_seconds()
    actual = inicio
    while actual < fin:
        medianoche = datetime.combine(actual.date() + timedelta(days=1), time.min)
        siguiente = min(fin, medianoche)
        fraccion_inicial = (actual - inicio).total_seconds() / total_segundos
        fraccion_final = (siguiente - inicio).total_seconds() / total_segundos
        p0 = potencia_inicial + (potencia_final - potencia_inicial) * fraccion_inicial
        p1 = potencia_inicial + (potencia_final - potencia_inicial) * fraccion_final
        horas = (siguiente - actual).total_seconds() / 3600
        importada, exportada = _integrar_signos(p0, p1, horas)
        resultado.append(IntervaloEnergia(actual, siguiente, importada, exportada))
        actual = siguiente
    return resultado


def _totales_diarios(intervalos: list[IntervaloEnergia]) -> tuple[DiaEnergia, ...]:
    """Agrega tramos por la fecha de inicio, nunca por la fecha final."""
    por_dia: dict[date, list[float]] = {}
    for intervalo in intervalos:
        dia = por_dia.setdefault(intervalo.inicio.date(), [0.0, 0.0])
        dia[0] += intervalo.importada_kwh
        dia[1] += intervalo.exportada_kwh
    return tuple(
        DiaEnergia(fecha, valores[0], valores[1], valores[0] - valores[1])
        for fecha, valores in sorted(por_dia.items())
    )


def analizar_energia_temporal(
    registros: list[dict[str, object]],
    *,
    hueco_maximo_minutos: int,
) -> ResultadoEnergia:
    """Integra P_total instantanea con intervalos y alcance controlados.

    Requiere que el ingeniero confirme externamente la semantica de muestras
    instantaneas. Cada hueco, ausencia o fecha duplicada bloquea el tramo.
    """
    if (
        isinstance(hueco_maximo_minutos, bool)
        or not isinstance(hueco_maximo_minutos, int)
        or not 1 <= hueco_maximo_minutos <= 1440
    ):
        raise ValueError("El hueco maximo debe estar entre 1 y 1440 minutos.")
    if not registros:
        raise ValueError("No existen mediciones para integrar.")
    if len({_identidad(registro) for registro in registros}) != 1:
        raise ValueError("No se deben mezclar fronteras, areas o puntos de medicion.")
    if any(not isinstance(registro.get("fecha_hora"), datetime) for registro in registros):
        raise ValueError("Todas las mediciones deben tener fecha y hora validas.")
    fechas = [registro["fecha_hora"] for registro in registros]
    if any(fecha.tzinfo is not None for fecha in fechas):
        raise ValueError("No se pueden mezclar o usar zonas horarias implicitas.")

    ordenados = sorted(registros, key=lambda registro: registro["fecha_hora"])
    repetidas = {fecha for fecha, cantidad in Counter(fechas).items() if cantidad > 1}
    admitidos: list[IntervaloEnergia] = []
    validos = 0
    descartados = 0
    for anterior, siguiente in zip(ordenados, ordenados[1:], strict=False):
        inicio = anterior["fecha_hora"]
        fin = siguiente["fecha_hora"]
        p0 = _potencia(anterior.get("p_total_kw"))
        p1 = _potencia(siguiente.get("p_total_kw"))
        minutos = (fin - inicio).total_seconds() / 60
        if (
            inicio in repetidas
            or fin in repetidas
            or p0 is None
            or p1 is None
            or minutos <= 0
            or minutos > hueco_maximo_minutos
        ):
            descartados += 1
            continue
        admitidos.extend(_separar_dias(inicio, fin, p0, p1))
        validos += 1

    importada = sum(tramo.importada_kwh for tramo in admitidos)
    exportada = sum(tramo.exportada_kwh for tramo in admitidos)
    horas = sum((tramo.fin - tramo.inicio).total_seconds() / 3600 for tramo in admitidos)
    return ResultadoEnergia(
        importada_kwh=importada,
        exportada_kwh=exportada,
        neta_kwh=importada - exportada,
        horas_integradas=horas,
        tramos_validos=validos,
        tramos_descartados=descartados,
        fechas_duplicadas=len(repetidas),
        intervalos=tuple(admitidos),
        por_dia=_totales_diarios(admitidos),
    )
