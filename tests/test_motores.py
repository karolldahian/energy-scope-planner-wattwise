"""Pruebas de importacion y calculos descriptivos de motores."""

from io import BytesIO

import pytest
from openpyxl import Workbook

from wattwise.dominio.motores import HP_A_KW, analizar_motores
from wattwise.infraestructura.lector_motores_excel import (
    COLUMNAS,
    leer_motores_excel,
)


def _motor() -> dict[str, object]:
    """Construye un motor valido para las pruebas."""
    return {
        "area": "Bombas",
        "equipo": "Motor 1",
        "potencia_nominal_hp": 2,
        "numero_fases": 3,
        "corriente_nominal_a": 5,
        "corriente_medida_a": 5.5,
        "horas_operacion_mes": 120,
    }


def _excel(filas: list[list[object]]) -> bytes:
    """Crea un XLSX temporal en memoria."""
    libro = Workbook()
    hoja = libro.active

    assert hoja is not None

    for fila in filas:
        hoja.append(fila)

    salida = BytesIO()
    libro.save(salida)
    libro.close()

    return salida.getvalue()


def test_conversion_hp_y_corriente() -> None:
    """Verifica conversion y porcentaje medido/nominal."""
    resultado = analizar_motores([_motor()])

    assert resultado.potencia_salida_nominal_total_kw == pytest.approx(2 * HP_A_KW)
    assert resultado.registros[0].relacion_corriente_pct == pytest.approx(110.0)
    assert resultado.motores_corriente_superior_nominal == 1
    assert resultado.cantidad_motores == 1


def test_dos_motores() -> None:
    """Agrupa dos registros de areas diferentes."""
    a = _motor()

    b = {
        **_motor(),
        "equipo": "Motor 2",
        "area": "Taller",
        "corriente_medida_a": 0,
    }

    resultado = analizar_motores([a, b])

    assert resultado.cantidad_motores == 2
    assert resultado.areas_identificadas == 2
    assert resultado.motores_corriente_superior_nominal == 1


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("potencia_nominal_hp", 0),
        ("potencia_nominal_hp", -1),
        ("potencia_nominal_hp", float("nan")),
        ("corriente_nominal_a", 0),
        ("corriente_medida_a", -1),
        ("corriente_medida_a", float("inf")),
        ("numero_fases", 2),
        ("numero_fases", True),
        ("horas_operacion_mes", 745),
        ("equipo", ""),
    ],
)
def test_rechaza_datos_invalidos(
    campo: str,
    valor: object,
) -> None:
    """Rechaza variables fuera del contrato."""
    fila = _motor()
    fila[campo] = valor

    with pytest.raises(ValueError, match="Fila Excel 2"):
        analizar_motores([fila])


def test_lectura_excel_correcta() -> None:
    """Lee motores desde un archivo XLSX."""
    fila = _motor()

    contenido = _excel(
        [
            list(COLUMNAS),
            [fila[campo] for campo in COLUMNAS],
        ]
    )

    resultado = analizar_motores(leer_motores_excel(contenido, "motores.xlsx"))

    assert resultado.registros[0].equipo == "Motor 1"


def test_rechaza_formula() -> None:
    """Rechaza formulas de Excel."""
    fila = _motor()
    fila["corriente_nominal_a"] = "=2+3"

    contenido = _excel(
        [
            list(COLUMNAS),
            [fila[campo] for campo in COLUMNAS],
        ]
    )

    with pytest.raises(ValueError, match="formula"):
        leer_motores_excel(contenido, "motores.xlsx")


def test_rechaza_columnas_diferentes() -> None:
    """No acepta un contrato de columnas diferente."""
    contenido = _excel(
        [
            ["equipo", "area"],
            ["M", "B"],
        ]
    )

    with pytest.raises(ValueError, match="columnas"):
        leer_motores_excel(contenido, "motores.xlsx")


def test_rechaza_extension() -> None:
    """Solo admite XLSX."""
    with pytest.raises(ValueError, match=".xlsx"):
        leer_motores_excel(b"sin contenido", "motores.csv")
