"""Pruebas de integridad y persistencia de resultados por proyecto."""

from pathlib import Path

import pytest

from wattwise.infraestructura.analisis_sqlite import (
    guardar_analisis,
    listar_analisis,
)
from wattwise.infraestructura.proyectos_sqlite import (
    crear_proyecto,
    eliminar_proyecto,
)


def test_guardar_y_recuperar(tmp_path: Path) -> None:
    ruta = tmp_path / "proyectos.sqlite3"
    proyecto = crear_proyecto(ruta, "Planta A")
    identificador = guardar_analisis(ruta, proyecto, "inventario", "Cargas", {"potencia_kw": 5.4})
    registro = listar_analisis(ruta, proyecto)[0]
    assert registro.id == identificador
    assert registro.datos == {"potencia_kw": 5.4}
    assert registro.tipo == "inventario"


def test_separacion_entre_proyectos(tmp_path: Path) -> None:
    ruta = tmp_path / "proyectos.sqlite3"
    uno = crear_proyecto(ruta, "Uno")
    dos = crear_proyecto(ruta, "Dos")
    guardar_analisis(ruta, uno, "motores", "M1", {"corriente_a": 3})
    assert len(listar_analisis(ruta, uno)) == 1
    assert listar_analisis(ruta, dos) == []


def test_rechaza_proyecto_inexistente(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no existe"):
        guardar_analisis(tmp_path / "db.sqlite3", 20, "motores", "A", {"valor": 1})


def test_proyecto_eliminado_no_conserva_analisis(tmp_path: Path) -> None:
    ruta = tmp_path / "db.sqlite3"
    proyecto = crear_proyecto(ruta, "Temporal")
    guardar_analisis(ruta, proyecto, "mediciones", "M", {"valor": 1})
    assert eliminar_proyecto(ruta, proyecto)
    assert listar_analisis(ruta, proyecto) == []


@pytest.mark.parametrize("identificador", [0, -1, True, "1"])
def test_rechaza_id_invalido(tmp_path: Path, identificador: object) -> None:
    with pytest.raises(ValueError):
        listar_analisis(tmp_path / "db.sqlite3", identificador)


@pytest.mark.parametrize("tipo", ["", "otro", "INVENTARIO", None])
def test_rechaza_tipo(tmp_path: Path, tipo: object) -> None:
    ruta = tmp_path / "db.sqlite3"
    proyecto = crear_proyecto(ruta, "Uno")
    with pytest.raises(ValueError):
        guardar_analisis(ruta, proyecto, tipo, "A", {"valor": 1})


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), object()])
def test_rechaza_datos_no_json(tmp_path: Path, valor: object) -> None:
    ruta = tmp_path / "db.sqlite3"
    proyecto = crear_proyecto(ruta, "Uno")
    with pytest.raises(ValueError):
        guardar_analisis(ruta, proyecto, "motores", "A", {"valor": valor})


def test_limite_tamano(tmp_path: Path) -> None:
    ruta = tmp_path / "db.sqlite3"
    proyecto = crear_proyecto(ruta, "Uno")
    with pytest.raises(ValueError, match="512 KiB"):
        guardar_analisis(ruta, proyecto, "motores", "A", {"valor": "x" * 600_000})


def test_lista_anidada_valida(tmp_path: Path) -> None:
    ruta = tmp_path / "db.sqlite3"
    proyecto = crear_proyecto(ruta, "Uno")
    guardar_analisis(ruta, proyecto, "mediciones", "Serie", {"muestras": [1, 2.2, None]})
    assert listar_analisis(ruta, proyecto)[0].datos["muestras"] == [1, 2.2, None]
