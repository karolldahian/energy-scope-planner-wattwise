"""Permite generar PDF descriptivo y PDF con capturas seleccionadas."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from wattwise.infraestructura.analisis_sqlite import AnalisisGuardado, listar_analisis
from wattwise.infraestructura.capturas_sqlite import (
    CapturaGrafica,
    eliminar_captura,
    guardar_captura,
    listar_capturas,
    recuperar_captura,
)
from wattwise.infraestructura.informe_graficas_pdf import generar_informe_graficas_pdf
from wattwise.infraestructura.informes_pdf import generar_informe_pdf
from wattwise.infraestructura.proyectos_sqlite import Proyecto, listar_proyectos


def _seleccionar_proyecto(ruta: Path) -> Proyecto | None:
    """Elige un proyecto existente antes de manipular capturas e informes."""
    import streamlit as st

    proyectos = listar_proyectos(ruta)
    if not proyectos:
        st.info("Crea un proyecto para preparar un informe.")
        return None
    opciones = {f"{item.id} - {item.nombre}": item for item in proyectos}
    seleccionado = st.selectbox("Proyecto", list(opciones), key="informe_proyecto")
    return opciones[seleccionado]


def _seleccionar_analisis(ruta: Path, proyecto_id: int) -> AnalisisGuardado | None:
    """Admite capturas de proyectos aun cuando no exista resumen JSON guardado."""
    import streamlit as st

    analisis = listar_analisis(ruta, proyecto_id)
    opciones: dict[str, AnalisisGuardado | None] = {
        "Sin análisis guardado (solo capturas del proyecto)": None
    }
    opciones.update({f"#{item.id} · {item.titulo} ({item.tipo})": item for item in analisis})
    elegido = st.selectbox("Análisis de referencia", list(opciones), key="informe_analisis")
    return opciones[elegido]


def _mostrar_pdf_descriptivo(proyecto: Proyecto, analisis: AnalisisGuardado | None) -> None:
    """Conserva la exportacion PDF descriptiva que ya existia."""
    import streamlit as st

    if analisis is None:
        st.caption("Selecciona un análisis guardado para generar el PDF descriptivo.")
        return
    with st.expander("PDF descriptivo de resultados guardados"):
        origen = st.selectbox(
            "Origen de datos",
            ["No verificado", "Datos de ensayo", "Datos declarados"],
            key="informe_origen",
        )
        incluir_tabla = st.checkbox("Incluir tabla de registros", value=True, key="informe_tabla")
        maximo_filas = st.number_input(
            "Máximo de registros en el PDF",
            min_value=1,
            max_value=50,
            value=20,
            key="informe_maximo",
        )
        observaciones = st.text_area(
            "Observaciones del informe descriptivo",
            max_chars=2000,
            key="informe_observaciones",
        )
        seleccion = (
            f"{proyecto.id}|{analisis.id}|{origen}|{incluir_tabla}|{maximo_filas}|{observaciones}"
        )
        clave = hashlib.sha256(seleccion.encode("utf-8")).hexdigest()[:20]
        if st.button("Generar PDF descriptivo", key="generar_informe_pdf"):
            try:
                st.session_state[f"pdf_{clave}"] = generar_informe_pdf(
                    proyecto.nombre,
                    analisis,
                    incluir_tabla=incluir_tabla,
                    maximo_filas=int(maximo_filas),
                    origen=origen,
                    observaciones=observaciones,
                )
                st.success("PDF descriptivo generado.")
            except (ValueError, OSError, ImportError) as error:
                st.error(f"No se pudo generar el informe: {error}")
        contenido = st.session_state.get(f"pdf_{clave}")
        if contenido is not None:
            st.download_button(
                "Descargar PDF descriptivo",
                data=contenido,
                mime="application/pdf",
                file_name=f"wattwise_informe_{proyecto.id}_{analisis.id}.pdf",
                key=f"descargar_informe_{clave}",
            )


def _guardar_png(ruta: Path, proyecto: Proyecto, analisis: AnalisisGuardado | None) -> None:
    """Guarda capturas exportadas manualmente desde la caja de ECharts."""
    import streamlit as st

    st.markdown("#### Añadir capturas PNG al proyecto")
    st.caption(
        "En cada gráfica ECharts pulsa Descargar PNG. Después selecciona "
        "aquí las imágenes descargadas. Las capturas no se generan automáticamente."
    )
    archivos = st.file_uploader(
        "Subir capturas PNG exportadas de ECharts",
        type=["png"],
        accept_multiple_files=True,
        key=f"informe_png_{proyecto.id}_{analisis.id if analisis else 0}",
    )
    descripcion = st.text_input(
        "Descripción de las capturas (opcional)",
        max_chars=500,
        key=f"informe_descripcion_png_{proyecto.id}_{analisis.id if analisis else 0}",
    )
    if st.button("Guardar las capturas en el proyecto", key="informe_guardar_png"):
        if not archivos:
            st.warning("Selecciona al menos una imagen PNG.")
            return
        guardadas = 0
        for archivo in archivos:
            try:
                guardar_captura(
                    ruta,
                    proyecto.id,
                    analisis.id if analisis else None,
                    archivo.name,
                    descripcion,
                    archivo.getvalue(),
                )
                guardadas += 1
            except (ValueError, OSError, sqlite3.Error) as error:
                st.error(f"{archivo.name}: {error}")
        if guardadas:
            st.success(f"{guardadas} capturas conservadas o reconocidas como duplicadas.")


def _elegir_capturas(
    ruta: Path, proyecto_id: int, analisis: AnalisisGuardado | None
) -> list[CapturaGrafica]:
    """Ofrece solo capturas del proyecto sin mezclar analisis diferentes."""
    import streamlit as st

    capturas = listar_capturas(ruta, proyecto_id)
    asociacion = None if analisis is None else analisis.id
    disponibles = [captura for captura in capturas if captura.analisis_id in (None, asociacion)]
    if analisis is None:
        disponibles = [captura for captura in disponibles if captura.analisis_id is None]
    if not disponibles:
        st.info("Todavía no hay capturas disponibles para este informe.")
        return []
    opciones = {
        f"#{captura.id} · {captura.nombre} ({captura.tamano_bytes // 1024} KiB)": captura
        for captura in disponibles
    }
    with st.expander("Vista previa de las capturas guardadas"):
        vista = st.selectbox("Ver captura", list(opciones), key=f"informe_vista_png_{proyecto_id}")
        metadatos, imagen = recuperar_captura(ruta, proyecto_id, opciones[vista].id)
        st.image(imagen, caption=metadatos.descripcion or metadatos.nombre)
        st.caption(f"SHA-256: {metadatos.sha256}")
    elegidos = st.multiselect(
        "Selecciona hasta 12 gráficas para incluir",
        list(opciones),
        key=f"informe_capturas_elegidas_{proyecto_id}_{asociacion}",
    )
    return [opciones[etiqueta] for etiqueta in elegidos]


def _eliminar_png(ruta: Path, proyecto_id: int) -> None:
    """Permite borrar una captura tras una confirmacion explícita."""
    import streamlit as st

    with st.expander("Eliminar una captura del proyecto"):
        capturas = listar_capturas(ruta, proyecto_id)
        if not capturas:
            st.caption("No hay capturas para eliminar.")
            return
        opciones = {f"#{item.id} · {item.nombre}": item.id for item in capturas}
        elegido = st.selectbox("Captura", list(opciones), key="informe_eliminar_captura")
        confirmar = st.checkbox(
            "Confirmo la eliminación de esta captura", key="informe_confirmar_eliminar"
        )
        if st.button("Eliminar captura", disabled=not confirmar):
            if eliminar_captura(ruta, proyecto_id, opciones[elegido]):
                st.rerun()
            else:
                st.warning("La captura ya no existe.")


def _mostrar_pdf_con_graficas(
    ruta: Path,
    proyecto: Proyecto,
    analisis: AnalisisGuardado | None,
    capturas: list[CapturaGrafica],
) -> None:
    """Genera y ofrece un PDF usando únicamente PNG ya almacenados."""
    import streamlit as st

    observaciones = st.text_area(
        "Observaciones generales del PDF con gráficas",
        max_chars=2000,
        key="informe_notas_graficas",
    )
    seleccion = (
        proyecto.id,
        analisis.id if analisis else None,
        tuple(item.id for item in capturas),
        observaciones,
    )
    clave = hashlib.sha256(repr(seleccion).encode("utf-8")).hexdigest()[:20]
    if st.button("Generar PDF con gráficas seleccionadas"):
        try:
            if not capturas:
                raise ValueError("Selecciona al menos una captura PNG.")
            imagenes = [recuperar_captura(ruta, proyecto.id, item.id) for item in capturas]
            contenido = generar_informe_graficas_pdf(
                proyecto.nombre, analisis, imagenes, observaciones=observaciones
            )
            st.session_state["wattwise_pdf_graficas"] = (clave, contenido)
            st.success("PDF con gráficas generado correctamente.")
        except (ValueError, OSError, ImportError, sqlite3.Error) as error:
            st.error(f"No se pudo generar el PDF ilustrado: {error}")
    guardado = st.session_state.get("wattwise_pdf_graficas")
    if guardado is not None and guardado[0] == clave:
        st.download_button(
            "Descargar PDF con gráficas",
            data=guardado[1],
            mime="application/pdf",
            file_name=f"wattwise_graficas_proyecto_{proyecto.id}.pdf",
            key=f"descargar_pdf_graficas_{clave}",
        )


def mostrar_informes(ruta: Path) -> None:
    """Presenta informes PDF y galeria persistente de capturas por proyecto."""
    import streamlit as st

    st.header("Informes técnicos")
    st.caption(
        "PDF descriptivo y PDF con capturas ECharts seleccionadas. "
        "Las capturas se exportan manualmente desde la gráfica."
    )
    try:
        proyecto = _seleccionar_proyecto(ruta)
        if proyecto is None:
            return
        analisis = _seleccionar_analisis(ruta, proyecto.id)
        _mostrar_pdf_descriptivo(proyecto, analisis)
        st.divider()
        _guardar_png(ruta, proyecto, analisis)
        capturas = _elegir_capturas(ruta, proyecto.id, analisis)
        _mostrar_pdf_con_graficas(ruta, proyecto, analisis, capturas)
        _eliminar_png(ruta, proyecto.id)
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No se pudo consultar el proyecto: {error}")
    st.warning(
        "La integridad del PNG se verifica, pero el contenido de las capturas "
        "y su correspondencia con las mediciones deben revisarse profesionalmente."
    )
