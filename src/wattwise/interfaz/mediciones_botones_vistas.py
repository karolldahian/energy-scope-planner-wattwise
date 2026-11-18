"""Reordena botones de Mediciones reutilizando los cálculos y gráficos originales."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wattwise.infraestructura.lector_mediciones_detalladas import MedicionesImportadas
from wattwise.interfaz import mediciones_avanzadas as original
from wattwise.interfaz.exportacion_html import mostrar_exportar_html
from wattwise.interfaz.guardar_vista_final import mostrar_guardar_analisis_en_vistas
from wattwise.interfaz.panel_energia import mostrar_indicadores_complementarios


def _mostrar_cierre(
    filtrados: list[dict[str, Any]],
    originales: list[dict[str, Any]],
    titulo_grupo: str,
    activos: list[str],
    variable_horaria: str,
    referencia: str,
    marcas: tuple[str, ...],
    ruta: Path,
) -> None:
    """Muestra observación, CSV y guardado de vista en ese orden."""
    import streamlit as st

    st.markdown("#### Observaciones del ingeniero")

    opciones = original._graficas_disponibles(
        filtrados,
        titulo_grupo,
        variable_horaria,
    )
    grafica = st.selectbox(
        "Gráfica para observaciones y análisis",
        list(opciones),
        key="md_grafica_para_guardar",
    )

    contexto = original._contexto_grafica(
        filtrados,
        titulo_grupo,
        opciones[grafica],
        activos,
        variable_horaria,
    )

    proyecto_id = original._elegir_proyecto(ruta)

    if proyecto_id is not None:
        original._mostrar_observaciones(
            ruta,
            proyecto_id,
            grafica,
            contexto,
        )

    original._exportar_tabla(filtrados)

    if proyecto_id is None:
        return

    mostrar_guardar_analisis_en_vistas(
        ruta,
        "mediciones",
        originales,
        {
            "version": 1,
            "grafica": titulo_grupo,
            "filtros": {
                "frontera": str(filtrados[0]["frontera"]),
                "area": str(filtrados[0]["area"]),
                "punto_medicion": str(filtrados[0]["punto_medicion"]),
            },
            "opciones": {},
            "periodo": {
                "desde": min(fila["fecha_hora"].date() for fila in filtrados).isoformat(),
                "hasta": max(fila["fecha_hora"].date() for fila in filtrados).isoformat(),
            },
            "series": list(activos),
            "referencia": referencia,
            "marcas": list(marcas),
        },
    )


def _mostrar_seleccion(
    filtrados: list[dict[str, Any]],
    originales: list[dict[str, Any]],
    ruta: Path,
) -> None:
    """Deja los KPI debajo del gráfico 75/25."""
    import streamlit as st

    grupos = {
        nombre: tuple(
            campo for campo in campos if original.estadisticas(filtrados, campo) is not None
        )
        for nombre, campos in original.GRUPOS.items()
    }
    grupos = {nombre: campos for nombre, campos in grupos.items() if campos}

    if not grupos:
        st.info("El filtro seleccionado no contiene variables eléctricas válidas.")
        return

    titulo_grupo = st.selectbox(
        "Grupo de análisis",
        list(grupos),
        key="grupo_detallado",
    )
    disponibles = list(grupos[titulo_grupo])

    izquierda, derecha = st.columns(
        [3, 1],
        gap="large",
    )

    with derecha:
        st.markdown("#### Controles")

        activos = st.multiselect(
            "Series visibles",
            disponibles,
            default=disponibles,
            format_func=original._etiqueta,
            key=f"series_{titulo_grupo}",
        )

        if not activos:
            st.info("Selecciona al menos una serie.")
            return

        referencia = st.selectbox(
            "Serie de referencia",
            activos,
            format_func=original._etiqueta,
            key=f"referencia_{titulo_grupo}",
        )

        marcas = tuple(
            nombre
            for nombre in (
                "Máximo",
                "Mínimo",
                "Promedio",
                "P95",
            )
            if st.checkbox(
                nombre,
                value=False,
                key=f"linea_{titulo_grupo}_{nombre}",
            )
        )

        st.caption("Leyenda interactiva, zoom, restaurar y descarga PNG en la gráfica.")

    grafico = original.grafico_temporal(
        filtrados,
        activos,
        titulo_grupo,
        marcas,
        referencia,
    )

    with izquierda:
        st.echarts_chart(
            grafico,
            height=510,
            key="grafico_detallado",
            alt=f"Curvas de {titulo_grupo}",
        )
        st.caption(
            "Curva del punto seleccionado. Los valores "
            "faltantes no se sustituyen. Las referencias "
            "corresponden a la serie y el período elegidos."
        )

    with derecha:
        mostrar_exportar_html(
            grafico,
            f"Curvas de {titulo_grupo}",
            "mediciones_curvas",
        )

    st.subheader("Indicadores del período seleccionado")
    for campo in activos:
        original._mostrar_kpi(filtrados, campo)

    mostrar_indicadores_complementarios(filtrados)

    st.markdown("#### Gráficas adicionales")

    variable_horaria = st.selectbox(
        "Variable para análisis horario",
        activos,
        format_func=original._etiqueta,
        key=f"variable_horaria_{titulo_grupo}",
    )

    mostrar_valores = st.checkbox(
        "Visualización de datos numéricos",
        value=False,
        key=f"md_valores_{titulo_grupo}",
    )

    original._mostrar_graficas_horarias(
        filtrados,
        variable_horaria,
        mostrar_valores,
    )

    _mostrar_cierre(
        filtrados,
        originales,
        titulo_grupo,
        activos,
        variable_horaria,
        referencia,
        marcas,
        ruta,
    )


def mostrar_panel_mediciones_detalladas(
    importado: MedicionesImportadas,
    ruta: Path | None = None,
) -> None:
    """Muestra Mediciones originales con los botones reubicados."""
    import streamlit as st

    original._mostrar_resumen_importacion(importado)
    filtrados = original._filtrar_registros(importado)

    if not filtrados:
        st.info("No hay registros en el período seleccionado.")
        return

    _mostrar_seleccion(
        filtrados,
        importado.registros,
        ruta if ruta is not None else original._ruta_proyectos(),
    )
