"""Regresiones de integridad PNG, aislamiento y PDF con graficas."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from wattwise.infraestructura.analisis_sqlite import AnalisisGuardado, inicializar_analisis
from wattwise.infraestructura.capturas_sqlite import (
    eliminar_captura,
    guardar_captura,
    listar_capturas,
    recuperar_captura,
    validar_png,
)
from wattwise.infraestructura.informe_graficas_pdf import generar_informe_graficas_pdf
from wattwise.infraestructura.proyectos_sqlite import crear_proyecto, eliminar_proyecto


def _png(color: str = "blue", dimension: tuple[int, int] = (500, 300)) -> bytes:
    salida = BytesIO()
    imagen = Image.new("RGB", dimension, color)
    imagen.save(salida, format="PNG")
    return salida.getvalue()


def _base(tmp_path: Path) -> tuple[Path, int, int]:
    ruta = tmp_path / "wattwise.sqlite3"
    proyecto = crear_proyecto(ruta, "Planta de ensayo")
    inicializar_analisis(ruta)
    with sqlite3.connect(ruta) as conexion:
        identidad = conexion.execute(
            "INSERT INTO analisis (proyecto_id, tipo, titulo, creado_utc, datos_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (proyecto, "inventario", "Balance de ensayo", "2026-11-14T10:00:00+00:00", "{}"),
        ).lastrowid
    assert identidad is not None
    return ruta, proyecto, identidad


def _analisis(proyecto: int, identidad: int) -> AnalisisGuardado:
    return AnalisisGuardado(
        identidad,
        proyecto,
        "inventario",
        "Ensayo <A>",
        "2026-11-14T10:00:00+00:00",
        {"potencia_total_kw": 12.5},
    )


def _captura(tmp_path: Path) -> tuple[Path, int, int, int]:
    ruta, proyecto, analisis = _base(tmp_path)
    identidad = guardar_captura(ruta, proyecto, analisis, "Pareto.png", "Area Hacienda", _png())
    return ruta, proyecto, analisis, identidad


def test_roundtrip_png_y_hash(tmp_path: Path) -> None:
    ruta, proyecto, _, identidad = _captura(tmp_path)
    registro, contenido = recuperar_captura(ruta, proyecto, identidad)
    assert registro.sha256 == hashlib.sha256(contenido).hexdigest()
    assert registro.nombre == "Pareto.png"
    assert contenido == _png()


def test_metadatos_sin_blob(tmp_path: Path) -> None:
    ruta, proyecto, _, _ = _captura(tmp_path)
    listado = listar_capturas(ruta, proyecto)
    assert len(listado) == 1
    assert not hasattr(listado[0], "contenido")


def test_deduplicacion_con_analisis(tmp_path: Path) -> None:
    ruta, proyecto, analisis, identidad = _captura(tmp_path)
    repetida = guardar_captura(ruta, proyecto, analisis, "Copia.png", "Otra", _png())
    assert identidad == repetida
    assert len(listar_capturas(ruta, proyecto)) == 1


def test_deduplicacion_sin_analisis(tmp_path: Path) -> None:
    ruta, proyecto, _ = _base(tmp_path)
    uno = guardar_captura(ruta, proyecto, None, "Uno.png", "", _png())
    dos = guardar_captura(ruta, proyecto, None, "Dos.png", "", _png())
    assert uno == dos


def test_admite_png_independiente_del_analisis(tmp_path: Path) -> None:
    ruta, proyecto, _ = _base(tmp_path)
    identidad = guardar_captura(ruta, proyecto, None, "Mediciones.png", "", _png())
    assert recuperar_captura(ruta, proyecto, identidad)[0].analisis_id is None


def test_no_mezcla_proyectos(tmp_path: Path) -> None:
    ruta, proyecto, _, identidad = _captura(tmp_path)
    otro = crear_proyecto(ruta, "Otro")
    assert listar_capturas(ruta, otro) == []
    with pytest.raises(ValueError, match="no encontrada"):
        recuperar_captura(ruta, otro, identidad)


def test_bloquea_analisis_de_otro_proyecto(tmp_path: Path) -> None:
    ruta, _, analisis = _base(tmp_path)
    otro = crear_proyecto(ruta, "Otro")
    with pytest.raises(ValueError, match="no pertenece"):
        guardar_captura(ruta, otro, analisis, "x.png", "", _png())


def test_bloquea_proyecto_inexistente(tmp_path: Path) -> None:
    ruta = tmp_path / "vacia.sqlite3"
    with pytest.raises(ValueError, match="no existe"):
        guardar_captura(ruta, 900, None, "x.png", "", _png())


@pytest.mark.parametrize("nombre", ["../a.png", "C:\\a.png", "a.jpg", "", " a.png", "a\x00.png"])
def test_rechaza_nombre_inseguro(tmp_path: Path, nombre: str) -> None:
    ruta, proyecto, _ = _base(tmp_path)
    with pytest.raises(ValueError, match="Nombre"):
        guardar_captura(ruta, proyecto, None, nombre, "", _png())


@pytest.mark.parametrize("contenido", [b"", b"hola", b"\x89PNG\r\n\x1a\ncorrupto"])
def test_rechaza_contenido_invalido(contenido: bytes) -> None:
    with pytest.raises(ValueError, match="PNG"):
        validar_png(contenido)


def test_rechaza_imagen_grande(tmp_path: Path) -> None:
    ruta, proyecto, _ = _base(tmp_path)
    with pytest.raises(ValueError, match="Dimensiones"):
        guardar_captura(ruta, proyecto, None, "grande.png", "", _png(dimension=(7001, 1)))


def test_bloquea_contenido_alterado(tmp_path: Path) -> None:
    ruta, proyecto, _, identidad = _captura(tmp_path)
    with sqlite3.connect(ruta) as conexion:
        conexion.execute(
            "UPDATE capturas_graficas SET contenido = ? WHERE id = ?",
            (sqlite3.Binary(_png("red")), identidad),
        )
    with pytest.raises(ValueError, match="SHA-256"):
        recuperar_captura(ruta, proyecto, identidad)


def test_eliminar_captura_no_elimina_proyecto(tmp_path: Path) -> None:
    ruta, proyecto, _, identidad = _captura(tmp_path)
    assert eliminar_captura(ruta, proyecto, identidad)
    assert not eliminar_captura(ruta, proyecto, identidad)
    assert listar_capturas(ruta, proyecto) == []


def test_eliminar_proyecto_borra_capturas(tmp_path: Path) -> None:
    ruta, proyecto, _, _ = _captura(tmp_path)
    assert eliminar_proyecto(ruta, proyecto)
    assert listar_capturas(ruta, proyecto) == []


def test_limite_cantidad(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import wattwise.infraestructura.capturas_sqlite as modulo

    ruta, proyecto, _ = _base(tmp_path)
    monkeypatch.setattr(modulo, "MAXIMO_POR_PROYECTO", 1)
    guardar_captura(ruta, proyecto, None, "a.png", "", _png("red"))
    with pytest.raises(ValueError, match="Limite"):
        guardar_captura(ruta, proyecto, None, "b.png", "", _png("green"))


def test_limite_total(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import wattwise.infraestructura.capturas_sqlite as modulo

    ruta, proyecto, _ = _base(tmp_path)
    inicio = _png("red")
    monkeypatch.setattr(modulo, "MAXIMO_TOTAL_PROYECTO", len(inicio) + 1)
    guardar_captura(ruta, proyecto, None, "a.png", "", inicio)
    with pytest.raises(ValueError, match="Limite"):
        guardar_captura(ruta, proyecto, None, "b.png", "", _png("blue"))


def test_pdf_con_portada_y_dos_graficas(tmp_path: Path) -> None:
    ruta, proyecto, analisis = _base(tmp_path)
    imagenes = []
    for nombre, color in (("Barras.png", "red"), ("Dona.png", "green")):
        identidad = guardar_captura(ruta, proyecto, analisis, nombre, "Ensayo", _png(color))
        imagenes.append(recuperar_captura(ruta, proyecto, identidad))
    contenido = generar_informe_graficas_pdf("Planta", _analisis(proyecto, analisis), imagenes)
    assert contenido.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page(?!s)\b", contenido)) == 3


def test_pdf_solo_capturas_proyecto(tmp_path: Path) -> None:
    ruta, proyecto, _ = _base(tmp_path)
    identidad = guardar_captura(ruta, proyecto, None, "Serie.png", "", _png())
    contenido = generar_informe_graficas_pdf(
        "Planta", None, [recuperar_captura(ruta, proyecto, identidad)]
    )
    assert len(re.findall(rb"/Type\s*/Page(?!s)\b", contenido)) == 2


def test_pdf_bloquea_captura_de_otro_analisis(tmp_path: Path) -> None:
    ruta, proyecto, analisis = _base(tmp_path)
    with sqlite3.connect(ruta) as conexion:
        otro_analisis = conexion.execute(
            "INSERT INTO analisis (proyecto_id, tipo, titulo, creado_utc, datos_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (proyecto, "inventario", "Otro", "2026", "{}"),
        ).lastrowid
    identidad = guardar_captura(ruta, proyecto, otro_analisis, "x.png", "", _png())
    with pytest.raises(ValueError, match="otro analisis"):
        generar_informe_graficas_pdf(
            "Planta",
            _analisis(proyecto, analisis),
            [recuperar_captura(ruta, proyecto, identidad)],
        )


def test_pdf_bloquea_captura_corrupta(tmp_path: Path) -> None:
    ruta, proyecto, analisis, identidad = _captura(tmp_path)
    metadata, contenido = recuperar_captura(ruta, proyecto, identidad)
    with pytest.raises(ValueError, match="SHA-256"):
        generar_informe_graficas_pdf(
            "Planta",
            _analisis(proyecto, analisis),
            [(metadata, contenido[:-1] + bytes([contenido[-1] ^ 1]))],
        )


def test_pdf_bloquea_lista_vacia(tmp_path: Path) -> None:
    ruta, proyecto, analisis = _base(tmp_path)
    with pytest.raises(ValueError, match="1 y 12"):
        generar_informe_graficas_pdf("Planta", _analisis(proyecto, analisis), [])


def test_pdf_bloquea_descripcion_larga(tmp_path: Path) -> None:
    ruta, proyecto, _, identidad = _captura(tmp_path)
    with pytest.raises(ValueError, match="observaciones"):
        generar_informe_graficas_pdf(
            "Planta",
            None,
            [recuperar_captura(ruta, proyecto, identidad)],
            observaciones="x" * 2001,
        )


def test_descripcion_mayor_al_limite_se_rechaza(tmp_path: Path) -> None:
    ruta, proyecto, _ = _base(tmp_path)
    with pytest.raises(ValueError, match="Descripcion"):
        guardar_captura(ruta, proyecto, None, "x.png", "x" * 501, _png())


def test_captura_vinculada_se_elimina_con_analisis(tmp_path: Path) -> None:
    ruta, proyecto, analisis, identidad = _captura(tmp_path)
    libre = guardar_captura(ruta, proyecto, None, "Libre.png", "", _png("red"))
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("PRAGMA foreign_keys = ON")
        conexion.execute("DELETE FROM analisis WHERE id = ?", (analisis,))
    restantes = {item.id for item in listar_capturas(ruta, proyecto)}
    assert identidad not in restantes
    assert libre in restantes


def test_pdf_rechaza_imagenes_de_dos_proyectos(tmp_path: Path) -> None:
    ruta, proyecto, _ = _base(tmp_path)
    otro = crear_proyecto(ruta, "Otro")
    a = guardar_captura(ruta, proyecto, None, "A.png", "", _png("red"))
    b = guardar_captura(ruta, otro, None, "B.png", "", _png("blue"))
    with pytest.raises(ValueError, match="mismo proyecto"):
        generar_informe_graficas_pdf(
            "Planta",
            None,
            [recuperar_captura(ruta, proyecto, a), recuperar_captura(ruta, otro, b)],
        )
