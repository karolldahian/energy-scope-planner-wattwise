"""Pruebas de indicadores y curvas ECharts por variable disponible."""

from datetime import datetime, timedelta

from wattwise.interfaz.mediciones_avanzadas import estadisticas, grafico_temporal


def _registros() -> list[dict[str, object]]:
    return [
        {"fecha_hora": datetime(2026, 11, 1) + timedelta(hours=i), "p_l1_kw": valor}
        for i, valor in enumerate((0, None, 10, 20))
    ]


def test_estadisticas_con_cero_y_ausente() -> None:
    resultado = estadisticas(_registros(), "p_l1_kw")
    assert resultado is not None
    assert resultado.minimo == 0
    assert resultado.maximo == 20
    assert resultado.promedio == 10
    assert resultado.validos == 3
    assert resultado.total == 4
    assert resultado.p95 == 19


def test_variable_inexistente_no_produce_indicadores() -> None:
    assert estadisticas(_registros(), "v_total_v") is None


def test_grafico_no_inventa_valor_faltante() -> None:
    grafico = grafico_temporal(_registros(), ["p_l1_kw"], "Potencia")
    assert grafico["series"][0]["connectNulls"] is False
    assert grafico["series"][0]["data"][1][1] is None
    assert grafico["toolbox"]["feature"]["saveAsImage"]["type"] == "png"
    assert len(grafico["dataZoom"]) == 2


def test_linea_p95_usa_serie_seleccionada() -> None:
    grafico = grafico_temporal(_registros(), ["p_l1_kw"], "Potencia", ("P95",), "p_l1_kw")
    assert grafico["series"][0]["markLine"]["data"][0]["yAxis"] == 19
