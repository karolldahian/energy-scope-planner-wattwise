"""Pruebas del analisis de inventarios electricos WattWise."""

from io import BytesIO

import pytest
from openpyxl import Workbook

from wattwise.dominio.inventario import analizar_inventario
from wattwise.infraestructura.lector_inventario_excel import (
    leer_inventario_excel,
)


def _crear_excel(filas: list[list[object]]) -> bytes:
    """Construye un archivo de ensayo en memoria."""
    libro = Workbook()
    hoja = libro.active

    assert hoja is not None

    for fila in filas:
        hoja.append(fila)

    salida = BytesIO()
    libro.save(salida)
    libro.close()

    return salida.getvalue()


def test_potencia_instalada_correcta() -> None:
    """Calcula potencia de varias cargas."""
    resultado = analizar_inventario(
        [
            {
                "equipo": "Motor A",
                "tipo_carga": "Motor",
                "cantidad": 2,
                "potencia_unitaria_kw": 5.5,
                "area": "Produccion",
            },
            {
                "equipo": "Luminaria",
                "tipo_carga": "Iluminacion",
                "cantidad": 10,
                "potencia_unitaria_kw": 0.1,
                "area": "Oficina",
            },
        ]
    )

    assert resultado.potencia_total_kw == pytest.approx(12.0)
    assert resultado.cantidad_equipos == 12
    assert resultado.cantidad_areas == 2
    assert resultado.tipo_carga_predominante == "Motor"


@pytest.mark.parametrize(
    "cantidad",
    [0, -1, True, 2.5, "3"],
)
def test_rechaza_cantidades_invalidas(cantidad: object) -> None:
    """Evita cantidades no enteras o ambiguas."""
    with pytest.raises(ValueError):
        analizar_inventario(
            [
                {
                    "equipo": "Motor",
                    "tipo_carga": "Motor",
                    "cantidad": cantidad,
                    "potencia_unitaria_kw": 3.0,
                }
            ]
        )


@pytest.mark.parametrize(
    "potencia",
    [-1, float("nan"), float("inf"), True],
)
def test_rechaza_potencias_invalidas(potencia: object) -> None:
    """Evita valores electricos invalidos."""
    with pytest.raises(ValueError):
        analizar_inventario(
            [
                {
                    "equipo": "Motor",
                    "tipo_carga": "Motor",
                    "cantidad": 2,
                    "potencia_unitaria_kw": potencia,
                }
            ]
        )


def test_lectura_excel_valida() -> None:
    """Lee encabezados y datos sin alterar valores."""
    contenido = _crear_excel(
        [
            ["equipo", "tipo_carga", "cantidad", "potencia_unitaria_kw"],
            ["Motor", "Motor", 2, 5.5],
        ]
    )

    filas = leer_inventario_excel(contenido, "inventario.xlsx")
    resultado = analizar_inventario(filas)

    assert resultado.potencia_total_kw == pytest.approx(11.0)


def test_rechaza_formulas_excel() -> None:
    """No confia en formulas incluidas en archivos externos."""
    contenido = _crear_excel(
        [
            ["equipo", "tipo_carga", "cantidad", "potencia_unitaria_kw"],
            ["Motor", "Motor", 2, "=5+1"],
        ]
    )

    with pytest.raises(ValueError, match="Formula"):
        leer_inventario_excel(contenido, "inventario.xlsx")


def test_rechaza_columnas_faltantes() -> None:
    """No calcula con inventarios incompletos."""
    contenido = _crear_excel(
        [
            ["equipo", "tipo_carga", "cantidad"],
            ["Motor", "Motor", 2],
        ]
    )

    with pytest.raises(ValueError, match="Faltan columnas"):
        leer_inventario_excel(contenido, "inventario.xlsx")


def test_rechaza_archivo_no_excel() -> None:
    """No procesa formatos distintos de XLSX."""
    with pytest.raises(ValueError):
        leer_inventario_excel(b"archivo", "inventario.csv")
