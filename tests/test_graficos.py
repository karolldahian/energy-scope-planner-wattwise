"""Pruebas de opciones de Apache ECharts para WattWise."""

from datetime import datetime

import pytest

from wattwise.dominio.inventario import analizar_inventario
from wattwise.dominio.mediciones import analizar_mediciones
from wattwise.dominio.motores import analizar_motores
from wattwise.interfaz.graficos import (
    grafico_inventario,
    grafico_mediciones,
    grafico_motores,
)


def test_barras_inventario() -> None:
    """Comprueba agrupaciones y potencia instalada."""
    resultado = analizar_inventario(
        [
            {
                "equipo": "A",
                "tipo_carga": "Bombas",
                "cantidad": 2,
                "potencia_unitaria_kw": 3,
                "area": "A",
            },
            {
                "equipo": "B",
                "tipo_carga": "Luces",
                "cantidad": 1,
                "potencia_unitaria_kw": 2,
                "area": "B",
            },
        ]
    )

    opciones = grafico_inventario(resultado)

    assert opciones["series"][0]["type"] == "bar"
    assert sum(opciones["series"][0]["data"]) == pytest.approx(8)

    opciones_area = grafico_inventario(
        resultado,
        por_area=True,
    )

    assert set(opciones_area["yAxis"]["data"]) == {"A", "B"}


def test_linea_mediciones() -> None:
    """Comprueba la estructura temporal del grafico."""
    resultado = analizar_mediciones(
        [
            {
                "fecha_hora": "2026-11-13 08:00:00",
                "tension_v": 220,
                "corriente_a": 2,
                "factor_potencia": 0.9,
                "potencia_activa_kw": 1,
            }
        ]
    )

    opciones = grafico_mediciones(resultado)
    tabla = opciones["dataset"]["source"]

    assert len(tabla) == 1
    assert isinstance(tabla.iloc[0]["fecha_hora"], datetime)
    assert opciones["series"][0]["encode"]["y"] == "potencia_activa_kw"


def test_comparacion_motores() -> None:
    """Verifica corrientes nominales y medidas en la grafica."""
    motor = {
        "area": "Bombas",
        "equipo": "M1",
        "potencia_nominal_hp": 1,
        "numero_fases": 1,
        "corriente_nominal_a": 10,
        "corriente_medida_a": 11,
        "horas_operacion_mes": 120,
    }

    opciones = grafico_motores(analizar_motores([motor]))

    assert opciones["series"][0]["data"] == [10.0]
    assert opciones["series"][1]["data"] == [11.0]
