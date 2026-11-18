"""Importacion y reapertura de originales archivados por proyecto."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from wattwise.infraestructura.archivos_proyecto import (
    guardar_archivo,
    listar_archivos,
    recuperar_archivo,
)


@dataclass(frozen=True, slots=True)
class FuenteArchivo:
    """Interfaz comun para archivos subidos y recuperados de SQLite."""

    name: str
    contenido: bytes
    guardado: bool = False

    @property
    def size(self) -> int:
        """Tamano real del archivo de origen."""
        return len(self.contenido)

    def getvalue(self) -> bytes:
        """Devuelve bytes originales sin transformacion."""
        return self.contenido


def _proyecto_activo() -> int | None:
    """Obtiene la selección de Proyectos; nunca usa otro proyecto implícito."""
    import streamlit as st

    proyecto_id = st.session_state.get("wattwise_proyecto_id")
    if type(proyecto_id) is not int or proyecto_id <= 0:
        st.info("Selecciona un proyecto de trabajo en Proyectos antes de cargar datos.")
        return None
    return proyecto_id


def seleccionar_fuente(ruta: Path, tipo: str, extensiones: list[str]) -> FuenteArchivo | None:
    """Carga o recupera exclusivamente originales del proyecto de trabajo."""
    import streamlit as st

    proyecto_id = _proyecto_activo()
    if proyecto_id is None:
        return None

    modo = st.radio(
        "Origen del archivo",
        ("Subir archivo", "Abrir archivo guardado"),
        key=f"fuente_modo_{tipo}_{proyecto_id}",
        horizontal=True,
    )
    if modo == "Subir archivo":
        archivo = st.file_uploader(
            "Seleccionar archivo",
            type=extensiones,
            key=f"fuente_subir_{tipo}_{proyecto_id}",
        )
        if archivo is None:
            return None
        try:
            contenido = archivo.getvalue()
            identificador = guardar_archivo(ruta, proyecto_id, tipo, archivo.name, contenido)
        except (ValueError, OSError, sqlite3.Error) as error:
            st.error(f"No se pudo conservar el archivo original: {error}")
            return None
        st.caption(f"Original conservado en este proyecto (archivo #{identificador}).")
        return FuenteArchivo(archivo.name, contenido, guardado=True)

    try:
        archivos = listar_archivos(ruta, proyecto_id, tipo)
        if not archivos:
            st.info("Este proyecto todavía no contiene archivos de este módulo.")
            return None
        opciones = {f"#{item.id} · {item.nombre}": item.id for item in archivos}
        etiqueta = st.selectbox(
            "Archivo original",
            list(opciones),
            key=f"fuente_archivo_{tipo}_{proyecto_id}",
        )
        item, contenido = recuperar_archivo(ruta, proyecto_id, opciones[etiqueta])
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No se pudo abrir el archivo guardado: {error}")
        return None
    st.caption(f"Original recuperado: {item.nombre} · SHA-256 verificado.")
    return FuenteArchivo(item.nombre, contenido, guardado=True)


def mostrar_guardado_original(ruta: Path, tipo: str, fuente: FuenteArchivo) -> None:
    """Mantiene la integración existente sin añadir formularios de guardado."""
    import streamlit as st

    if fuente.guardado:
        return
    proyecto_id = _proyecto_activo()
    if proyecto_id is None:
        return
    try:
        guardar_archivo(ruta, proyecto_id, tipo, fuente.name, fuente.getvalue())
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No se pudo conservar el archivo original: {error}")
        st.stop()


def mostrar_originales_proyecto(ruta: Path, proyecto_id: int) -> None:
    """Lista y permite descargar los bytes originales del proyecto elegido."""
    import pandas as pd
    import streamlit as st

    st.subheader("Archivos originales del proyecto")
    try:
        originales = listar_archivos(ruta, proyecto_id)
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No se pudieron consultar los originales: {error}")
        return
    if not originales:
        st.info("Este proyecto todavía no contiene archivos originales.")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": item.id,
                    "Tipo": item.tipo,
                    "Nombre": item.nombre,
                    "Tamaño (KiB)": round(item.tamano_bytes / 1024, 2),
                    "Fecha UTC": item.creado_utc,
                }
                for item in originales
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    opciones = {f"#{item.id} · {item.tipo} · {item.nombre}": item.id for item in originales}
    elegido = st.selectbox("Original para descargar", list(opciones), key="original_descarga")
    try:
        metadatos, contenido = recuperar_archivo(ruta, proyecto_id, opciones[elegido])
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No se pudo recuperar el archivo: {error}")
        return
    mime = (
        "text/csv"
        if metadatos.nombre.lower().endswith(".csv")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.download_button(
        "Descargar original íntegro",
        data=contenido,
        file_name=metadatos.nombre,
        mime=mime,
        key="descargar_original_proyecto",
    )
