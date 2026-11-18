"""Pruebas de persistencia SQLite de metadatos de proyectos."""

from pathlib import Path

import pytest

from wattwise.infraestructura.proyectos_sqlite import (
    crear_proyecto,
    eliminar_proyecto,
    listar_proyectos,
)


def test_crear_y_reabrir_proyecto(tmp_path: Path) -> None:
    ruta = tmp_path / "data" / "proyectos.sqlite3"
    identificador = crear_proyecto(ruta, "Planta A", "Revision inicial")
    proyectos = listar_proyectos(ruta)
    assert len(proyectos) == 1
    assert proyectos[0].id == identificador
    assert proyectos[0].nombre == "Planta A"
    assert proyectos[0].descripcion == "Revision inicial"
    assert ruta.is_file()


def test_listar_vacio(tmp_path: Path) -> None:
    assert listar_proyectos(tmp_path / "vacia.sqlite3") == []


def test_orden_de_proyectos(tmp_path: Path) -> None:
    ruta = tmp_path / "orden.sqlite3"
    crear_proyecto(ruta, "Primero")
    crear_proyecto(ruta, "Segundo")
    assert [p.nombre for p in listar_proyectos(ruta)] == ["Segundo", "Primero"]


def test_eliminar_proyecto(tmp_path: Path) -> None:
    ruta = tmp_path / "borrar.sqlite3"
    identificador = crear_proyecto(ruta, "Temporal")
    assert eliminar_proyecto(ruta, identificador)
    assert not eliminar_proyecto(ruta, identificador)
    assert listar_proyectos(ruta) == []


@pytest.mark.parametrize("nombre", ["", "  ", "x" * 121, None, 12])
def test_rechaza_nombre_invalido(tmp_path: Path, nombre: object) -> None:
    with pytest.raises(ValueError):
        crear_proyecto(tmp_path / "invalido.sqlite3", nombre)


def test_rechaza_descripcion_larga(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        crear_proyecto(tmp_path / "invalido.sqlite3", "A", "x" * 1001)


@pytest.mark.parametrize("identificador", [0, -1, True, "1"])
def test_rechaza_identificador_invalido(tmp_path: Path, identificador: object) -> None:
    with pytest.raises(ValueError):
        eliminar_proyecto(tmp_path / "invalido.sqlite3", identificador)


def test_consultas_parametrizadas(tmp_path: Path) -> None:
    ruta = tmp_path / "segura.sqlite3"
    nombre = "Proyecto'); DROP TABLE proyectos;--"
    crear_proyecto(ruta, nombre)
    assert listar_proyectos(ruta)[0].nombre == nombre
    crear_proyecto(ruta, "Otro")
    assert len(listar_proyectos(ruta)) == 2
