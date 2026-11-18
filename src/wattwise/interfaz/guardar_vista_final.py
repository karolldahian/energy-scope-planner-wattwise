"""Guardado directo de vistas reproducibles desde los paneles existentes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from wattwise.dominio.inventario import analizar_inventario
from wattwise.dominio.motores import analizar_motores
from wattwise.dominio.vistas import validar_vista
from wattwise.infraestructura.archivos_proyecto import listar_archivos, recuperar_archivo
from wattwise.infraestructura.lector_inventario_excel import leer_inventario_excel
from wattwise.infraestructura.lector_mediciones_detalladas import leer_mediciones_detalladas
from wattwise.infraestructura.lector_motores_excel import leer_motores_excel
from wattwise.infraestructura.vistas_sqlite import guardar_vista, listar_vistas


def _registros_originales(
    tipo: str,
    contenido: bytes,
    nombre: str,
) -> list[dict[str, object]]:
    """Reconstruye las filas con los lectores oficiales de WattWise."""
    if tipo == "mediciones":
        if not nombre.lower().endswith(".xlsx"):
            raise ValueError("Las vistas de mediciones requieren Excel detallado.")
        return leer_mediciones_detalladas(contenido, nombre).registros

    from wattwise.interfaz.paneles_completos import (
        registros_inventario,
        registros_motores,
    )

    if tipo == "inventario":
        registros = leer_inventario_excel(contenido, nombre)
        return registros_inventario(analizar_inventario(registros))

    if tipo == "motores":
        registros = leer_motores_excel(contenido, nombre)
        return registros_motores(analizar_motores(registros))

    raise ValueError("Módulo de vistas no admitido.")


def _buscar_original(
    ruta: Path,
    proyecto_id: int,
    tipo: str,
    registros: list[dict[str, object]],
) -> int | None:
    """Elige solamente una fuente con las mismas filas completas."""
    for archivo in listar_archivos(ruta, proyecto_id, tipo):
        try:
            _origen, contenido = recuperar_archivo(
                ruta,
                proyecto_id,
                archivo.id,
            )

            if (
                _registros_originales(
                    tipo,
                    contenido,
                    archivo.nombre,
                )
                == registros
            ):
                return archivo.id

        except (ValueError, OSError, sqlite3.Error):
            continue

    return None


def mostrar_guardar_analisis_en_vistas(
    ruta: Path,
    tipo: str,
    registros_completos: list[dict[str, object]],
    configuracion: dict[str, object],
) -> None:
    """Guarda la vista sin cambiar gráfica, KPI ni tabla CSV."""
    import streamlit as st

    st.divider()
    proyecto_id = st.session_state.get("wattwise_proyecto_id")

    if type(proyecto_id) is not int or proyecto_id <= 0:
        st.info("Selecciona un proyecto activo para guardar este análisis en Vistas.")
        return

    grafica = str(configuracion.get("grafica", "Análisis"))
    titulo = st.text_input(
        "Nombre de la vista",
        value=grafica[:120],
        max_chars=120,
        key=f"ww_nombre_vista_{proyecto_id}_{tipo}_{grafica}",
    ).strip()

    if not st.button(
        "Guardar análisis en Vistas",
        key=f"ww_guardar_vistas_{tipo}",
    ):
        return

    if not titulo:
        st.warning("Escribe un nombre para la vista antes de guardarla.")
        return

    try:
        normalizada = validar_vista(tipo, configuracion)

        archivo_id = _buscar_original(
            ruta,
            proyecto_id,
            tipo,
            registros_completos,
        )

        if archivo_id is None:
            st.warning(
                "Guarda primero el archivo original de este análisis "
                "en el proyecto activo. No se guardó una vista sin "
                "origen verificable."
            )
            return

        for existente in listar_vistas(ruta, proyecto_id):
            if (
                existente.archivo_id == archivo_id
                and existente.tipo == tipo
                and existente.configuracion == normalizada
                and existente.titulo == titulo
            ):
                st.info("Este análisis ya está guardado en Vistas. Puedes abrirlo allí.")
                return

        guardar_vista(
            ruta,
            proyecto_id,
            archivo_id,
            tipo,
            titulo,
            normalizada,
        )

        st.success(
            "Análisis guardado en Vistas. Allí recuperarás la gráfica, "
            "los indicadores, las observaciones y la tabla "
            "con descarga CSV."
        )

    except (ValueError, TypeError, OSError, sqlite3.Error) as error:
        st.error(f"No se pudo guardar el análisis en Vistas: {error}")
