"""Compara potencia nominal declarada y pico medido solo con alcance confirmado."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True, slots=True)
class ResultadoComparacion:
    """Resultado descriptivo trazable, no diagnostico de demanda ni fallas."""

    potencia_instalada_kw: float
    potencia_maxima_medida_kw: float
    relacion_pct: float | None
    equipos_inventariados: int
    muestras_validas: int
    muestras_totales: int
    punto_medicion: str
    primera_fecha: datetime
    ultima_fecha: datetime
    alcance_confirmado: str
    advertencias: tuple[str, ...]


def _real(valor: object, nombre: str) -> float:
    """Rechaza ausencias, booleanos y numeros no finitos."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not isfinite(valor):
        raise ValueError(f"{nombre}: se requiere un numero finito.")
    return float(valor)


def _potencia_instalada(registros: list[dict[str, object]]) -> tuple[float, int]:
    """Suma kW declarados y cantidad fisica sin asumir consumo."""
    if not registros:
        raise ValueError("Selecciona al menos una carga del inventario.")
    total = 0.0
    unidades = 0
    for registro in registros:
        kw = _real(registro.get("potencia_instalada_kw"), "Potencia instalada")
        cantidad = registro.get("cantidad")
        if kw < 0 or isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad < 1:
            raise ValueError("El inventario contiene potencias o cantidades invalidas.")
        total += kw
        unidades += cantidad
    if not isfinite(total):
        raise ValueError("La potencia instalada total no es finita.")
    return total, unidades


def _identidad(registro: dict[str, object]) -> tuple[str, str, str]:
    return tuple(
        str(registro.get(clave) or "Sin especificar")
        for clave in ("frontera", "area", "punto_medicion")
    )


def _mediciones(registros: list[dict[str, object]]) -> tuple[list[float], list[datetime], str]:
    """Exige un solo punto y datos realmente medidos de potencia total."""
    if not registros:
        raise ValueError("Selecciona mediciones de un punto.")
    identidades = {_identidad(registro) for registro in registros}
    if len(identidades) != 1:
        raise ValueError("No es valido mezclar fronteras, areas o puntos de medicion.")
    punto = next(iter(identidades))[2]
    if punto == "Sin especificar":
        raise ValueError("El punto de medicion debe estar identificado.")
    fechas = _fechas_validas(registros)
    potencias = _potencias_validas(registros)
    if not potencias:
        raise ValueError("El punto no tiene potencia activa total medida valida.")
    return potencias, fechas, punto


def _fechas_validas(registros: list[dict[str, object]]) -> list[datetime]:
    """No mezcla fechas sin zona con fechas de zona implícita."""
    fechas = [registro.get("fecha_hora") for registro in registros]
    if not all(isinstance(fecha, datetime) and fecha.tzinfo is None for fecha in fechas):
        raise ValueError("Las mediciones deben tener fechas locales validas.")
    return fechas


def _potencias_validas(registros: list[dict[str, object]]) -> list[float]:
    """Descarta huecos y deja intactos los signos de potencia medida."""
    potencias = []
    for registro in registros:
        valor = registro.get("p_total_kw")
        if isinstance(valor, (int, float)) and not isinstance(valor, bool) and isfinite(valor):
            potencias.append(float(valor))
    return potencias


def _advertencias(
    instalada: float,
    potencias: list[float],
    relacion: float | None,
    fechas: list[datetime],
) -> tuple[str, ...]:
    """Reúne cautelas de interpretación y calidad de la medición."""
    avisos = [
        "Comparacion descriptiva: potencia de placa no equivale a demanda de diseno.",
        "La confirmacion de alcance es declarada por el usuario, no verificada por la app.",
    ]
    if instalada == 0:
        avisos.append("Instalada igual a cero: no se calcula relacion porcentual.")
    if any(potencia < 0 for potencia in potencias):
        avisos.append("Existen potencias negativas; verificar sentido de flujo.")
    if relacion is not None and relacion > 100:
        avisos.append("El pico supera la potencia declarada; revisar cobertura y placa.")
    if len(potencias) < 2:
        avisos.append("Una sola muestra no demuestra representatividad temporal.")
    if len(set(fechas)) != len(fechas):
        avisos.append("Hay instantes duplicados; revisar procedencia.")
    return tuple(avisos)


def comparar_potencias(
    inventario: list[dict[str, object]],
    mediciones: list[dict[str, object]],
    *,
    alcance_confirmado: bool,
    justificacion_alcance: str,
) -> ResultadoComparacion:
    """Compara solo despues de una confirmacion profesional explicita."""
    if alcance_confirmado is not True:
        raise ValueError("Debes confirmar expresamente el alcance electrico.")
    if (
        not isinstance(justificacion_alcance, str)
        or not 15 <= len(justificacion_alcance.strip()) <= 500
    ):
        raise ValueError("Describe el alcance electrico en 15 a 500 caracteres.")
    instalada, equipos = _potencia_instalada(inventario)
    potencias, fechas, punto = _mediciones(mediciones)
    maxima = max(potencias)
    relacion = 100 * maxima / instalada if instalada > 0 and maxima >= 0 else None
    return ResultadoComparacion(
        potencia_instalada_kw=instalada,
        potencia_maxima_medida_kw=maxima,
        relacion_pct=relacion,
        equipos_inventariados=equipos,
        muestras_validas=len(potencias),
        muestras_totales=len(mediciones),
        punto_medicion=punto,
        primera_fecha=min(fechas),
        ultima_fecha=max(fechas),
        alcance_confirmado=justificacion_alcance.strip(),
        advertencias=_advertencias(instalada, potencias, relacion, fechas),
    )


def grafico_comparacion(resultado: ResultadoComparacion) -> dict[str, object]:
    """Devuelve dos barras kW de origen distinto, sin mezclar series temporales."""
    return {
        "backgroundColor": "#ffffff",
        "title": {"text": "Potencia instalada frente a pico medido", "left": "center"},
        "tooltip": {"trigger": "axis", "renderMode": "richText"},
        "grid": {"top": 85, "bottom": 65, "left": 70, "right": 35},
        "xAxis": {"type": "category", "data": ["Instalada declarada", "Maxima medida"]},
        "yAxis": {"type": "value", "name": "kW"},
        "toolbox": {
            "right": 8,
            "feature": {
                "saveAsImage": {"type": "png", "pixelRatio": 2},
                "restore": {},
            },
        },
        "series": [
            {
                "type": "bar",
                "name": "Potencia (kW)",
                "data": [resultado.potencia_instalada_kw, resultado.potencia_maxima_medida_kw],
                "itemStyle": {"color": "#2563eb"},
                "barMaxWidth": 100,
            }
        ],
    }
