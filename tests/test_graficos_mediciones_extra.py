"""Pruebas de agregaciones descriptivas horarias en ECharts."""

from datetime import datetime

from wattwise.interfaz.graficos_mediciones_extra import (
    grafico_heatmap_horario,
    grafico_perfil_horario,
)


def _registros() -> list[dict[str, object]]:
    return [
        {"fecha_hora": datetime(2026, 1, 1, 8), "p_total_kw": 0.0},
        {"fecha_hora": datetime(2026, 1, 1, 9), "p_total_kw": 10.0},
        {"fecha_hora": datetime(2026, 1, 2, 8), "p_total_kw": 20.0},
        {"fecha_hora": datetime(2026, 1, 2, 9), "p_total_kw": None},
    ]


def test_perfil_promedia_por_hora_y_conserva_cero() -> None:
    grafico = grafico_perfil_horario(_registros(), "p_total_kw", "kW")
    assert grafico is not None
    assert grafico["series"][0]["data"] == [10.0, 10.0]


def test_heatmap_no_inventa_celdas_vacias() -> None:
    grafico = grafico_heatmap_horario(_registros(), "p_total_kw", "kW")
    assert grafico is not None
    assert len(grafico["series"][0]["data"]) == 3
    assert grafico["visualMap"]["min"] == 0.0


def test_heatmap_requiere_dos_dias() -> None:
    assert grafico_heatmap_horario(_registros()[:2], "p_total_kw", "kW") is None


def test_perfil_requiere_dos_horas() -> None:
    assert grafico_perfil_horario(_registros()[::2], "p_total_kw", "kW") is None


def test_no_grafica_variable_ausente() -> None:
    assert grafico_perfil_horario(_registros(), "v_total_v", "V") is None
