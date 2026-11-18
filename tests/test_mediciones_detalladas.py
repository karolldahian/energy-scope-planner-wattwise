"""Pruebas de importacion flexible con libros de Excel en memoria."""

from datetime import datetime
from io import BytesIO

import pytest
from openpyxl import Workbook

from wattwise.infraestructura.lector_mediciones_detalladas import leer_mediciones_detalladas


def _archivo(columnas: tuple[str, ...], filas: list[tuple[object, ...]]) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.append(columnas)
    for fila in filas:
        hoja.append(fila)
    salida = BytesIO()
    libro.save(salida)
    libro.close()
    return salida.getvalue()


def test_lee_potencia_sola_y_conserva_cero() -> None:
    datos = _archivo(("fecha_hora", "p_total_kw"), [(datetime(2026, 1, 1), 0)])
    resultado = leer_mediciones_detalladas(datos, "mediciones.xlsx")
    assert resultado.cobertura == {"p_total_kw": 1}
    assert resultado.registros[0]["p_total_kw"] == 0
    assert resultado.registros[0]["p_l1_kw"] is None


def test_lee_solo_corriente_y_fecha_excel_numerica() -> None:
    datos = _archivo(("i_total_a", "fecha_hora"), [(12.5, 45154.375)])
    resultado = leer_mediciones_detalladas(datos, "mediciones.xlsx")
    assert resultado.registros[0]["i_total_a"] == 12.5
    assert resultado.registros[0]["fecha_hora"] == datetime(2023, 8, 16, 9, 0)


def test_acepta_valores_parciales_y_avisa() -> None:
    datos = _archivo(
        ("fecha_hora", "v_l1_v", "fp_total"),
        [(datetime(2026, 1, 1), 220, None), (datetime(2026, 1, 2), "malo", 0.9)],
    )
    resultado = leer_mediciones_detalladas(datos, "mediciones.xlsx")
    assert resultado.cobertura == {"v_l1_v": 1, "fp_total": 1}
    assert resultado.registros[1]["v_l1_v"] is None
    assert resultado.problemas == 1


def test_fila_con_fecha_mala_se_registra() -> None:
    datos = _archivo(
        ("fecha_hora", "p_l1_kw"),
        [("invalida", 5), (datetime(2026, 1, 2), 3)],
    )
    resultado = leer_mediciones_detalladas(datos, "mediciones.xlsx")
    assert len(resultado.registros) == 1
    assert resultado.filas_omitidas == 1
    assert resultado.advertencias


def test_decimal_colombiano() -> None:
    datos = _archivo(("fecha_hora", "p_total_kw"), [(datetime(2026, 1, 1), "12,5")])
    resultado = leer_mediciones_detalladas(datos, "mediciones.xlsx")
    assert resultado.registros[0]["p_total_kw"] == 12.5


def test_rechaza_si_no_hay_variable_electrica() -> None:
    datos = _archivo(("fecha_hora", "area"), [(datetime(2026, 1, 1), "A")])
    with pytest.raises(ValueError, match="variable electrica"):
        leer_mediciones_detalladas(datos, "mediciones.xlsx")


def test_rechaza_duplicados() -> None:
    datos = _archivo(("fecha_hora", "p_total_kw", "p_total_kw"), [(datetime(2026, 1, 1), 1, 2)])
    with pytest.raises(ValueError, match="duplicadas"):
        leer_mediciones_detalladas(datos, "mediciones.xlsx")


def test_rechaza_si_todo_es_invalido() -> None:
    datos = _archivo(("fecha_hora", "fp_total"), [(datetime(2026, 1, 1), 2)])
    with pytest.raises(ValueError, match="No hay variables"):
        leer_mediciones_detalladas(datos, "mediciones.xlsx")


def test_rechaza_csv() -> None:
    datos = _archivo(("fecha_hora", "p_total_kw"), [(datetime(2026, 1, 1), 2)])
    with pytest.raises(ValueError, match="XLSX"):
        leer_mediciones_detalladas(datos, "mediciones.csv")


def test_rechaza_formulas() -> None:
    datos = _archivo(("fecha_hora", "p_total_kw"), [(datetime(2026, 1, 1), "=2+3")])
    with pytest.raises(ValueError, match="No hay variables"):
        leer_mediciones_detalladas(datos, "mediciones.xlsx")
