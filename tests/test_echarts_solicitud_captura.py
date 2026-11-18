"""Evita guardar capturas anteriores al solicitar una nueva vista."""

from __future__ import annotations

import base64
import struct
import zlib

import pytest

from wattwise.interfaz.echarts_capturable import _JS, decodificar_captura


def _png() -> bytes:
    """Construye un PNG pequeño con estructura admitida."""

    def chunk(tipo: bytes, contenido: bytes) -> bytes:
        crc = zlib.crc32(tipo + contenido) & 0xFFFFFFFF
        return len(contenido).to_bytes(4, "big") + tipo + contenido + struct.pack(">I", crc)

    cabecera = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixeles = zlib.compress(b"\x00\xff\x00\x00\xff")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", cabecera)
        + chunk(b"IDAT", pixeles)
        + chunk(b"IEND", b"")
    )


def _mensaje(solicitud: object) -> dict[str, object]:
    """Entrega un mensaje comparable con el emitido por el navegador."""
    return {
        "estado_echarts": {"series": [{"type": "bar", "data": [1]}]},
        "imagen_png_base64": base64.b64encode(_png()).decode("ascii"),
        "solicitud_captura": solicitud,
    }


def test_la_captura_conserva_el_id_de_solicitud() -> None:
    """Una captura solo puede corresponder a la solicitud que la produjo."""
    captura = decodificar_captura(_mensaje(37))
    assert captura is not None
    assert captura.solicitud_captura == 37


def test_captura_anterior_compatible_con_formato_previo() -> None:
    """Las capturas previas se reconocen como no solicitadas."""
    mensaje = _mensaje(1)
    del mensaje["solicitud_captura"]
    captura = decodificar_captura(mensaje)
    assert captura is not None
    assert captura.solicitud_captura == 0


@pytest.mark.parametrize("solicitud", [-1, True, "12", None, 1.5])
def test_rechaza_id_de_solicitud_invalido(solicitud: object) -> None:
    """No permite confundir booleanos o texto con una solicitud nueva."""
    with pytest.raises(ValueError, match="solicitud"):
        decodificar_captura(_mensaje(solicitud))


def test_js_envia_la_solicitud_original() -> None:
    """Comprueba que el puente devuelve el identificador del pedido."""
    assert "solicitud_captura: solicitud" in _JS
