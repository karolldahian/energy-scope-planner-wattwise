"""Graficos horarios ECharts sin agregaciones entre puntos de medicion."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import isfinite


def _muestras(registros: list[dict[str, object]], campo: str) -> list[tuple[datetime, float]]:
    """Selecciona fechas y valores validos, preservando los ceros."""
    muestras = []
    for registro in registros:
        fecha = registro.get("fecha_hora")
        valor = registro.get(campo)
        if (
            isinstance(fecha, datetime)
            and isinstance(valor, (int, float))
            and not isinstance(valor, bool)
            and isfinite(valor)
        ):
            muestras.append((fecha, float(valor)))
    return muestras


def _agrupar(
    muestras: list[tuple[datetime, float]],
    clave: str,
) -> dict[tuple[str, int] | int, list[float]]:
    """Reune observaciones para promedios descriptivos, no energia."""
    grupos: dict[tuple[str, int] | int, list[float]] = defaultdict(list)
    for fecha, valor in muestras:
        indice = (fecha.date().isoformat(), fecha.hour) if clave == "dia_hora" else fecha.hour
        grupos[indice].append(valor)
    return grupos


def grafico_heatmap_horario(
    registros: list[dict[str, object]],
    campo: str,
    unidad: str,
) -> dict[str, object] | None:
    """Genera un mapa dia-hora; requiere dos dias y al menos dos horas distintas."""
    muestras = _muestras(registros, campo)
    dias = sorted({fecha.date().isoformat() for fecha, _ in muestras})
    horas = sorted({fecha.hour for fecha, _ in muestras})
    if len(dias) < 2 or len(horas) < 2:
        return None
    grupos = _agrupar(muestras, "dia_hora")
    puntos = [
        [hora, dia, round(sum(valores) / len(valores), 4)]
        for (dia, hora), valores in grupos.items()
    ]
    puntos.sort(key=lambda punto: (punto[1], punto[0]))
    valores = [punto[2] for punto in puntos]
    return {
        "backgroundColor": "#ffffff",
        "title": {"text": f"Mapa horario: {campo} ({unidad})", "left": "center"},
        "tooltip": {"position": "top", "formatter": "{c}"},
        "grid": {"top": 90, "left": 100, "right": 85, "bottom": 95},
        "xAxis": {"type": "category", "data": [f"{hora:02d}:00" for hora in range(24)]},
        "yAxis": {"type": "category", "data": dias},
        "visualMap": {
            "min": min(valores),
            "max": max(valores),
            "calculable": True,
            "orient": "vertical",
            "right": 5,
            "top": "middle",
        },
        "toolbox": {
            "right": 8,
            "feature": {"saveAsImage": {"type": "png", "pixelRatio": 2}, "restore": {}},
        },
        "series": [
            {
                "name": f"Promedio ({unidad})",
                "type": "heatmap",
                "data": [[punto[0], dias.index(punto[1]), punto[2]] for punto in puntos],
                "emphasis": {"itemStyle": {"borderColor": "#333", "borderWidth": 1}},
            }
        ],
    }


def grafico_perfil_horario(
    registros: list[dict[str, object]],
    campo: str,
    unidad: str,
) -> dict[str, object] | None:
    """Muestra la media por hora de registros; no supone energia ni continuidad."""
    muestras = _muestras(registros, campo)
    grupos = _agrupar(muestras, "hora")
    if len(grupos) < 2:
        return None
    datos = [
        [f"{hora:02d}:00", round(sum(grupos[hora]) / len(grupos[hora]), 4)]
        for hora in sorted(grupos)
    ]
    return {
        "backgroundColor": "#ffffff",
        "title": {"text": f"Perfil horario promedio: {campo} ({unidad})", "left": "center"},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 70, "right": 30, "top": 75, "bottom": 80},
        "xAxis": {"type": "category", "name": "Hora", "data": [dato[0] for dato in datos]},
        "yAxis": {"type": "value", "name": unidad, "scale": True},
        "toolbox": {
            "right": 8,
            "feature": {"saveAsImage": {"type": "png", "pixelRatio": 2}, "restore": {}},
        },
        "series": [{"name": campo, "type": "bar", "data": [dato[1] for dato in datos]}],
    }
