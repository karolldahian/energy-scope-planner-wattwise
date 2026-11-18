"""Regresiones del nombre editable y los controles de exportación ECharts."""

from __future__ import annotations

import base64
import struct
import sys
import zlib
from types import SimpleNamespace

import pytest

from wattwise.interfaz import echarts_capturable as modulo


def _png_minimo() -> bytes:
    """PNG válido de un píxel para probar la carga de capturas."""

    def bloque(tipo: bytes, datos: bytes) -> bytes:
        crc = zlib.crc32(tipo + datos) & 0xFFFFFFFF
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", crc)

    cabecera = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixeles = zlib.compress(b"\x00\xff\x00\x00\xff")
    return (
        b"\x89PNG\r\n\x1a\n"
        + bloque(b"IHDR", cabecera)
        + bloque(b"IDAT", pixeles)
        + bloque(b"IEND", b"")
    )


@pytest.mark.parametrize(
    ("titulo", "esperado"),
    [
        ({"text": "Curva activa"}, "Curva activa"),
        ([{"text": "Corriente por fase"}], "Corriente por fase"),
        ({"text": " "}, "Gráfica"),
        (None, "Gráfica"),
    ],
)
def test_titulo_original(titulo: object, esperado: str) -> None:
    assert modulo._titulo_inicial({"title": titulo}) == esperado


def test_captura_conserva_nombre_editado() -> None:
    resultado = modulo.decodificar_captura(
        {
            "estado_echarts": {"series": [{"type": "line", "data": [1]}]},
            "imagen_png_base64": base64.b64encode(_png_minimo()).decode("ascii"),
            "nombre_archivo": "Zoom del equipo B2",
        }
    )
    assert resultado is not None
    assert resultado.nombre_archivo == "Zoom del equipo B2"


def test_captura_rechaza_nombre_excesivo() -> None:
    with pytest.raises(ValueError):
        modulo.decodificar_captura(
            {
                "estado_echarts": {"series": [{"type": "line", "data": [1]}]},
                "imagen_png_base64": base64.b64encode(_png_minimo()).decode("ascii"),
                "nombre_archivo": "x" * 121,
            }
        )


def test_nombre_predeterminado_llega_al_componente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montajes: list[dict[str, object]] = []

    class Componentes:
        def component(self, nombre: str, **kwargs: object) -> object:
            del nombre, kwargs

            def montar(**datos: object) -> SimpleNamespace:
                montajes.append(datos)
                return SimpleNamespace(captura=None)

            return montar

    falso = SimpleNamespace(components=SimpleNamespace(v2=Componentes()))
    monkeypatch.setitem(sys.modules, "streamlit", falso)
    modulo._componente.cache_clear()
    try:
        opciones = {
            "title": {"text": "Pareto por equipo"},
            "series": [{"type": "bar", "data": [1]}],
        }
        modulo.mostrar_echarts_capturable(opciones, clave="demo")
        assert montajes[0]["data"]["titulo_predeterminado"] == "Pareto por equipo"
    finally:
        modulo._componente.cache_clear()


def test_titulo_predeterminado_invalido() -> None:
    opciones = {"series": [{"type": "bar", "data": [1]}]}
    with pytest.raises(ValueError):
        modulo.mostrar_echarts_capturable(opciones, clave="prueba", titulo_predeterminado=" ")
