"""Ubica acciones de Inventario y Motores sin alterar sus módulos originales."""

from __future__ import annotations

from pathlib import Path

from wattwise.interfaz import paneles_completos as original
from wattwise.interfaz.exportacion_html import mostrar_exportar_html
from wattwise.interfaz.guardar_vista_final import mostrar_guardar_analisis_en_vistas
from wattwise.interfaz.panel_guardado_inventario import (
    mostrar_grafico_inventario_capturable,
    mostrar_guardado_inventario,
)


def _grafica_inventario(
    registros: list[dict[str, object]],
    vista: str,
    linea: bool,
    acumulado: bool,
    referencia: bool,
    mostrar_valores: bool,
) -> dict[str, object]:
    """Invoca los generadores existentes con los mismos parámetros."""
    if vista in original.VISTAS_INVENTARIO[:2]:
        return original.pareto_inventario(
            registros,
            "tipo_carga" if vista == original.VISTAS_INVENTARIO[0] else "equipo",
            linea_barras=linea,
            acumulado=acumulado,
            umbral_80=referencia,
            mostrar_valores=mostrar_valores,
        )

    graficas = (
        original.barras_areas,
        original.dona_cargas,
        original.matriz_inventario,
    )
    indice = original.VISTAS_INVENTARIO.index(vista) - 2
    return graficas[indice](
        registros,
        mostrar_valores=mostrar_valores,
    )


def mostrar_inventario_completo(
    resultado: object,
    ruta: Path,
) -> None:
    """Conserva ECharts, KPI, notas y CSV con botones reubicados."""
    import streamlit as st

    completos = original.registros_inventario(resultado)
    if not completos:
        st.info("No hay equipos para analizar.")
        return

    registros = completos
    columnas = st.columns(4)
    filtros: dict[str, str] = {}

    for columna, (campo, titulo, clave) in zip(
        columnas,
        (
            ("frontera", "Frontera", "inv_frontera"),
            ("area", "Área", "inv_area"),
            ("tipo_carga", "Tipo de carga", "inv_tipo"),
            ("equipo", "Equipo", "inv_equipo"),
        ),
        strict=True,
    ):
        with columna:
            registros, filtros[campo] = original._filtro(
                registros,
                titulo,
                campo,
                clave,
            )

    if not registros:
        st.info("No hay equipos para la selección actual.")
        return

    izquierda, derecha = st.columns([3, 1], gap="large")

    with derecha:
        st.markdown("#### Controles")
        vista = st.selectbox(
            "Gráfica",
            original.VISTAS_INVENTARIO,
            key="inv_grafica",
        )

        if vista.startswith("Pareto"):
            linea = st.checkbox(
                "Línea de cumbre",
                value=True,
                key="inv_cumbres",
            )
            acumulado = st.checkbox(
                "Porcentaje acumulado",
                value=True,
                key="inv_acumulado",
            )
            referencia = st.checkbox(
                "Referencia del 80 %",
                value=True,
                key="inv_80",
            )
        else:
            linea, acumulado, referencia = True, True, True

        mostrar = st.checkbox(
            "Visualización de datos numéricos",
            value=True,
            key="inv_mostrar_valores",
        )
        st.caption("Leyenda, zoom, restauración y exportación PNG/HTML.")

    grafico = _grafica_inventario(
        registros,
        vista,
        linea,
        acumulado,
        referencia,
        mostrar,
    )

    with izquierda:
        captura = mostrar_grafico_inventario_capturable(grafico)
        st.caption("Agrupaciones calculadas únicamente a partir del inventario y los filtros.")

    with derecha:
        mostrar_exportar_html(
            grafico,
            vista,
            "inventario_actual",
        )

    st.markdown("#### Indicadores del inventario filtrado")
    original._kpis_inventario(registros)

    original._mostrar_notas(
        ruta,
        "inventario",
        vista,
        filtros,
    )
    original._tabla(registros, "inventario")

    mostrar_guardado_inventario(
        ruta,
        resultado,
        vista,
        filtros,
        {
            "linea_barras": linea,
            "acumulado": acumulado,
            "umbral_80": referencia,
        },
        grafico,
        captura,
    )


def _mostrar_grafica_motor(
    registros: list[dict[str, object]],
    vista: str,
    mostrar: bool,
) -> dict[str, object] | None:
    """Utiliza los mismos gráficos y alturas de Motores."""
    import streamlit as st

    if vista == original.VISTAS_MOTORES[0]:
        grafico = original.corrientes_motores(
            registros,
            mostrar_valores=mostrar,
        )
        st.echarts_chart(
            grafico,
            height=540,
            key="motor_corrientes",
            alt=vista,
        )
        return grafico

    if vista == original.VISTAS_MOTORES[1]:
        grafico = original.mapa_revision_motores(
            registros,
            "relacion",
            mostrar_valores=mostrar,
        )

        if grafico is not None:
            st.echarts_chart(
                grafico,
                height=520,
                key="motor_mapa_relacion",
                alt=vista,
            )

        horas = original.mapa_revision_motores(
            registros,
            "horas",
            mostrar_valores=mostrar,
        )
        if horas is not None:
            st.caption("Horas: mapa independiente, con escala distinta al porcentaje.")
            st.echarts_chart(
                horas,
                height=520,
                key="motor_mapa_horas",
                alt="Horas por motor",
            )
        return grafico

    campo = "potencia_nominal_hp" if vista == original.VISTAS_MOTORES[2] else "horas_operacion_mes"
    grafico = original.barras_motores(
        registros,
        campo,
        mostrar_valores=mostrar,
    )

    if grafico is not None:
        st.echarts_chart(
            grafico,
            height=530,
            key="motor_barras",
            alt=vista,
        )

    return grafico


def mostrar_motores_completo(
    resultado: object,
    ruta: Path,
) -> None:
    """Mantiene indicadores y tabla, con guardar análisis al final."""
    import streamlit as st

    completos = original.registros_motores(resultado)
    if not completos:
        st.info("No hay motores para analizar.")
        return

    registros = completos
    columnas = st.columns(3)
    filtros: dict[str, str] = {}

    for columna, (campo, titulo, clave) in zip(
        columnas,
        (
            ("area", "Área", "motor_area"),
            ("numero_fases", "Número de fases", "motor_fases"),
            ("equipo", "Equipo", "motor_equipo"),
        ),
        strict=True,
    ):
        with columna:
            registros, filtros[campo] = original._filtro(
                registros,
                titulo,
                campo,
                clave,
            )

    if not registros:
        st.info("No hay motores para la selección actual.")
        return

    vistas = list(original.VISTAS_MOTORES)

    if not any(fila.get("horas_operacion_mes") is not None for fila in registros):
        vistas.remove(original.VISTAS_MOTORES[3])

    izquierda, derecha = st.columns([3, 1], gap="large")

    with derecha:
        st.markdown("#### Controles")
        vista = st.selectbox(
            "Gráfica",
            vistas,
            key="motor_grafica",
        )
        mostrar = st.checkbox(
            "Visualización de datos numéricos",
            value=True,
            key="motor_mostrar_valores",
        )
        st.caption("Relación de corrientes: indicador descriptivo, no diagnóstico.")

    with izquierda:
        grafico = _mostrar_grafica_motor(
            registros,
            vista,
            mostrar,
        )
        st.caption("Revisar placa, instrumento y condiciones antes de concluir una falla.")

    with derecha:
        mostrar_exportar_html(
            grafico,
            vista,
            "motores_actual",
        )

    st.markdown("#### Indicadores de motores filtrados")
    original._kpis_motores(registros)

    original._mostrar_notas(
        ruta,
        "motores",
        vista,
        {
            "area": filtros["area"],
            "fases": filtros["numero_fases"],
            "equipo": filtros["equipo"],
        },
    )
    original._tabla(registros, "motores")

    mostrar_guardar_analisis_en_vistas(
        ruta,
        "motores",
        completos,
        {
            "version": 1,
            "grafica": vista,
            "filtros": filtros,
            "opciones": {"mapa_variable": "relacion"},
        },
    )
