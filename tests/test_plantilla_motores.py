"""Pruebas de la plantilla XLSX de motores."""

from io import BytesIO

from openpyxl import load_workbook

from wattwise.infraestructura.lector_motores_excel import COLUMNAS
from wattwise.infraestructura.plantilla_motores import crear_plantilla_motores


def test_plantilla_tiene_encabezados_compatibles() -> None:
    contenido = crear_plantilla_motores()
    libro = load_workbook(BytesIO(contenido), read_only=True)
    try:
        hoja = libro.worksheets[0]
        assert hoja.title == "Motores"
        assert tuple(celda.value for celda in hoja[1]) == COLUMNAS
        assert hoja["A2"].value is None
    finally:
        libro.close()


def test_plantilla_incluye_instrucciones() -> None:
    contenido = crear_plantilla_motores()
    libro = load_workbook(BytesIO(contenido), read_only=True)
    try:
        hoja = libro["Instrucciones"]
        assert hoja.max_row == len(COLUMNAS) + 1
        assert hoja["B4"].value is not None
    finally:
        libro.close()


def test_plantilla_es_determinista_en_contenido() -> None:
    primera = load_workbook(BytesIO(crear_plantilla_motores()), read_only=True)
    segunda = load_workbook(BytesIO(crear_plantilla_motores()), read_only=True)
    try:
        for fila_primera, fila_segunda in zip(
            primera.worksheets[0].values,
            segunda.worksheets[0].values,
            strict=True,
        ):
            assert fila_primera == fila_segunda
    finally:
        primera.close()
        segunda.close()
