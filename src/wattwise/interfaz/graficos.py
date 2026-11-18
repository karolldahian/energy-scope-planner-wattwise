"""Opciones de Apache ECharts nativo de Streamlit."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from wattwise.dominio.inventario import ResultadoInventario
from wattwise.dominio.mediciones import ResumenMediciones
from wattwise.dominio.motores import ResumenMotores


def grafico_inventario(
    resultado: ResultadoInventario,
    *,
    por_area: bool = False,
) -> dict[str, object]:
    """Presenta potencia instalada por tipo de carga o area."""
    grupos: defaultdict[str, float] = defaultdict(float)

    for registro in resultado.registros:
        grupo = (registro.area or "Sin area") if por_area else registro.tipo_carga

        grupos[grupo] += registro.potencia_instalada_kw

    ordenados = sorted(
        grupos.items(),
        key=lambda item: (-item[1], item[0]),
    )

    principales = ordenados[:20]

    if len(ordenados) > 20:
        restantes = sum(valor for _, valor in ordenados[20:])
        principales.append(("Otros grupos", restantes))

    return {
        "tooltip": {"trigger": "axis"},
        "grid": {
            "left": "30%",
            "right": "7%",
            "top": 20,
            "bottom": 40,
        },
        "xAxis": {
            "type": "value",
            "name": "kW",
        },
        "yAxis": {
            "type": "category",
            "data": [nombre for nombre, _ in reversed(principales)],
            "axisLabel": {
                "width": 150,
                "overflow": "truncate",
            },
        },
        "series": [
            {
                "type": "bar",
                "name": "Potencia instalada (kW)",
                "data": [valor for _, valor in reversed(principales)],
            }
        ],
        "toolbox": {
            "left": 0,
            "feature": {"restore": {}},
        },
    }


def grafico_mediciones(
    resultado: ResumenMediciones,
) -> dict[str, object]:
    """Presenta la serie real de potencia activa medida."""
    tabla = pd.DataFrame(
        {
            "fecha_hora": [m.fecha_hora for m in resultado.registros],
            "potencia_activa_kw": [m.potencia_activa_kw for m in resultado.registros],
        }
    )

    return {
        "tooltip": {"trigger": "axis"},
        "grid": {
            "left": 70,
            "right": 35,
            "top": 35,
            "bottom": 90,
        },
        "dataset": {"source": tabla},
        "xAxis": {"type": "time"},
        "yAxis": {
            "type": "value",
            "name": "kW",
        },
        "dataZoom": [
            {"type": "inside"},
            {"type": "slider", "bottom": 20},
        ],
        "series": [
            {
                "type": "line",
                "name": "Potencia activa (kW)",
                "encode": {
                    "x": "fecha_hora",
                    "y": "potencia_activa_kw",
                },
                "showSymbol": False,
                "sampling": "lttb",
            }
        ],
    }


def grafico_motores(
    resultado: ResumenMotores,
) -> dict[str, object]:
    """Compara amperios nominales y medidos sin diagnosticar fallas."""
    motores = sorted(
        resultado.registros,
        key=lambda motor: (
            -motor.relacion_corriente_pct,
            motor.equipo,
        ),
    )[:20]

    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 4},
        "grid": {
            "left": "32%",
            "right": "7%",
            "top": 65,
            "bottom": 30,
        },
        "xAxis": {
            "type": "value",
            "name": "A",
        },
        "yAxis": {
            "type": "category",
            "data": [motor.equipo for motor in reversed(motores)],
            "axisLabel": {
                "width": 170,
                "overflow": "truncate",
            },
        },
        "series": [
            {
                "type": "bar",
                "name": "Nominal (A)",
                "data": [motor.corriente_nominal_a for motor in reversed(motores)],
            },
            {
                "type": "bar",
                "name": "Medida (A)",
                "data": [motor.corriente_medida_a for motor in reversed(motores)],
            },
        ],
    }
