"""Pruebas del lector de mediciones XLSX."""

from datetime import datetime
from io import BytesIO

import pytest
from openpyxl import Workbook

from wattwise.infraestructura.lector_mediciones_excel import (
    COLUMNAS,
    leer_mediciones_excel,
)


def _excel(filas: list[list[object]]) -> bytes:
    libro = Workbook()
    hoja = libro.active
    assert hoja is not None
    for fila in filas:
        hoja.append(fila)
    salida = BytesIO()
    libro.save(salida)
    libro.close()
    return salida.getvalue()


def _fila() -> list[object]:
    return ["2026-11-13 08:00:00", 220, 5, 0.9, 1.2]


def test_lee_fecha_textual_y_valores() -> None:
    contenido = _excel([list(COLUMNAS), _fila()])
    resultado = leer_mediciones_excel(contenido, "mediciones.xlsx")
    assert len(resultado) == 1
    assert resultado[0]["fecha_hora"] == "2026-11-13 08:00:00"
    assert resultado[0]["potencia_activa_kw"] == 1.2


def test_lee_fecha_nativa_excel() -> None:
    fila = _fila()
    fila[0] = datetime(2026, 11, 13, 8)
    contenido = _excel([list(COLUMNAS), fila])
    resultado = leer_mediciones_excel(contenido, "mediciones.xlsx")
    assert resultado[0]["fecha_hora"] == "2026-11-13 08:00:00"


def test_omite_filas_totalmente_vacias() -> None:
    contenido = _excel([list(COLUMNAS), _fila(), [None] * 5])
    assert len(leer_mediciones_excel(contenido, "mediciones.xlsx")) == 1


def test_rechaza_formulas() -> None:
    fila = _fila()
    fila[4] = "=2+3"
    contenido = _excel([list(COLUMNAS), fila])
    with pytest.raises(ValueError, match="formula"):
        leer_mediciones_excel(contenido, "mediciones.xlsx")


def test_rechaza_encabezados_diferentes() -> None:
    contenido = _excel([["equipo", "potencia"], ["A", 1]])
    with pytest.raises(ValueError, match="columnas"):
        leer_mediciones_excel(contenido, "mediciones.xlsx")


def test_rechaza_xlsx_vacio() -> None:
    contenido = _excel([list(COLUMNAS)])
    with pytest.raises(ValueError, match="no contiene mediciones"):
        leer_mediciones_excel(contenido, "mediciones.xlsx")


def test_rechaza_fecha_numerica() -> None:
    fila = _fila()
    fila[0] = 12345
    contenido = _excel([list(COLUMNAS), fila])
    with pytest.raises(ValueError, match="fecha_hora"):
        leer_mediciones_excel(contenido, "mediciones.xlsx")


@pytest.mark.parametrize("nombre", ["mediciones.csv", "mediciones.xls"])
def test_rechaza_extension(nombre: str) -> None:
    with pytest.raises(ValueError, match=".xlsx"):
        leer_mediciones_excel(b"no es excel", nombre)


def test_rechaza_zip_invalido() -> None:
    with pytest.raises(ValueError, match="XLSX valido"):
        leer_mediciones_excel(b"no es zip", "mediciones.xlsx")
