"""Indicadores eléctricos complementarios con validación conservadora."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from wattwise.dominio.energia_temporal import ResultadoEnergia


@dataclass(frozen=True, slots=True)
class ResumenDesbalanceTension:
    """Desbalance porcentual entre tres tensiones simultáneas comparables."""

    promedio_pct: float
    maximo_pct: float
    p95_pct: float
    muestras_validas: int
    muestras_totales: int


def _numero_positivo(valor: object) -> float | None:
    """Admite números reales estrictamente positivos, nunca valores ausentes."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    if not isfinite(valor) or valor <= 0:
        return None
    return float(valor)


def _potencia_no_negativa(valor: object) -> float | None:
    """Acepta potencia real finita, incluido cero, pero nunca exportación."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    if not isfinite(valor) or valor < 0:
        return None
    return float(valor)


def _desbalance_fila(registro: dict[str, object]) -> float | None:
    """Calcula desviación máxima relativa a la media de tres tensiones."""
    tensiones = [_numero_positivo(registro.get(campo)) for campo in ("v_l1_v", "v_l2_v", "v_l3_v")]
    if any(tension is None for tension in tensiones):
        return None
    promedio = sum(tensiones) / 3
    return 100 * max(abs(tension - promedio) for tension in tensiones) / promedio


def calcular_desbalance_tension(
    registros: list[dict[str, object]],
) -> ResumenDesbalanceTension | None:
    """Resume desbalance de tensión sin sustituir ausencias por ceros.

    Las tres columnas deben representar una misma convención de tensión
    (fase-neutro o línea-línea), tomadas simultáneamente en cada fila.
    """
    valores = sorted(
        valor for registro in registros if (valor := _desbalance_fila(registro)) is not None
    )
    if not valores:
        return None
    posicion = (len(valores) - 1) * 0.95
    inferior = int(posicion)
    superior = min(inferior + 1, len(valores) - 1)
    p95 = valores[inferior] + (valores[superior] - valores[inferior]) * (posicion - inferior)
    return ResumenDesbalanceTension(
        promedio_pct=sum(valores) / len(valores),
        maximo_pct=valores[-1],
        p95_pct=p95,
        muestras_validas=len(valores),
        muestras_totales=len(registros),
    )


def calcular_factor_carga(
    registros: list[dict[str, object]],
    energia: ResultadoEnergia,
) -> float | None:
    """Calcula factor de carga de importación únicamente en una serie íntegra.

    Reutiliza la energía validada por integración trapezoidal. No emite un
    factor si hay huecos, fechas duplicadas, exportación o potencia negativa.
    El máximo es muestral, no una máxima demanda facturable por intervalo.
    """
    campos = ("frontera", "area", "punto_medicion")
    identidades = {
        tuple(str(fila.get(campo) or "Sin especificar") for campo in campos) for fila in registros
    }
    if len(identidades) != 1:
        return None
    if (
        len(registros) < 2
        or energia.tramos_validos != len(registros) - 1
        or energia.tramos_descartados
        or energia.fechas_duplicadas
        or energia.horas_integradas <= 0
        or energia.exportada_kwh > 0
    ):
        return None
    if any(not isinstance(fila.get("fecha_hora"), datetime) for fila in registros):
        return None
    potencias = [_potencia_no_negativa(fila.get("p_total_kw")) for fila in registros]
    if any(potencia is None for potencia in potencias):
        return None
    maximo = max(potencia for potencia in potencias if potencia is not None)
    if maximo <= 0:
        return None
    porcentaje = 100 * energia.importada_kwh / (maximo * energia.horas_integradas)
    if not isfinite(porcentaje) or not 0 <= porcentaje <= 100 + 1e-8:
        return None
    return min(100.0, porcentaje)
