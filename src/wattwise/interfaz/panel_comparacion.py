"""Comparacion condicionada entre inventario y un unico punto medido."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from wattwise.dominio.calidad_mediciones import auditar_mediciones
from wattwise.dominio.comparacion import comparar_potencias, grafico_comparacion
from wattwise.dominio.inventario import analizar_inventario
from wattwise.infraestructura.archivos_proyecto import listar_archivos, recuperar_archivo
from wattwise.infraestructura.comparaciones_sqlite import (
    guardar_comparacion,
    listar_comparaciones,
)
from wattwise.infraestructura.lector_inventario_excel import leer_inventario_excel
from wattwise.infraestructura.lector_mediciones_detalladas import leer_mediciones_detalladas
from wattwise.infraestructura.proyectos_sqlite import listar_proyectos
from wattwise.interfaz.paneles_completos import registros_inventario


def _elegir_fuente(
    ruta: Path,
    proyecto_id: int,
    tipo: str,
) -> tuple[int, str, bytes] | None:
    """Recupera un original del proyecto con verificacion de su huella."""
    import streamlit as st

    archivos = listar_archivos(ruta, proyecto_id, tipo)
    if tipo == "mediciones":
        archivos = [archivo for archivo in archivos if archivo.nombre.lower().endswith(".xlsx")]
    if not archivos:
        st.info(f"Este proyecto no tiene originales {tipo} compatibles.")
        return None

    opciones = {f"#{archivo.id} · {archivo.nombre}": archivo.id for archivo in archivos}
    etiqueta = st.selectbox(f"Archivo de {tipo}", list(opciones), key=f"cmp_archivo_{tipo}")
    archivo, contenido = recuperar_archivo(ruta, proyecto_id, opciones[etiqueta])
    return archivo.id, archivo.nombre, contenido


def _filtrar_inventario(
    registros: list[dict[str, object]],
) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    """Exige seleccion manual de areas, sin asumir alcance del instrumento."""
    import streamlit as st

    disponibles = sorted({str(registro.get("area") or "Sin especificar") for registro in registros})
    areas = st.multiselect(
        "Áreas incluidas en el inventario que vas a comparar",
        disponibles,
        default=[],
        key="cmp_areas",
    )
    seleccionados = [
        registro
        for registro in registros
        if str(registro.get("area") or "Sin especificar") in areas
    ]
    return seleccionados, tuple(sorted(areas))


def _identidad_punto(registro: dict[str, object]) -> tuple[str, str, str]:
    """Compone la clave de medicion, que no debe inferirse solo por area."""
    return tuple(
        str(registro.get(clave) or "Sin especificar")
        for clave in ("frontera", "area", "punto_medicion")
    )


def _seleccionar_punto(registros: list[dict[str, object]]) -> list[dict[str, object]]:
    """Selecciona una identidad de medicion completa, nunca varios puntos."""
    import streamlit as st

    opciones = {
        " | ".join(identidad): identidad
        for identidad in sorted({_identidad_punto(registro) for registro in registros})
        if identidad[2] != "Sin especificar"
    }
    if not opciones:
        st.warning("No hay puntos de medición identificados para una comparación segura.")
        return []

    seleccionado = st.selectbox("Punto medido", list(opciones), key="cmp_punto")
    identidad = opciones[seleccionado]
    return [registro for registro in registros if _identidad_punto(registro) == identidad]


def _mostrar_calidad(registros: list[dict[str, object]]) -> None:
    """Muestra trazabilidad y cobertura sin inventar señales faltantes."""
    import pandas as pd
    import streamlit as st

    calidad = auditar_mediciones(registros)

    with st.expander("Calidad y cobertura del punto seleccionado"):
        a, b, c = st.columns(3)
        a.metric("Muestras", calidad.total_registros)
        b.metric("Fechas duplicadas", calidad.timestamps_duplicados)
        c.metric("Huecos prolongados", calidad.huecos_largos)

        st.caption(
            f"Período: {calidad.primera_fecha} a {calidad.ultima_fecha}. "
            f"Muestreo mediano: {calidad.intervalo_mediano_min} minutos (descriptivo)."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Variable": item.variable,
                        "Válidos": item.validos,
                        "Faltantes": item.faltantes,
                        "Cobertura (%)": round(item.cobertura_pct, 2),
                    }
                    for item in calidad.variables
                ]
            ),
            width="stretch",
            hide_index=True,
        )
        for aviso in calidad.advertencias:
            st.warning(aviso)


def _mostrar_guardados(ruta: Path, proyecto_id: int) -> None:
    """Permite consultar historicos y justificaciones persistidas."""
    import streamlit as st

    comparaciones = listar_comparaciones(ruta, proyecto_id)
    if not comparaciones:
        return

    with st.expander(f"Comparaciones guardadas ({len(comparaciones)})"):
        opciones = {
            f"#{comparacion.id} · {comparacion.creado_utc}": comparacion
            for comparacion in comparaciones
        }
        elegido = st.selectbox("Histórico", list(opciones), key="cmp_historico")
        registro = opciones[elegido]

        st.write(f"Áreas incluidas: {', '.join(registro.areas)}")
        st.caption(
            f"Original inventario #{registro.inventario_id} · Mediciones #{registro.mediciones_id}"
        )
        st.json(registro.resultado)


def _leer_fuentes(
    ruta: Path,
    proyecto_id: int,
) -> tuple[int, int, list[dict[str, object]], list[dict[str, object]]] | None:
    """Revalida cada original archivado con su lector de dominio habitual."""
    import streamlit as st

    a, b = st.columns(2)
    with a:
        fuente_inventario = _elegir_fuente(ruta, proyecto_id, "inventario")
    with b:
        fuente_mediciones = _elegir_fuente(ruta, proyecto_id, "mediciones")

    if fuente_inventario is None or fuente_mediciones is None:
        return None

    inventario_id, nombre_inventario, bytes_inventario = fuente_inventario
    mediciones_id, nombre_mediciones, bytes_mediciones = fuente_mediciones

    resultado_inventario = analizar_inventario(
        leer_inventario_excel(bytes_inventario, nombre_inventario)
    )
    importado = leer_mediciones_detalladas(bytes_mediciones, nombre_mediciones)

    return (
        inventario_id,
        mediciones_id,
        registros_inventario(resultado_inventario),
        importado.registros,
    )


def mostrar_comparacion(ruta: Path) -> None:
    """Compara fuentes originales solo con confirmacion electrica expresa."""
    import streamlit as st

    st.header("Comparación · Inventario frente a mediciones")
    st.warning(
        "El nombre del área no demuestra que el punto de medición cubra esas cargas. "
        "Si no conoces el alcance eléctrico, no confirmes la comparación."
    )

    try:
        proyectos = listar_proyectos(ruta)
        if not proyectos:
            st.info("Crea un proyecto y conserva primero ambos Excel originales.")
            return

        opciones = {f"{proyecto.id} - {proyecto.nombre}": proyecto.id for proyecto in proyectos}
        seleccionado = st.selectbox("Proyecto", list(opciones), key="cmp_proyecto")
        proyecto_id = opciones[seleccionado]

        fuentes = _leer_fuentes(ruta, proyecto_id)
        if fuentes is None:
            _mostrar_guardados(ruta, proyecto_id)
            return

        inventario_id, mediciones_id, inventario, registros = fuentes
        inventario, areas = _filtrar_inventario(inventario)
        mediciones = _seleccionar_punto(registros)

        if not inventario or not mediciones:
            st.info("Selecciona áreas de inventario y un punto identificado.")
        else:
            _mostrar_calidad(mediciones)
            _calcular_y_mostrar(
                ruta,
                proyecto_id,
                inventario_id,
                mediciones_id,
                inventario,
                mediciones,
                areas,
            )

        _mostrar_guardados(ruta, proyecto_id)

    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No se puede completar la comparación: {error}")


def _calcular_y_mostrar(
    ruta: Path,
    proyecto_id: int,
    inventario_id: int,
    mediciones_id: int,
    inventario: list[dict[str, object]],
    mediciones: list[dict[str, object]],
    areas: tuple[str, ...],
) -> None:
    """Bloquea KPIs y grafica hasta que exista justificacion de cobertura."""
    import streamlit as st

    contexto = {
        "proyecto": proyecto_id,
        "inventario": inventario_id,
        "mediciones": mediciones_id,
        "areas": areas,
        "punto": _identidad_punto(mediciones[0]),
    }
    clave = hashlib.sha256(
        json.dumps(contexto, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]

    st.subheader("Confirmación del alcance")
    justificacion = st.text_area(
        "Explica qué alimenta el punto, qué cargas cubre y cómo lo verificaste",
        max_chars=500,
        key=f"cmp_justificacion_{clave}",
    )
    confirmado = st.checkbox(
        "Confirmo que el punto seleccionado cubre exactamente las cargas del inventario "
        "filtrado, sin circuitos adicionales ni cargas omitidas.",
        key=f"cmp_confirmacion_{clave}",
    )

    if not confirmado:
        st.info("Los indicadores comparativos permanecen bloqueados hasta confirmar el alcance.")
        return

    try:
        resultado = comparar_potencias(
            inventario,
            mediciones,
            alcance_confirmado=confirmado,
            justificacion_alcance=justificacion,
        )
    except ValueError as error:
        st.warning(str(error))
        return

    izquierda, derecha = st.columns([3, 1], gap="large")
    with izquierda:
        st.echarts_chart(
            grafico_comparacion(resultado),
            height=420,
            key="cmp_grafica",
            alt="Potencia instalada declarada frente al máximo de potencia activa medido",
        )
    with derecha:
        st.markdown("#### Interpretación")
        st.caption("Solo se comparan kW, no kWh. No se diagnostica falla ni ahorro.")
        st.caption(f"Punto: {resultado.punto_medicion}")

    st.subheader("Indicadores de la comparación")
    c1, c2 = st.columns(2)
    c1.metric("Potencia instalada", f"{resultado.potencia_instalada_kw:,.3f} kW")
    c2.metric("Pico medido", f"{resultado.potencia_maxima_medida_kw:,.3f} kW")

    c1, c2 = st.columns(2)
    relacion = (
        "No calculable" if resultado.relacion_pct is None else f"{resultado.relacion_pct:,.2f} %"
    )
    c1.metric("Máximo / instalada", relacion)
    c2.metric(
        "Muestras válidas",
        f"{resultado.muestras_validas} / {resultado.muestras_totales}",
    )

    for advertencia in resultado.advertencias:
        st.warning(advertencia)

    if st.button(
        "Guardar comparación confirmada",
        key=f"cmp_guardar_{clave}",
    ):
        try:
            identificador = guardar_comparacion(
                ruta,
                proyecto_id,
                inventario_id,
                mediciones_id,
                resultado,
                areas,
            )
            st.success(f"Comparación #{identificador} guardada con su justificación y fuentes.")
        except (ValueError, OSError, sqlite3.Error) as error:
            st.error(f"No se pudo guardar la comparación: {error}")
