"""Regresion de calidad temporal y comparacion con alcance confirmado."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from wattwise.dominio.calidad_mediciones import auditar_mediciones
from wattwise.dominio.comparacion import comparar_potencias, grafico_comparacion
from wattwise.infraestructura.archivos_proyecto import guardar_archivo
from wattwise.infraestructura.comparaciones_sqlite import (
    guardar_comparacion,
    listar_comparaciones,
)
from wattwise.infraestructura.proyectos_sqlite import crear_proyecto, eliminar_proyecto

JUSTIFICACION = (
    "El plano unifilar confirma que este medidor alimenta exclusivamente las cargas seleccionadas."
)


def _inventario() -> list[dict[str, object]]:
    return [
        {
            "area": "Hacienda",
            "equipo": "Bomba",
            "potencia_instalada_kw": 10,
            "cantidad": 2,
        },
        {
            "area": "Hacienda",
            "equipo": "Luz",
            "potencia_instalada_kw": 5,
            "cantidad": 5,
        },
    ]


def _mediciones() -> list[dict[str, object]]:
    inicio = datetime(2026, 1, 1, 9)
    return [
        {
            "fecha_hora": inicio,
            "frontera": "Parque",
            "area": "Hacienda",
            "punto_medicion": "PM-01",
            "p_total_kw": 2.0,
        },
        {
            "fecha_hora": inicio + timedelta(minutes=15),
            "frontera": "Parque",
            "area": "Hacienda",
            "punto_medicion": "PM-01",
            "p_total_kw": 9.0,
        },
        {
            "fecha_hora": inicio + timedelta(minutes=30),
            "frontera": "Parque",
            "area": "Hacienda",
            "punto_medicion": "PM-01",
            "p_total_kw": None,
        },
    ]


def _comparar(
    *,
    inventario=None,
    mediciones=None,
    confirmado=True,
    descripcion=JUSTIFICACION,
):
    return comparar_potencias(
        _inventario() if inventario is None else inventario,
        _mediciones() if mediciones is None else mediciones,
        alcance_confirmado=confirmado,
        justificacion_alcance=descripcion,
    )


def test_maximo_es_pico_no_suma_de_puntos() -> None:
    resultado = _comparar()
    assert resultado.potencia_instalada_kw == 15
    assert resultado.potencia_maxima_medida_kw == 9
    assert resultado.relacion_pct == 60
    assert resultado.equipos_inventariados == 7
    assert resultado.muestras_validas == 2
    assert resultado.muestras_totales == 3


def test_grafico_comparacion_tiene_dos_barras_echarts() -> None:
    grafico = grafico_comparacion(_comparar())
    assert grafico["series"][0]["data"] == [15, 9]
    assert grafico["toolbox"]["feature"]["saveAsImage"]["type"] == "png"


def test_bloquea_sin_confirmacion() -> None:
    with pytest.raises(ValueError, match="confirmar"):
        _comparar(confirmado=False)


@pytest.mark.parametrize("descripcion", ["", "Cubre zona", "a" * 501])
def test_bloquea_justificacion_insuficiente(descripcion: str) -> None:
    with pytest.raises(ValueError, match="15 a 500"):
        _comparar(descripcion=descripcion)


def test_bloquea_inventario_vacio() -> None:
    with pytest.raises(ValueError, match="carga"):
        _comparar(inventario=[])


def test_bloquea_mediciones_vacias() -> None:
    with pytest.raises(ValueError, match="mediciones"):
        _comparar(mediciones=[])


def test_bloquea_puntos_distintos() -> None:
    datos = _mediciones()
    datos[1]["punto_medicion"] = "PM-02"
    with pytest.raises(ValueError, match="mezclar"):
        _comparar(mediciones=datos)


def test_bloquea_fronteras_distintas() -> None:
    datos = _mediciones()
    datos[1]["frontera"] = "Otra"
    with pytest.raises(ValueError, match="mezclar"):
        _comparar(mediciones=datos)


def test_bloquea_punto_desconocido() -> None:
    datos = _mediciones()
    for dato in datos:
        dato["punto_medicion"] = None
    with pytest.raises(ValueError, match="identificado"):
        _comparar(mediciones=datos)


def test_no_usa_fases_como_total() -> None:
    datos = _mediciones()
    for dato in datos:
        dato["p_total_kw"] = None
        dato["p_l1_kw"] = 4
    with pytest.raises(ValueError, match="potencia activa total"):
        _comparar(mediciones=datos)


def test_potencia_instalada_cero_no_divide() -> None:
    inventario = [{"cantidad": 1, "potencia_instalada_kw": 0}]
    resultado = _comparar(inventario=inventario)
    assert resultado.relacion_pct is None


def test_potencia_negativa_conserva_advertencia() -> None:
    datos = _mediciones()
    datos[0]["p_total_kw"] = -2
    resultado = _comparar(mediciones=datos)
    assert any("negativas" in aviso for aviso in resultado.advertencias)


def test_pico_mayor_que_instalada_no_diagnostica_falla() -> None:
    datos = _mediciones()
    datos[1]["p_total_kw"] = 30
    resultado = _comparar(mediciones=datos)
    assert resultado.relacion_pct == 200
    assert any("revisar" in aviso for aviso in resultado.advertencias)


def test_cantidad_invalida_no_se_acepta() -> None:
    inventario = [{"cantidad": True, "potencia_instalada_kw": 10}]
    with pytest.raises(ValueError, match="invalidas"):
        _comparar(inventario=inventario)


def test_fecha_con_zona_se_bloquea() -> None:
    datos = _mediciones()
    datos[0]["fecha_hora"] = datos[0]["fecha_hora"].replace(tzinfo=UTC)
    with pytest.raises(ValueError, match="locales"):
        _comparar(mediciones=datos)


def test_calidad_conserva_cero_y_detecta_huecos() -> None:
    datos = _mediciones()
    datos[0]["p_total_kw"] = 0
    datos.append(dict(datos[1], fecha_hora=datetime(2026, 1, 1, 13), p_total_kw=3))
    resultado = auditar_mediciones(datos)
    assert resultado.total_registros == 4
    assert resultado.huecos_largos == 1
    assert resultado.variables[0].validos == 3
    assert resultado.variables[0].faltantes == 1


def test_calidad_duplicados_sin_contarlos_dos_veces() -> None:
    datos = _mediciones()
    datos.append(dict(datos[0]))
    resultado = auditar_mediciones(datos)
    assert resultado.timestamps_duplicados == 1
    assert resultado.fechas_distintas == 3


def test_calidad_un_instante_es_permitido() -> None:
    resultado = auditar_mediciones(_mediciones()[:1])
    assert resultado.intervalo_mediano_min is None
    assert any("unico" in aviso.lower() for aviso in resultado.advertencias)


def test_calidad_lista_vacia_no_inventa_resultado() -> None:
    with pytest.raises(ValueError, match="No hay"):
        auditar_mediciones([])


def test_calidad_fecha_invalida_no_pasa() -> None:
    datos = _mediciones()
    datos[0]["fecha_hora"] = "2026-01-01"
    with pytest.raises(ValueError, match="fechas"):
        auditar_mediciones(datos)


def _archivos(tmp_path: Path):
    ruta = tmp_path / "comparaciones.sqlite3"
    proyecto = crear_proyecto(ruta, "Parque")
    inventario = guardar_archivo(ruta, proyecto, "inventario", "01.xlsx", b"inventario")
    mediciones = guardar_archivo(ruta, proyecto, "mediciones", "02.xlsx", b"mediciones")
    return ruta, proyecto, inventario, mediciones


def test_persistencia_guarda_resultado_y_hash(tmp_path: Path) -> None:
    ruta, proyecto, inventario, mediciones = _archivos(tmp_path)
    id_comparacion = guardar_comparacion(
        ruta, proyecto, inventario, mediciones, _comparar(), ("Hacienda",)
    )
    registro = listar_comparaciones(ruta, proyecto)[0]
    assert registro.id == id_comparacion
    assert registro.resultado["potencia_maxima_medida_kw"] == 9
    assert registro.areas == ("Hacienda",)
    assert len(registro.sha256_inventario) == 64
    assert len(registro.sha256_mediciones) == 64
    assert registro.resultado["alcance_confirmado"] == JUSTIFICACION


def test_persistencia_aisla_proyectos(tmp_path: Path) -> None:
    ruta, proyecto, inventario, mediciones = _archivos(tmp_path)
    otro = crear_proyecto(ruta, "Otro")
    guardar_comparacion(ruta, proyecto, inventario, mediciones, _comparar(), ("Hacienda",))
    assert listar_comparaciones(ruta, otro) == []


def test_persistencia_bloquea_original_de_otro_proyecto(tmp_path: Path) -> None:
    ruta, proyecto, inventario, mediciones = _archivos(tmp_path)
    otro = crear_proyecto(ruta, "Otro")
    with pytest.raises(ValueError, match="no pertenece"):
        guardar_comparacion(ruta, otro, inventario, mediciones, _comparar(), ("Hacienda",))


def test_persistencia_bloquea_tipo_invertido(tmp_path: Path) -> None:
    ruta, proyecto, inventario, mediciones = _archivos(tmp_path)
    with pytest.raises(ValueError, match="no pertenece"):
        guardar_comparacion(ruta, proyecto, mediciones, inventario, _comparar(), ("Hacienda",))


@pytest.mark.parametrize(
    "areas",
    [(), ("",), ("Hacienda", ""), ["Hacienda"]],
)
def test_persistencia_bloquea_filtros_invalidos(tmp_path: Path, areas: object) -> None:
    ruta, proyecto, inventario, mediciones = _archivos(tmp_path)
    with pytest.raises(ValueError, match="areas"):
        guardar_comparacion(ruta, proyecto, inventario, mediciones, _comparar(), areas)


def test_persistencia_no_toca_originales(tmp_path: Path) -> None:
    ruta, proyecto, inventario, mediciones = _archivos(tmp_path)
    guardar_comparacion(ruta, proyecto, inventario, mediciones, _comparar(), ("Hacienda",))
    import sqlite3

    with sqlite3.connect(ruta) as conexion:
        contenido = conexion.execute(
            "SELECT contenido FROM archivos_originales WHERE id = ?",
            (inventario,),
        ).fetchone()[0]

    assert contenido == b"inventario"


def test_eliminar_proyecto_borra_comparaciones_en_cascada(tmp_path: Path) -> None:
    ruta, proyecto, inventario, mediciones = _archivos(tmp_path)
    guardar_comparacion(ruta, proyecto, inventario, mediciones, _comparar(), ("Hacienda",))
    assert eliminar_proyecto(ruta, proyecto)
    assert listar_comparaciones(ruta, proyecto) == []
