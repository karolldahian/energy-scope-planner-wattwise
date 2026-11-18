"""Controles de captura reproducible para las cinco gráficas de Inventarios."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from wattwise.interfaz.echarts_capturable import (
    CapturaEcharts,
    mostrar_echarts_capturable,
)
from wattwise.interfaz.guardado_inventario_capturado import (
    guardar_vista_inventario_capturada,
    originales_coincidentes,
)

_PENDIENTE = "ww_inventario_vista_pendiente"
_FORMULARIO = "ww_inventario_vista_formulario"
_CONTADOR = "ww_inventario_vista_contador"


@dataclass(frozen=True, slots=True)
class SolicitudInventario:
    """Congela el origen y contexto exactos de una captura solicitada."""

    numero: int
    firma: str
    proyecto_id: int
    archivo_id: int
    grafica: str
    filtros: dict[str, str]
    opciones: dict[str, bool]
    titulo: str


def firma_inventario(
    proyecto_id: int,
    resultado: object,
    grafica: str,
    filtros: dict[str, str],
    opciones: dict[str, bool],
    grafico: dict[str, object],
) -> str:
    """Vincula una petición a proyecto, inventario completo y gráfica visible."""
    contenido = {
        "proyecto_id": proyecto_id,
        "origen": hashlib.sha256(repr(resultado).encode("utf-8")).hexdigest(),
        "grafica": grafica,
        "filtros": filtros,
        "opciones": opciones,
        "grafico": grafico,
    }
    serializado = json.dumps(
        contenido,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def mostrar_grafico_inventario_capturable(
    grafico: dict[str, object],
) -> CapturaEcharts | None:
    """Conserva el componente de captura y el estado interactivo real."""
    import streamlit as st

    pendiente = st.session_state.get(_PENDIENTE)
    solicitud = pendiente.numero if isinstance(pendiente, SolicitudInventario) else 0

    return mostrar_echarts_capturable(
        grafico,
        clave="inventario_completo",
        altura=570,
        solicitud_captura=solicitud,
    )


def _finalizar_pendiente(
    ruta: Path,
    resultado: object,
    firma: str,
    captura: CapturaEcharts | None,
) -> bool:
    """Descarta respuestas antiguas y registra únicamente capturas solicitadas."""
    import streamlit as st

    pendiente = st.session_state.get(_PENDIENTE)

    if not isinstance(pendiente, SolicitudInventario):
        return False

    if pendiente.firma != firma:
        st.session_state.pop(_PENDIENTE, None)
        st.warning("Cambió el inventario, proyecto o gráfico. La captura anterior se descartó.")
        return False

    if captura is None or captura.solicitud_captura != pendiente.numero:
        return True

    st.session_state.pop(_PENDIENTE, None)

    try:
        vista_id = guardar_vista_inventario_capturada(
            ruta=ruta,
            proyecto_id=pendiente.proyecto_id,
            archivo_id=pendiente.archivo_id,
            resultado=resultado,
            grafica=pendiente.grafica,
            filtros=pendiente.filtros,
            opciones=pendiente.opciones,
            captura=captura,
            titulo=pendiente.titulo,
        )
    except (ValueError, OSError, sqlite3.Error, RuntimeError) as error:
        st.error(f"No se pudo guardar la vista capturada: {error}")
    else:
        st.success(f"Vista #{vista_id} guardada con PNG, estado ECharts y notas.")

    return False


def _abrir_formulario(firma: str) -> bool:
    """Mantiene compatibilidad con el flujo anterior de formulario."""
    import streamlit as st

    if st.button("📌 Guardar como vista", key="ww_inv_abrir_vista"):
        st.session_state[_FORMULARIO] = firma

    return st.session_state.get(_FORMULARIO) == firma


def _solicitar_captura(
    proyecto_id: int,
    archivo_id: int,
    grafica: str,
    filtros: dict[str, str],
    opciones: dict[str, bool],
    firma: str,
    titulo: str,
) -> None:
    """Solicita una captura nueva y nunca reutiliza una respuesta anterior."""
    import streamlit as st

    anterior = st.session_state.get(_CONTADOR, 0)
    siguiente = anterior + 1 if type(anterior) is int and anterior >= 0 else 1

    st.session_state[_CONTADOR] = siguiente
    st.session_state[_PENDIENTE] = SolicitudInventario(
        numero=siguiente,
        firma=firma,
        proyecto_id=proyecto_id,
        archivo_id=archivo_id,
        grafica=grafica,
        filtros=dict(filtros),
        opciones=dict(opciones),
        titulo=titulo.strip(),
    )
    st.session_state.pop(_FORMULARIO, None)
    st.rerun()


def _formulario(
    ruta: Path,
    proyecto_id: int,
    resultado: object,
    grafica: str,
    filtros: dict[str, str],
    opciones: dict[str, bool],
    firma: str,
) -> None:
    """Conserva el formulario anterior para compatibilidad."""
    import streamlit as st

    try:
        candidatos = originales_coincidentes(
            ruta,
            proyecto_id,
            resultado,
        )
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No se pudieron verificar los Excel originales: {error}")
        return

    if not candidatos:
        st.info(
            "Primero conserva el Excel original de este inventario "
            "en el proyecto activo, desde 'Guardar archivo original "
            "en un proyecto'."
        )
        return

    etiquetas = {item.id: f"#{item.id} · {item.nombre}" for item in candidatos}
    indice = str(grafica).replace(" ", "_")

    archivo_id = st.selectbox(
        "Excel original verificado",
        list(etiquetas),
        format_func=lambda valor: etiquetas[valor],
        key=f"ww_inv_origen_{proyecto_id}_{indice}",
    )
    titulo = st.text_input(
        "Nombre de la vista",
        value=grafica,
        max_chars=120,
        key=f"ww_inv_titulo_{proyecto_id}_{indice}",
    )

    if st.button(
        "Confirmar y capturar vista",
        key="ww_inv_confirmar_vista",
    ):
        if not titulo.strip():
            st.warning("Escribe un nombre para la vista.")
            return

        _solicitar_captura(
            proyecto_id,
            archivo_id,
            grafica,
            filtros,
            opciones,
            firma,
            titulo,
        )


def mostrar_guardado_inventario(
    ruta: Path,
    resultado: object,
    grafica: str,
    filtros: dict[str, str],
    opciones: dict[str, bool],
    grafico: dict[str, object],
    captura: CapturaEcharts | None,
) -> None:
    """Guarda desde el final, manteniendo la captura ECharts existente."""
    import streamlit as st

    proyecto_id = st.session_state.get("wattwise_proyecto_id")

    if type(proyecto_id) is not int or proyecto_id <= 0:
        st.info("Selecciona un proyecto activo para guardar el análisis en Vistas.")
        st.session_state.pop(_PENDIENTE, None)
        st.session_state.pop(_FORMULARIO, None)
        return

    firma = firma_inventario(
        proyecto_id,
        resultado,
        grafica,
        filtros,
        opciones,
        grafico,
    )

    if _finalizar_pendiente(ruta, resultado, firma, captura):
        st.info("Capturando la gráfica actual para guardarla en Vistas…")
        if st.button(
            "Cancelar captura",
            key="ww_inv_cancelar_captura",
        ):
            st.session_state.pop(_PENDIENTE, None)
            st.rerun()
        return

    titulo = st.text_input(
        "Nombre de la vista",
        value=grafica[:120],
        max_chars=120,
        key=f"ww_inv_nombre_final_{proyecto_id}_{grafica}",
    ).strip()

    if not st.button(
        "Guardar análisis en Vistas",
        key="ww_inv_abrir_vista",
    ):
        return

    if not titulo:
        st.warning("Escribe un nombre para la vista antes de guardarla.")
        return

    try:
        candidatos = originales_coincidentes(
            ruta,
            proyecto_id,
            resultado,
        )
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No se pudo comprobar el Excel original: {error}")
        return

    if not candidatos:
        st.warning(
            "Guarda primero el Excel original de este inventario "
            "en el proyecto activo. La vista no se guarda sin una "
            "fuente que coincida."
        )
        return

    _solicitar_captura(
        proyecto_id,
        candidatos[0].id,
        grafica,
        filtros,
        opciones,
        firma,
        titulo,
    )
