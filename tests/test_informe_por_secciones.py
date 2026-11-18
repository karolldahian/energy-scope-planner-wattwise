"""Regresión de informes nuevos sin modificar PDF, ECharts ni notas originales."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from wattwise.infraestructura.capturas_sqlite import guardar_captura
from wattwise.infraestructura.informe_por_secciones import (
    AnalisisInforme,
    BorradorInforme,
    generar_pdf_por_secciones,
    guardar_borrador_informe,
    recuperar_borrador_informe,
    validar_borrador,
)
from wattwise.infraestructura.proyectos_sqlite import crear_proyecto, eliminar_proyecto


def _png() -> bytes:
    memoria = BytesIO()
    Image.new("RGB", (700, 320), "white").save(memoria, format="PNG")
    return memoria.getvalue()


@pytest.fixture
def preparado(tmp_path: Path) -> tuple[Path, BorradorInforme]:
    ruta = tmp_path / "wattwise.sqlite3"
    proyecto_id = crear_proyecto(ruta, "Proyecto de ensayo")
    captura_id = guardar_captura(ruta, proyecto_id, None, "pareto.png", "", _png())
    borrador = BorradorInforme(
        proyecto_id=proyecto_id,
        nombre="Proyecto de ensayo",
        responsable="Ingeniería",
        fecha=date.today().isoformat(),
        descripcion="Informe técnico",
        analisis=(
            AnalisisInforme(
                clave="inventario_1",
                titulo="Pareto de cargas",
                modulo="inventario",
                grafica="Pareto por tipo de carga",
                captura_id=captura_id,
                observacion="Concentración de potencia instalada.",
            ),
            AnalisisInforme(
                clave="mediciones_2",
                titulo="Perfil de potencia",
                modulo="mediciones",
                grafica="Potencia activa (kW)",
                observacion="Se observan variaciones temporales.",
                incluir_grafica=False,
            ),
        ),
    )
    return ruta, borrador


def test_guardar_y_recuperar_sin_perder_orden(preparado: tuple[Path, BorradorInforme]) -> None:
    ruta, borrador = preparado
    guardar_borrador_informe(ruta, borrador)
    assert recuperar_borrador_informe(ruta, borrador.proyecto_id) == borrador
    assert [item.clave for item in borrador.analisis] == ["inventario_1", "mediciones_2"]


def test_reemplazo_atomico_del_borrador(preparado: tuple[Path, BorradorInforme]) -> None:
    ruta, borrador = preparado
    guardar_borrador_informe(ruta, borrador)
    actualizado = replace(borrador, descripcion="Descripción actualizada")
    guardar_borrador_informe(ruta, actualizado)
    assert recuperar_borrador_informe(ruta, borrador.proyecto_id) == actualizado
    with sqlite3.connect(ruta) as conexion:
        total = conexion.execute("SELECT COUNT(*) FROM borradores_informe_secciones").fetchone()[0]
        assert total == 1


def test_verifica_sha256(preparado: tuple[Path, BorradorInforme]) -> None:
    ruta, borrador = preparado
    guardar_borrador_informe(ruta, borrador)
    with sqlite3.connect(ruta) as conexion:
        contenido, huella = conexion.execute(
            "SELECT contenido_json, sha256 FROM borradores_informe_secciones"
        ).fetchone()
        assert hashlib.sha256(contenido.encode("utf-8")).hexdigest() == huella
        conexion.execute(
            "UPDATE borradores_informe_secciones SET contenido_json = ? WHERE proyecto_id = ?",
            ('{"manipulado":true}', borrador.proyecto_id),
        )
    with pytest.raises(ValueError, match="integridad"):
        recuperar_borrador_informe(ruta, borrador.proyecto_id)


def test_proyectos_aislados(preparado: tuple[Path, BorradorInforme]) -> None:
    ruta, borrador = preparado
    otro = crear_proyecto(ruta, "Segundo proyecto")
    guardar_borrador_informe(ruta, borrador)
    assert recuperar_borrador_informe(ruta, otro) is None
    with pytest.raises(ValueError, match="no pertenece"):
        generar_pdf_por_secciones(ruta, replace(borrador, proyecto_id=otro))


def test_borrador_se_elimina_con_proyecto(preparado: tuple[Path, BorradorInforme]) -> None:
    ruta, borrador = preparado
    guardar_borrador_informe(ruta, borrador)
    assert eliminar_proyecto(ruta, borrador.proyecto_id)
    assert recuperar_borrador_informe(ruta, borrador.proyecto_id) is None


def test_genera_un_pdf_real(preparado: tuple[Path, BorradorInforme]) -> None:
    ruta, borrador = preparado
    pdf = generar_pdf_por_secciones(ruta, borrador)
    assert pdf.startswith(b"%PDF-")
    assert b"%%EOF" in pdf[-100:]
    assert len(pdf) > 2000


def test_pdf_solo_observaciones(preparado: tuple[Path, BorradorInforme]) -> None:
    ruta, borrador = preparado
    nota = replace(borrador.analisis[0], incluir_grafica=False)
    assert generar_pdf_por_secciones(ruta, replace(borrador, analisis=(nota,))).startswith(b"%PDF-")


def test_bloquea_png_que_falta(preparado: tuple[Path, BorradorInforme]) -> None:
    ruta, borrador = preparado
    item = replace(borrador.analisis[0], captura_id=None)
    with pytest.raises(ValueError, match="falta subir"):
        generar_pdf_por_secciones(ruta, replace(borrador, analisis=(item,)))


def test_bloquea_informe_sin_contenido(preparado: tuple[Path, BorradorInforme]) -> None:
    ruta, borrador = preparado
    item = replace(borrador.analisis[0], incluir_grafica=False, incluir_observacion=False)
    with pytest.raises(ValueError, match="Incluye al menos"):
        generar_pdf_por_secciones(ruta, replace(borrador, analisis=(item,)))


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("modulo", "calidad"),
        ("grafica", "Gráfica inexistente"),
        ("captura_id", True),
        ("incluir_grafica", 1),
        ("clave", "../../ruta"),
    ],
)
def test_rechaza_analisis_invalidos(
    preparado: tuple[Path, BorradorInforme], campo: str, valor: object
) -> None:
    _, borrador = preparado
    item = replace(borrador.analisis[0], **{campo: valor})
    with pytest.raises(ValueError):
        validar_borrador(replace(borrador, analisis=(item,)))


def test_fechas_y_claves_unicas(preparado: tuple[Path, BorradorInforme]) -> None:
    _, borrador = preparado
    with pytest.raises(ValueError, match="fecha"):
        validar_borrador(replace(borrador, fecha="ayer"))
    with pytest.raises(ValueError, match="distintos"):
        validar_borrador(replace(borrador, analisis=(borrador.analisis[0],) * 2))


def test_no_guarda_proyecto_que_no_existe(preparado: tuple[Path, BorradorInforme]) -> None:
    ruta, borrador = preparado
    with pytest.raises(ValueError, match="no existe"):
        guardar_borrador_informe(ruta, replace(borrador, proyecto_id=999))
