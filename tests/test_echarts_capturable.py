"""Regresiones del puente que transporta la imagen y el estado ECharts."""

from __future__ import annotations

import base64
import struct
import sys
import zlib
from types import SimpleNamespace

import pytest

from wattwise.interfaz import echarts_capturable as modulo


def _png_minimo() -> bytes:
    """PNG RGBA válido de un píxel, sin recursos externos."""

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


def test_opciones_validas() -> None:
    contenido = modulo._validar_opciones({"series": [{"type": "line", "data": [1, 2]}]})
    assert '"series"' in contenido


@pytest.mark.parametrize(
    "opciones",
    [{}, {"series": []}, {"series": [float("nan")]}, {"series": [object()]}],
)
def test_opciones_invalidas(opciones: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        modulo._validar_opciones(opciones)


def test_captura_y_png_validos() -> None:
    png = _png_minimo()
    estado = {"series": [{"type": "line", "data": [1]}], "dataZoom": [{"start": 25}]}
    resultado = modulo.decodificar_captura(
        {
            "estado_echarts": estado,
            "imagen_png_base64": base64.b64encode(png).decode("ascii"),
        }
    )
    assert resultado is not None
    assert resultado.imagen_png == png
    assert resultado.estado_echarts["dataZoom"][0]["start"] == 25


@pytest.mark.parametrize(
    "valor",
    [123, {}, {"estado_echarts": {}, "imagen_png_base64": "A==="}],
)
def test_capturas_invalidas(valor: object) -> None:
    with pytest.raises(ValueError):
        modulo.decodificar_captura(valor)


def test_componente_registrado_una_vez(monkeypatch: pytest.MonkeyPatch) -> None:
    llamadas: list[tuple[str, object]] = []

    class Componentes:
        def component(self, nombre: str, **kwargs: object) -> object:
            llamadas.append(("registro", nombre))

            def montar(**datos: object) -> SimpleNamespace:
                llamadas.append(("montaje", datos))
                return SimpleNamespace(captura=None)

            return montar

    falso = SimpleNamespace(components=SimpleNamespace(v2=Componentes()))
    monkeypatch.setitem(sys.modules, "streamlit", falso)
    modulo._componente.cache_clear()
    try:
        opciones = {"series": [{"type": "bar", "data": [1]}]}
        assert modulo.mostrar_echarts_capturable(opciones, clave="prueba") is None
        assert modulo.mostrar_echarts_capturable(opciones, clave="otra") is None
        assert len([tipo for tipo, _ in llamadas if tipo == "registro"]) == 1
    finally:
        modulo._componente.cache_clear()


def test_parametros_invalidos() -> None:
    opciones = {"series": [{"type": "bar", "data": [1]}]}
    for parametros in (
        {"clave": ""},
        {"clave": "test", "altura": True},
        {"clave": "test", "altura": 200},
        {"clave": "test", "solicitud_captura": -1},
        {"clave": "test", "mostrar_boton_prueba": "sí"},
    ):
        with pytest.raises(ValueError):
            modulo.mostrar_echarts_capturable(opciones, **parametros)
