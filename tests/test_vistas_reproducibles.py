"""Pruebas de contrato versionado, aislamiento de proyectos y reproduccion."""

from __future__ import annotations

import sqlite3
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from wattwise.dominio.vistas import validar_vista
from wattwise.infraestructura.archivos_proyecto import guardar_archivo
from wattwise.infraestructura.proyectos_sqlite import crear_proyecto, eliminar_proyecto
from wattwise.infraestructura.vistas_sqlite import (
    eliminar_vista,
    guardar_vista,
    listar_vistas,
)
from wattwise.interfaz.reproduccion_vistas import reconstruir_vista


def _config(tipo: str = "inventario") -> dict[str, object]:
    if tipo == "inventario":
        return {
            "version": 1,
            "grafica": "Pareto por equipo",
            "filtros": {
                "frontera": "Todos",
                "area": "A",
                "tipo_carga": "Todos",
                "equipo": "Todos",
            },
            "opciones": {"linea_barras": True, "acumulado": True, "umbral_80": False},
        }
    if tipo == "motores":
        return {
            "version": 1,
            "grafica": "Mapa de revision",
            "filtros": {"area": "A", "numero_fases": "Todos", "equipo": "Todos"},
            "opciones": {"mapa_variable": "relacion"},
        }
    return {
        "version": 1,
        "grafica": "Potencia activa (kW)",
        "filtros": {"frontera": "F", "area": "A", "punto_medicion": "PM1"},
        "opciones": {},
        "periodo": {"desde": "2026-01-01", "hasta": "2026-01-02"},
        "series": ["p_total_kw", "p_l1_kw"],
        "referencia": "p_total_kw",
        "marcas": ["P95"],
    }


def _fuentes(tmp_path: Path) -> tuple[Path, int, dict[str, int]]:
    ruta = tmp_path / "wattwise.sqlite3"
    proyecto = crear_proyecto(ruta, "Proyecto A")
    ids = {
        tipo: guardar_archivo(ruta, proyecto, tipo, f"{tipo}.xlsx", tipo.encode())
        for tipo in ("inventario", "motores", "mediciones")
    }
    return ruta, proyecto, ids


@pytest.mark.parametrize("tipo", ["inventario", "motores", "mediciones"])
def test_contrato_valido_canonico(tipo: str) -> None:
    configuracion = _config(tipo)
    normalizada = validar_vista(tipo, configuracion)
    assert normalizada == configuracion
    assert normalizada is not configuracion


@pytest.mark.parametrize("version", [0, 2, True, "1"])
def test_version_desconocida(version: object) -> None:
    configuracion = _config()
    configuracion["version"] = version
    with pytest.raises(ValueError, match="Version"):
        validar_vista("inventario", configuracion)


def test_bloquea_tipo_desconocido() -> None:
    with pytest.raises(ValueError, match="Tipo"):
        validar_vista("inventar", _config())


def test_bloquea_filtros_ajenos() -> None:
    config = _config()
    config["filtros"]["circuito"] = "inventado"
    with pytest.raises(ValueError, match="filtros"):
        validar_vista("inventario", config)


def test_bloquea_filtros_largos() -> None:
    config = _config()
    config["filtros"]["area"] = "x" * 121
    with pytest.raises(ValueError, match="filtro"):
        validar_vista("inventario", config)


def test_bloquea_opciones_no_booleanas() -> None:
    config = _config()
    config["opciones"]["acumulado"] = 1
    with pytest.raises(ValueError, match="Pareto"):
        validar_vista("inventario", config)


def test_bloquea_mapa_motor_desconocido() -> None:
    config = _config("motores")
    config["opciones"]["mapa_variable"] = "eficiencia"
    with pytest.raises(ValueError, match="mapa"):
        validar_vista("motores", config)


def test_bloquea_serie_fuera_del_grupo() -> None:
    config = _config("mediciones")
    config["series"] = ["v_total_v"]
    with pytest.raises(ValueError, match="series"):
        validar_vista("mediciones", config)


def test_bloquea_serie_duplicada() -> None:
    config = _config("mediciones")
    config["series"] = ["p_total_kw", "p_total_kw"]
    with pytest.raises(ValueError, match="series"):
        validar_vista("mediciones", config)


def test_bloquea_serie_objeto() -> None:
    config = _config("mediciones")
    config["series"] = [{"codigo": "p_total_kw"}]
    with pytest.raises(ValueError, match="series"):
        validar_vista("mediciones", config)


def test_bloquea_referencia_ausente() -> None:
    config = _config("mediciones")
    config["referencia"] = "p_l3_kw"
    with pytest.raises(ValueError, match="referencia"):
        validar_vista("mediciones", config)


def test_bloquea_periodo_invertido() -> None:
    config = _config("mediciones")
    config["periodo"] = {"desde": "2026-02-01", "hasta": "2026-01-01"}
    with pytest.raises(ValueError, match="inicio"):
        validar_vista("mediciones", config)


def test_bloquea_marca_desconocida() -> None:
    config = _config("mediciones")
    config["marcas"] = ["Pronostico"]
    with pytest.raises(ValueError, match="referencias"):
        validar_vista("mediciones", config)


def test_bloquea_campos_extra() -> None:
    config = _config("inventario")
    config["executar"] = "codigo"
    with pytest.raises(ValueError, match="campos"):
        validar_vista("inventario", config)


@pytest.mark.parametrize("tipo", ["inventario", "motores", "mediciones"])
def test_persistencia_redonda_por_tipo(tmp_path: Path, tipo: str) -> None:
    ruta, proyecto, fuentes = _fuentes(tmp_path)
    identificador = guardar_vista(
        ruta, proyecto, fuentes[tipo], tipo, "Vista segura", _config(tipo)
    )
    guardada = listar_vistas(ruta, proyecto)[0]
    assert guardada.id == identificador
    assert guardada.tipo == tipo
    assert guardada.configuracion == _config(tipo)
    assert len(guardada.sha256_archivo) == 64


def test_persistencia_no_modifica_configuracion_entrada(tmp_path: Path) -> None:
    ruta, proyecto, fuentes = _fuentes(tmp_path)
    original = _config("inventario")
    copia = deepcopy(original)
    guardar_vista(ruta, proyecto, fuentes["inventario"], "inventario", "A", original)
    assert original == copia


def test_persistencia_bloquea_archivo_de_otro_proyecto(tmp_path: Path) -> None:
    ruta, _, fuentes = _fuentes(tmp_path)
    segundo = crear_proyecto(ruta, "Otro")
    with pytest.raises(ValueError, match="no pertenece"):
        guardar_vista(ruta, segundo, fuentes["inventario"], "inventario", "A", _config())


def test_persistencia_bloquea_tipo_invertido(tmp_path: Path) -> None:
    ruta, proyecto, fuentes = _fuentes(tmp_path)
    with pytest.raises(ValueError, match="no pertenece"):
        guardar_vista(ruta, proyecto, fuentes["motores"], "inventario", "A", _config())


def test_persistencia_bloquea_titulo_vacio(tmp_path: Path) -> None:
    ruta, proyecto, fuentes = _fuentes(tmp_path)
    with pytest.raises(ValueError, match="titulo"):
        guardar_vista(ruta, proyecto, fuentes["inventario"], "inventario", " ", _config())


def test_persistencia_aislamiento(tmp_path: Path) -> None:
    ruta, proyecto, fuentes = _fuentes(tmp_path)
    otro = crear_proyecto(ruta, "Otro")
    guardar_vista(ruta, proyecto, fuentes["inventario"], "inventario", "Vista A", _config())
    assert listar_vistas(ruta, otro) == []


def test_persistencia_eliminar_protegido(tmp_path: Path) -> None:
    ruta, proyecto, fuentes = _fuentes(tmp_path)
    otro = crear_proyecto(ruta, "Otro")
    identidad = guardar_vista(ruta, proyecto, fuentes["inventario"], "inventario", "A", _config())
    assert not eliminar_vista(ruta, otro, identidad)
    assert eliminar_vista(ruta, proyecto, identidad)
    assert listar_vistas(ruta, proyecto) == []


def test_cascada_eliminar_proyecto(tmp_path: Path) -> None:
    ruta, proyecto, fuentes = _fuentes(tmp_path)
    guardar_vista(ruta, proyecto, fuentes["inventario"], "inventario", "A", _config())
    assert eliminar_proyecto(ruta, proyecto)
    assert listar_vistas(ruta, proyecto) == []


def test_cascada_eliminar_archivo(tmp_path: Path) -> None:
    ruta, proyecto, fuentes = _fuentes(tmp_path)
    guardar_vista(ruta, proyecto, fuentes["inventario"], "inventario", "A", _config())
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("PRAGMA foreign_keys = ON")
        conexion.execute(
            "DELETE FROM archivos_originales WHERE id = ?",
            (fuentes["inventario"],),
        )
    assert listar_vistas(ruta, proyecto) == []


def test_limite_de_vistas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import wattwise.infraestructura.vistas_sqlite as modulo

    ruta, proyecto, fuentes = _fuentes(tmp_path)
    monkeypatch.setattr(modulo, "MAXIMO_VISTAS_POR_PROYECTO", 1)
    guardar_vista(ruta, proyecto, fuentes["inventario"], "inventario", "A", _config())
    with pytest.raises(ValueError, match="limite"):
        guardar_vista(ruta, proyecto, fuentes["inventario"], "inventario", "B", _config())


def test_reconstruccion_inventario_filtro() -> None:
    registros = [
        {
            "frontera": "F",
            "area": "A",
            "tipo_carga": "Bombas",
            "equipo": "B",
            "cantidad": 2,
            "potencia_instalada_kw": 4.0,
        },
        {
            "frontera": "F",
            "area": "B",
            "tipo_carga": "Bombas",
            "equipo": "C",
            "cantidad": 1,
            "potencia_instalada_kw": 100.0,
        },
    ]
    resultado = reconstruir_vista("inventario", registros, _config())
    assert len(resultado.registros) == 1
    assert resultado.indicadores["potencia_kw"] == 4
    assert resultado.grafico["series"][0]["data"] == [4]


def _registros_medidos() -> list[dict[str, object]]:
    return [
        {
            "fecha_hora": datetime(2026, 1, 1, 8),
            "frontera": "F",
            "area": "A",
            "punto_medicion": "PM1",
            "p_total_kw": 0.0,
            "p_l1_kw": 1.0,
        },
        {
            "fecha_hora": datetime(2026, 1, 2, 8),
            "frontera": "F",
            "area": "A",
            "punto_medicion": "PM1",
            "p_total_kw": 4.0,
            "p_l1_kw": None,
        },
    ]


def test_reconstruccion_mediciones_conserva_cero_y_none() -> None:
    resultado = reconstruir_vista(
        "mediciones",
        _registros_medidos(),
        _config("mediciones"),
    )
    assert len(resultado.registros) == 2
    assert resultado.indicadores["p_total_kw"]["validos"] == 2
    assert resultado.indicadores["p_l1_kw"]["validos"] == 1
    assert resultado.grafico["series"][0]["data"][0][1] == 0.0
    assert resultado.grafico["series"][1]["data"][1][1] is None


def test_reconstruccion_mediciones_bloquea_puntos_mezclados() -> None:
    registros = _registros_medidos()
    registros[1]["punto_medicion"] = "PM2"
    config = _config("mediciones")
    config["filtros"]["punto_medicion"] = "Todos"
    with pytest.raises(ValueError, match="mezclaria"):
        reconstruir_vista("mediciones", registros, config)


def test_reconstruccion_mediciones_bloquea_serie_ausente() -> None:
    registros = _registros_medidos()
    for fila in registros:
        fila["p_l1_kw"] = None
    with pytest.raises(ValueError, match="no tiene datos"):
        reconstruir_vista("mediciones", registros, _config("mediciones"))


def test_reconstruccion_no_inventa_filtros_desaparecidos() -> None:
    with pytest.raises(ValueError, match="no contiene registros"):
        reconstruir_vista("inventario", [{"area": "B"}], _config())
