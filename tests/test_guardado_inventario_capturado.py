"""Comprueba procedencia y reversión de vistas capturadas de Inventarios."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from wattwise.interfaz import guardado_inventario_capturado as modulo
from wattwise.interfaz.echarts_capturable import CapturaEcharts


def _argumentos() -> dict[str, Any]:
    """Prepara una captura mínima para comprobar el flujo de guardado."""
    return {
        "ruta": Path("pruebas.sqlite3"),
        "proyecto_id": 4,
        "archivo_id": 8,
        "resultado": object(),
        "grafica": "Pareto por tipo de carga",
        "filtros": {
            "frontera": "Todos",
            "area": "Todos",
            "tipo_carga": "Todos",
            "equipo": "Todos",
        },
        "opciones": {
            "linea_barras": True,
            "acumulado": True,
            "umbral_80": True,
        },
        "captura": CapturaEcharts(
            estado_echarts={"series": [{"type": "bar", "data": [2]}]},
            imagen_png=b"imagen",
            nombre_archivo="Pareto",
        ),
        "titulo": "Pareto de inventario",
    }


@pytest.fixture
def dependencias(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[tuple[Any, ...]]]:
    """Aísla el orquestador de la base de datos para validar llamadas."""
    llamadas: dict[str, list[tuple[Any, ...]]] = {
        "vista": [],
        "captura": [],
        "eliminacion": [],
        "notas": [],
    }
    monkeypatch.setattr(modulo, "registros_inventario", lambda _: [{"id_fila": 2}])
    monkeypatch.setattr(modulo, "_contenido_coincide", lambda *_: True)

    def guardar(*args: Any) -> int:
        llamadas["vista"].append(args)
        return 17

    def capturar(*args: Any) -> None:
        llamadas["captura"].append(args)

    def borrar(*args: Any) -> bool:
        llamadas["eliminacion"].append(args)
        return True

    def notas(*args: Any) -> list[object]:
        llamadas["notas"].append(args)
        return []

    monkeypatch.setattr(modulo, "guardar_vista", guardar)
    monkeypatch.setattr(modulo, "guardar_captura_vista", capturar)
    monkeypatch.setattr(modulo, "eliminar_vista", borrar)
    monkeypatch.setattr(modulo, "listar_observaciones", notas)
    return llamadas


def test_guarda_vista_y_captura_con_mismo_proyecto(dependencias: dict[str, Any]) -> None:
    """Guarda estado interactivo e imagen vinculados a la misma vista."""
    vista_id = modulo.guardar_vista_inventario_capturada(**_argumentos())
    assert vista_id == 17
    llamada_vista = dependencias["vista"][0]
    assert llamada_vista[1:4] == (4, 8, "inventario")
    assert llamada_vista[5]["version"] == 1
    assert llamada_vista[5]["filtros"]["area"] == "Todos"
    llamada_captura = dependencias["captura"][0]
    assert llamada_captura[1:3] == (4, 17)
    assert llamada_captura[3]["series"][0]["data"] == [2]
    assert llamada_captura[4] == b"imagen"
    assert llamada_captura[5] == []
    assert dependencias["eliminacion"] == []


def test_original_diferente_bloquea_guardado(
    monkeypatch: pytest.MonkeyPatch, dependencias: dict[str, Any]
) -> None:
    """Impide vincular una vista a un Excel que no produjo sus registros."""
    monkeypatch.setattr(modulo, "_contenido_coincide", lambda *_: False)
    with pytest.raises(ValueError, match="no coincide"):
        modulo.guardar_vista_inventario_capturada(**_argumentos())
    assert dependencias["vista"] == []


def test_fallo_captura_revierte_vista(
    monkeypatch: pytest.MonkeyPatch, dependencias: dict[str, Any]
) -> None:
    """No conserva una vista reproducible sin su captura requerida."""

    def fallo(*_args: Any) -> None:
        raise sqlite3.IntegrityError("Fallo simulado")

    monkeypatch.setattr(modulo, "guardar_captura_vista", fallo)
    with pytest.raises(sqlite3.IntegrityError, match="Fallo simulado"):
        modulo.guardar_vista_inventario_capturada(**_argumentos())
    assert dependencias["eliminacion"][0][1:] == (4, 17)


@pytest.mark.parametrize("id_invalido", [0, -1, True, "7"])
def test_identificadores_invalidos(id_invalido: object, dependencias: dict[str, Any]) -> None:
    """No se aceptan IDs que puedan mezclar proyectos."""
    argumentos = _argumentos()
    argumentos["proyecto_id"] = id_invalido
    with pytest.raises(ValueError, match="proyecto"):
        modulo.guardar_vista_inventario_capturada(**argumentos)
    assert dependencias["vista"] == []


def test_opciones_no_validas_no_guardan(dependencias: dict[str, Any]) -> None:
    """Rechaza opciones ajenas al contrato de inventarios."""
    argumentos = _argumentos()
    argumentos["opciones"]["umbral_80"] = "sí"
    with pytest.raises(ValueError, match="opciones"):
        modulo.guardar_vista_inventario_capturada(**argumentos)
    assert dependencias["vista"] == []


def test_origenes_coincidentes_no_inventa_archivos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Solo ofrece Excel que se reabrieron y coincidieron con el análisis."""
    archivos = [SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)]
    monkeypatch.setattr(modulo, "registros_inventario", lambda _: [{"fila": 1}])
    monkeypatch.setattr(modulo, "listar_archivos", lambda *_: archivos)

    def coincidencia(_ruta: Path, _proyecto: int, id_archivo: int, _filas: object) -> bool:
        if id_archivo == 1:
            raise ValueError("Excel corrupto")
        return id_archivo == 3

    monkeypatch.setattr(modulo, "_contenido_coincide", coincidencia)
    encontrados = modulo.originales_coincidentes(Path("pruebas.sqlite3"), 4, object())
    assert [archivo.id for archivo in encontrados] == [3]


def test_tipo_ajeno_no_se_asocia_a_inventario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No permite vincular archivos de Motores como origen de Inventarios."""
    monkeypatch.setattr(
        modulo,
        "recuperar_archivo",
        lambda *_: (SimpleNamespace(tipo="motores", nombre="motores.xlsx"), b"xls"),
    )
    assert not modulo._contenido_coincide(Path("base.sqlite3"), 4, 8, [{"id_fila": 2}])


def test_nombre_invalido_no_guarda(dependencias: dict[str, Any]) -> None:
    """Impide registrar títulos vacíos o excesivos."""
    for titulo in ("   ", "x" * 121):
        argumentos = _argumentos()
        argumentos["titulo"] = titulo
        with pytest.raises(ValueError, match="nombre"):
            modulo.guardar_vista_inventario_capturada(**argumentos)
    assert dependencias["vista"] == []


def test_contexto_notas_conservado(
    monkeypatch: pytest.MonkeyPatch, dependencias: dict[str, Any]
) -> None:
    """Adjunta exactamente las notas del gráfico y filtros actuales."""
    nota = SimpleNamespace(texto="Nota original", mostrar_en_informe=False)
    monkeypatch.setattr(modulo, "listar_observaciones", lambda *_: [nota])
    argumentos = _argumentos()
    modulo.guardar_vista_inventario_capturada(**argumentos)
    assert dependencias["captura"][0][5] == [nota]
