"""Pruebas del lector CSV y su contrato de datos."""

import pytest

from wattwise.infraestructura.lector_mediciones_csv import (
    COLUMNAS,
    leer_mediciones_csv,
)


def _csv(*filas: str) -> bytes:
    encabezados = ",".join(COLUMNAS)
    return ("\n".join((encabezados, *filas)) + "\n").encode()


def test_importa_registro_valido() -> None:
    filas = leer_mediciones_csv(
        _csv("2026-11-13 08:00:00,220,5,0.9,1.2"),
        "datos.csv",
    )
    assert filas[0]["fecha_hora"] == "2026-11-13 08:00:00"
    assert filas[0]["potencia_activa_kw"] == 1.2


def test_admite_utf8_con_bom() -> None:
    contenido = b"\xef\xbb\xbf" + _csv("2026-11-13 08:00:00,220,5,0.9,1.2")
    assert len(leer_mediciones_csv(contenido, "datos.csv")) == 1


def test_importa_dos_registros() -> None:
    contenido = _csv(
        "2026-11-13 08:00:00,220,5,0.9,1.2",
        "2026-11-13 09:00:00,221,6,0.8,1.3",
    )
    assert len(leer_mediciones_csv(contenido, "datos.csv")) == 2


def test_rechaza_otros_encabezados() -> None:
    with pytest.raises(ValueError, match="columnas"):
        leer_mediciones_csv(b"equipo,valor\nA,2\n", "datos.csv")


def test_rechaza_columnas_incompletas() -> None:
    with pytest.raises(ValueError, match="columnas incorrecto"):
        leer_mediciones_csv(
            _csv("2026-11-13 08:00:00,220,5"),
            "datos.csv",
        )


def test_rechaza_columnas_extra() -> None:
    with pytest.raises(ValueError, match="columnas incorrecto"):
        leer_mediciones_csv(
            _csv("2026-11-13 08:00:00,220,5,0.9,1.2,99"),
            "datos.csv",
        )


def test_rechaza_formula() -> None:
    with pytest.raises(ValueError, match="formula"):
        leer_mediciones_csv(
            _csv("2026-11-13 08:00:00,220,5,0.9,=1+2"),
            "datos.csv",
        )


def test_rechaza_no_finito() -> None:
    with pytest.raises(ValueError, match="finito"):
        leer_mediciones_csv(
            _csv("2026-11-13 08:00:00,nan,5,0.9,1.2"),
            "datos.csv",
        )


def test_rechaza_csv_vacio() -> None:
    with pytest.raises(ValueError, match="no contiene mediciones"):
        leer_mediciones_csv(
            (",".join(COLUMNAS) + "\n").encode(),
            "datos.csv",
        )


def test_rechaza_extension() -> None:
    with pytest.raises(ValueError, match=".csv"):
        leer_mediciones_csv(
            _csv("2026-11-13 08:00:00,220,5,0.9,1.2"),
            "datos.xlsx",
        )


def test_rechaza_utf8_invalido() -> None:
    with pytest.raises(ValueError, match="UTF-8"):
        leer_mediciones_csv(b"\xff\xfe", "datos.csv")
