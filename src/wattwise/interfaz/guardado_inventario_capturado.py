"""Vincula capturas de inventario con su Excel original y notas verificadas."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from wattwise.dominio.inventario import analizar_inventario
from wattwise.infraestructura.archivos_proyecto import (
    ArchivoProyecto,
    listar_archivos,
    recuperar_archivo,
)
from wattwise.infraestructura.capturas_vistas_sqlite import guardar_captura_vista
from wattwise.infraestructura.lector_inventario_excel import leer_inventario_excel
from wattwise.infraestructura.observaciones_sqlite import listar_observaciones
from wattwise.infraestructura.vistas_sqlite import eliminar_vista, guardar_vista
from wattwise.interfaz.echarts_capturable import CapturaEcharts
from wattwise.interfaz.paneles_completos import registros_inventario


def _identificador(valor: object) -> int:
    """Exige identificadores positivos sin admitir booleanos."""
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError("Selecciona un proyecto y un archivo original válidos.")
    return valor


def _contenido_coincide(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int,
    registros_actuales: list[dict[str, object]],
) -> bool:
    """Reabre y revalida el archivo; compara todas las filas, sin filtros."""
    origen, contenido = recuperar_archivo(ruta, proyecto_id, archivo_id)
    if origen.tipo != "inventario":
        return False
    registros_excel = leer_inventario_excel(contenido, origen.nombre)
    resultado_origen = analizar_inventario(registros_excel)
    return registros_inventario(resultado_origen) == registros_actuales


def originales_coincidentes(
    ruta: Path,
    proyecto_id: int,
    resultado: object,
) -> list[ArchivoProyecto]:
    """Devuelve solo originales íntegros del proyecto con idénticos registros."""
    _identificador(proyecto_id)
    registros = registros_inventario(resultado)
    if not registros:
        return []
    candidatos = listar_archivos(ruta, proyecto_id, "inventario")
    compatibles: list[ArchivoProyecto] = []
    for candidato in candidatos:
        try:
            coincide = _contenido_coincide(ruta, proyecto_id, candidato.id, registros)
        except (ValueError, OSError, sqlite3.Error):
            # Un archivo dañado nunca puede utilizarse como procedencia.
            continue
        if coincide:
            compatibles.append(candidato)
    return compatibles


def _validar_configuracion(
    grafica: str,
    filtros: dict[str, str],
    opciones: dict[str, bool],
    titulo: str,
) -> None:
    """Comprueba los campos originales del contrato de vistas de inventario."""
    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 120:
        raise ValueError("El nombre de la vista debe tener entre 1 y 120 caracteres.")
    if not isinstance(grafica, str) or not grafica.strip():
        raise ValueError("La gráfica seleccionada no es válida.")
    filtros_esperados = {"frontera", "area", "tipo_carga", "equipo"}
    if not isinstance(filtros, dict) or set(filtros) != filtros_esperados:
        raise ValueError("Los filtros del inventario están incompletos.")
    if any(not isinstance(valor, str) for valor in filtros.values()):
        raise ValueError("Los filtros del inventario deben contener texto.")
    opciones_esperadas = {"linea_barras", "acumulado", "umbral_80"}
    if not isinstance(opciones, dict) or set(opciones) != opciones_esperadas:
        raise ValueError("Las opciones de visualización no son válidas.")
    if any(not isinstance(valor, bool) for valor in opciones.values()):
        raise ValueError("Las opciones de visualización no son válidas.")


def guardar_vista_inventario_capturada(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int,
    resultado: object,
    grafica: str,
    filtros: dict[str, str],
    opciones: dict[str, bool],
    captura: CapturaEcharts,
    titulo: str,
) -> int:
    """Persiste la vista, PNG y notas; revierte la vista si falla la captura."""
    _identificador(proyecto_id)
    _identificador(archivo_id)
    if not isinstance(captura, CapturaEcharts):
        raise ValueError("Se necesita una captura real de la gráfica visible.")
    _validar_configuracion(grafica, filtros, opciones, titulo)

    registros = registros_inventario(resultado)
    if not registros:
        raise ValueError("No hay registros de inventario para guardar.")
    if not _contenido_coincide(ruta, proyecto_id, archivo_id, registros):
        raise ValueError(
            "El Excel guardado no coincide con el inventario que se está mostrando. "
            "Guarda primero el original correcto en este proyecto."
        )

    configuracion: dict[str, object] = {
        "version": 1,
        "grafica": grafica,
        "filtros": dict(filtros),
        "opciones": dict(opciones),
    }
    notas = listar_observaciones(ruta, proyecto_id, "inventario", grafica, filtros)
    vista_id = guardar_vista(
        ruta, proyecto_id, archivo_id, "inventario", titulo.strip(), configuracion
    )
    try:
        guardar_captura_vista(
            ruta,
            proyecto_id,
            vista_id,
            captura.estado_echarts,
            captura.imagen_png,
            notas,
        )
    except (ValueError, OSError, sqlite3.Error):
        # Evita una vista incompleta que parezca tener captura.
        eliminar_vista(ruta, proyecto_id, vista_id)
        raise
    return vista_id
