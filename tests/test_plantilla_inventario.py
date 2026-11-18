"""Pruebas del generador XLSX de inventarios WattWise."""

from io import BytesIO

from openpyxl import load_workbook

from wattwise.infraestructura.lector_inventario_excel import (
    COLUMNAS_OBLIGATORIAS,
    COLUMNAS_PERMITIDAS,
)
from wattwise.infraestructura.plantilla_inventario import (
    ENCABEZADOS,
    crear_plantilla_inventario,
)


def test_plantilla_es_excel_valido() -> None:
    """Comprueba que el archivo generado sea un XLSX valido."""
    contenido = crear_plantilla_inventario()

    assert contenido.startswith(b"PK")

    libro = load_workbook(BytesIO(contenido))

    try:
        assert libro.sheetnames == ["Inventario"]
    finally:
        libro.close()


def test_encabezados_compatibles_con_lector() -> None:
    """Comprueba que las columnas coincidan con el lector."""
    assert set(ENCABEZADOS) == COLUMNAS_PERMITIDAS
    assert set(ENCABEZADOS) >= COLUMNAS_OBLIGATORIAS

    libro = load_workbook(BytesIO(crear_plantilla_inventario()))

    try:
        hoja = libro.active
        assert hoja is not None

        encabezados = tuple(celda.value for celda in hoja[1])

        assert encabezados == ENCABEZADOS
    finally:
        libro.close()


def test_plantilla_no_contiene_equipos_ficticios() -> None:
    """Comprueba que no existan registros precargados."""
    libro = load_workbook(BytesIO(crear_plantilla_inventario()))

    try:
        hoja = libro.active
        assert hoja is not None

        for fila in hoja.iter_rows(
            min_row=2,
            max_row=101,
        ):
            assert all(celda.value is None for celda in fila)
    finally:
        libro.close()


def test_plantilla_contiene_validaciones() -> None:
    """Verifica reglas basicas de cantidad y potencia."""
    libro = load_workbook(BytesIO(crear_plantilla_inventario()))

    try:
        hoja = libro.active
        assert hoja is not None

        validaciones = list(hoja.data_validations.dataValidation)

        assert len(validaciones) == 2

        rangos = {str(validacion.sqref) for validacion in validaciones}

        assert "C2:C100001" in rangos
        assert "D2:D100001" in rangos
    finally:
        libro.close()
