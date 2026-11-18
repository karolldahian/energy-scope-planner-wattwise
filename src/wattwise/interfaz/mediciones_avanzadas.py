"""Panel de mediciones con gráficos horarios y diagnósticos eléctricos."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Any

from wattwise.infraestructura.analisis_sqlite import guardar_analisis
from wattwise.infraestructura.lector_mediciones_detalladas import MedicionesImportadas
from wattwise.infraestructura.observaciones_sqlite import (
    Observacion,
    actualizar_visibilidad_observacion,
    eliminar_observacion,
    guardar_observacion,
    listar_observaciones,
)
from wattwise.infraestructura.proyectos_sqlite import listar_proyectos
from wattwise.interfaz.graficos_mediciones_adaptativos import (
    grafico_barras_horarias,
    grafico_diagnostico,
)

GRUPOS = {
    "Potencia activa (kW)": (
        "p_total_kw",
        "p_l1_kw",
        "p_l2_kw",
        "p_l3_kw",
    ),
    "Corrientes (A)": (
        "i_total_a",
        "i_l1_a",
        "i_l2_a",
        "i_l3_a",
    ),
    "Tensiones (V)": (
        "v_total_v",
        "v_l1_v",
        "v_l2_v",
        "v_l3_v",
    ),
    "Factor de potencia": ("fp_total",),
}

COLORES = {
    "p_total_kw": "#2563eb",
    "i_total_a": "#2563eb",
    "v_total_v": "#2563eb",
    "p_l1_kw": "#16a34a",
    "i_l1_a": "#16a34a",
    "v_l1_v": "#16a34a",
    "p_l2_kw": "#f59e0b",
    "i_l2_a": "#f59e0b",
    "v_l2_v": "#f59e0b",
    "p_l3_kw": "#9333ea",
    "i_l3_a": "#9333ea",
    "v_l3_v": "#9333ea",
    "fp_total": "#2563eb",
}

NOMBRES = {
    "p_total_kw": "Potencia total",
    "i_total_a": "Corriente general",
    "v_total_v": "Tensión general",
    "fp_total": "Factor de potencia",
}


@dataclass(frozen=True, slots=True)
class Estadisticas:
    """Resumen estadístico sin completar registros ausentes."""

    maximo: float
    minimo: float
    promedio: float
    p95: float
    validos: int
    total: int


def estadisticas(
    registros: list[dict[str, object]],
    campo: str,
) -> Estadisticas | None:
    """Calcula máximo, mínimo, promedio y percentil 95."""
    valores = sorted(
        float(registro[campo])
        for registro in registros
        if isinstance(registro.get(campo), (int, float))
        and not isinstance(registro.get(campo), bool)
        and isfinite(registro[campo])
    )

    if not valores:
        return None

    indice = (len(valores) - 1) * 0.95
    inferior = int(indice)
    superior = min(inferior + 1, len(valores) - 1)

    percentil = valores[inferior] + (valores[superior] - valores[inferior]) * (indice - inferior)

    return Estadisticas(
        maximo=valores[-1],
        minimo=valores[0],
        promedio=sum(valores) / len(valores),
        p95=percentil,
        validos=len(valores),
        total=len(registros),
    )


def _etiqueta(campo: str) -> str:
    """Devuelve el nombre mostrado para una serie."""
    return NOMBRES.get(
        campo,
        campo.replace("_", " ").upper(),
    )


def _unidad(campo: str) -> str:
    """Indica la unidad eléctrica."""
    if campo.startswith("p_"):
        return "kW"
    if campo.startswith("i_"):
        return "A"
    if campo.startswith("v_"):
        return "V"
    return "adimensional"


def grafico_temporal(
    registros: list[dict[str, object]],
    campos: list[str],
    titulo: str,
    referencias: tuple[str, ...] = (),
    campo_referencia: str | None = None,
) -> dict[str, Any]:
    """Conserva la curva temporal principal y sus referencias."""
    ordenados = sorted(
        registros,
        key=lambda registro: registro["fecha_hora"],
    )
    series: list[dict[str, Any]] = []

    for campo in campos:
        valores = [
            [
                registro["fecha_hora"].isoformat(),
                registro.get(campo),
            ]
            for registro in ordenados
        ]

        serie: dict[str, Any] = {
            "name": _etiqueta(campo),
            "type": "line",
            "data": valores,
            "showSymbol": False,
            "connectNulls": False,
            "lineStyle": {"width": 2},
            "itemStyle": {"color": COLORES[campo]},
            "emphasis": {"focus": "series"},
        }

        if campo == campo_referencia:
            resumen = estadisticas(ordenados, campo)
            if resumen is not None:
                niveles = {
                    "Maximo": resumen.maximo,
                    "Minimo": resumen.minimo,
                    "Máximo": resumen.maximo,
                    "Mínimo": resumen.minimo,
                    "Promedio": resumen.promedio,
                    "P95": resumen.p95,
                }
                marcas = [
                    {
                        "name": nombre,
                        "yAxis": niveles[nombre],
                    }
                    for nombre in referencias
                    if nombre in niveles
                ]

                if marcas:
                    serie["markLine"] = {
                        "silent": True,
                        "symbol": "none",
                        "data": marcas,
                        "label": {"formatter": "{b}: {c}"},
                    }

        series.append(serie)

    return {
        "backgroundColor": "#ffffff",
        "title": {
            "text": titulo,
            "left": "center",
            "textStyle": {"fontSize": 16},
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "cross"},
        },
        "legend": {"type": "scroll", "top": 36},
        "grid": {
            "left": 65,
            "right": 36,
            "top": 90,
            "bottom": 86,
        },
        "toolbox": {
            "right": 10,
            "feature": {
                "saveAsImage": {
                    "type": "png",
                    "pixelRatio": 2,
                    "name": "wattwise_mediciones",
                },
                "restore": {},
            },
        },
        "xAxis": {
            "type": "time",
            "name": "Fecha y hora",
        },
        "yAxis": {
            "type": "value",
            "scale": True,
        },
        "dataZoom": [
            {"type": "inside"},
            {
                "type": "slider",
                "bottom": 25,
            },
        ],
        "series": series,
        "animation": False,
    }


def _opciones(
    registros: list[dict[str, object]],
    campo: str,
) -> list[str]:
    return sorted({str(registro[campo]) for registro in registros})


def _mostrar_kpi(
    registros: list[dict[str, object]],
    campo: str,
) -> None:
    """Mantiene los indicadores estadísticos existentes."""
    import streamlit as st

    resumen = estadisticas(registros, campo)
    if resumen is None:
        return

    st.markdown(f"##### {_etiqueta(campo)}")
    unidad = "" if campo == "fp_total" else _unidad(campo)
    columnas = st.columns(2)

    valores = (
        ("Máximo", resumen.maximo),
        ("Mínimo", resumen.minimo),
        ("Promedio", resumen.promedio),
        ("Percentil 95", resumen.p95),
    )

    for indice, (nombre, valor) in enumerate(valores):
        with columnas[indice % 2]:
            st.metric(
                nombre,
                f"{valor:,.3f} {unidad}".strip(),
            )

    st.caption(f"Cobertura: {resumen.validos} de {resumen.total} registros válidos.")


def _filtrar_registros(
    importado: MedicionesImportadas,
) -> list[dict[str, object]]:
    """Filtra frontera, área, punto y fechas sin mezclarlos."""
    import streamlit as st

    registros = importado.registros
    a, b, c = st.columns(3)

    with a:
        frontera = st.selectbox(
            "Frontera",
            _opciones(registros, "frontera"),
            key="frontera_detallada",
        )

    registros = [fila for fila in registros if fila["frontera"] == frontera]

    with b:
        area = st.selectbox(
            "Área",
            _opciones(registros, "area"),
            key="area_detallada",
        )

    registros = [fila for fila in registros if fila["area"] == area]

    with c:
        punto = st.selectbox(
            "Punto de medición",
            _opciones(registros, "punto_medicion"),
            key="punto_detallado",
        )

    registros = [fila for fila in registros if fila["punto_medicion"] == punto]

    dias = [fila["fecha_hora"].date() for fila in registros]
    inicio, fin = min(dias), max(dias)

    rango = st.date_input(
        "Período",
        value=(inicio, fin),
        min_value=inicio,
        max_value=fin,
        key="periodo_detallado",
    )

    if isinstance(rango, tuple) and len(rango) == 2:
        desde, hasta = rango
        registros = [
            fila
            for fila in registros
            if isinstance(desde, date)
            and isinstance(hasta, date)
            and desde <= fila["fecha_hora"].date() <= hasta
        ]

    return registros


def _texto_diagnostico(campo: str) -> str:
    """Explica los límites de las gráficas complementarias."""
    if campo == "fp_total":
        return (
            "FP ponderado por potencia activa positiva. "
            "La dispersión utiliza potencia y FP del mismo registro, "
            "con carga significativa. La referencia 0,90 no "
            "demuestra multas ni penalizaciones."
        )

    if campo.startswith("v_"):
        return (
            "La gráfica derecha muestra el mínimo registrado "
            "en cada hora para las fases disponibles. "
            "Los márgenes del eje son visuales, no límites "
            "normativos de tensión nominal."
        )

    if campo.startswith("i_"):
        return (
            "El desbalance requiere las corrientes L1, L2 y L3 "
            "medidas en la misma muestra. El 10 % es una "
            "referencia de revisión, no un diagnóstico automático "
            "de sobrecarga ni de corriente en el neutro."
        )

    return (
        "Potencia promedio y máxima registrada por hora. "
        "El mapa presenta potencia media por día y hora. "
        "No se calculan kWh."
    )


def _mostrar_graficas_horarias(
    registros: list[dict[str, object]],
    campo: str,
    mostrar_valores: bool = False,
) -> None:
    """Dibuja comportamiento a la izquierda y diagnóstico a la derecha."""
    import streamlit as st

    barras = grafico_barras_horarias(
        registros,
        campo,
        mostrar_valores=mostrar_valores,
    )
    diagnostico = grafico_diagnostico(
        registros,
        campo,
        mostrar_valores=mostrar_valores,
    )

    st.subheader("Exploración por horarios y diagnóstico")
    st.caption(_texto_diagnostico(campo))

    izquierda, derecha = st.columns(2, gap="large")

    with izquierda:
        st.markdown("#### Comportamiento horario")

        if barras is None:
            st.info("No hay datos suficientes para el gráfico horario de esta variable.")
        else:
            st.echarts_chart(
                barras,
                height=420,
                key="perfil_horario_detallado",
                alt=f"Comportamiento horario de {_etiqueta(campo)}",
            )

    with derecha:
        st.markdown("#### Diagnóstico de ingeniería")

        if diagnostico is None:
            st.info("Faltan series simultáneas o datos válidos para este diagnóstico.")
        else:
            st.echarts_chart(
                diagnostico,
                height=420,
                key="diagnostico_detallado",
                alt=f"Diagnóstico de {_etiqueta(campo)}",
            )


def _ruta_proyectos() -> Path:
    """Localiza la base SQLite del proyecto."""
    return Path(__file__).resolve().parents[3] / "data" / "proyectos.sqlite3"


def _graficas_disponibles(
    registros: list[dict[str, object]],
    titulo_grupo: str,
    variable: str,
) -> dict[str, str]:
    """Incluye únicamente visualizaciones realmente disponibles."""
    opciones = {
        f"Curvas · {titulo_grupo}": "curvas",
    }

    if grafico_barras_horarias(registros, variable) is not None:
        opciones[f"Perfil horario · {_etiqueta(variable)}"] = "perfil"

    if grafico_diagnostico(registros, variable) is not None:
        if variable.startswith("p_"):
            opciones[f"Mapa día-hora · {_etiqueta(variable)}"] = "mapa"
        else:
            opciones[f"Diagnóstico de ingeniería · {_etiqueta(variable)}"] = "diagnostico"

    return opciones


def _campos_diagnostico(
    registros: list[dict[str, object]],
    variable: str,
) -> list[str]:
    """Identifica qué señales alimentan el diagnóstico."""
    if variable == "fp_total":
        return ["p_total_kw", "fp_total"]

    if variable.startswith("i_"):
        return [
            "i_l1_a",
            "i_l2_a",
            "i_l3_a",
        ]

    if variable.startswith("v_"):
        return [
            campo
            for campo in ("v_l1_v", "v_l2_v", "v_l3_v")
            if estadisticas(registros, campo) is not None
        ]

    return [variable]


def _campos_para_tipo(
    registros: list[dict[str, object]],
    tipo: str,
    activos: list[str],
    variable: str,
) -> list[str]:
    """Recupera las señales utilizadas por la gráfica elegida."""
    if tipo == "curvas":
        return list(activos)

    if tipo == "diagnostico":
        return _campos_diagnostico(registros, variable)

    if variable.startswith("i_") or variable == "fp_total":
        return _campos_diagnostico(registros, variable)

    return [variable]


def _contexto_grafica(
    registros: list[dict[str, object]],
    titulo_grupo: str,
    tipo_grafica: str,
    activos: list[str],
    variable_horaria: str,
) -> dict[str, str]:
    """Asocia notas a punto, período, grupo y variables."""
    origen = registros[0]
    fechas = [fila["fecha_hora"] for fila in registros]
    campos = _campos_para_tipo(
        registros,
        tipo_grafica,
        activos,
        variable_horaria,
    )

    return {
        "frontera": str(origen["frontera"]),
        "area": str(origen["area"]),
        "punto_medicion": str(origen["punto_medicion"]),
        "desde": min(fechas).isoformat(),
        "hasta": max(fechas).isoformat(),
        "grupo": titulo_grupo,
        "variables": ",".join(sorted(campos)),
    }


def _clave_interfaz(
    grafica: str,
    contexto: dict[str, str],
) -> str:
    """Separa los textos de notas de diferentes gráficas."""
    serializado = json.dumps(
        [grafica, contexto],
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()[:16]


def _elegir_proyecto(ruta: Path) -> int | None:
    """Usa el proyecto activo global, sin un segundo selector."""
    import streamlit as st

    proyecto_id = st.session_state.get("wattwise_proyecto_id")
    if not isinstance(proyecto_id, int) or isinstance(proyecto_id, bool) or proyecto_id <= 0:
        st.info("Selecciona un proyecto activo en la barra lateral.")
        return None

    try:
        proyectos = listar_proyectos(ruta)
    except (OSError, sqlite3.Error, ValueError) as error:
        st.error(f"No fue posible consultar los proyectos: {error}")
        return None

    if proyecto_id not in {proyecto.id for proyecto in proyectos}:
        st.warning("El proyecto activo ya no existe.")
        return None

    return proyecto_id


def _listar_notas(
    ruta: Path,
    proyecto_id: int,
    grafica: str,
    contexto: dict[str, str],
) -> list[object]:
    """Consulta observaciones del contexto seleccionado."""
    return listar_observaciones(
        ruta,
        proyecto_id,
        "mediciones",
        grafica,
        contexto,
    )


def _controles_nota(
    ruta: Path,
    proyecto_id: int,
    nota: Observacion,
) -> None:
    """Actualiza la visibilidad y permite eliminar una nota del proyecto."""
    import streamlit as st

    mostrar = st.checkbox(
        "Mostrar en el informe",
        value=nota.mostrar_en_informe,
        key=f"md_visible_nota_{proyecto_id}_{nota.id}",
    )
    if mostrar != nota.mostrar_en_informe:
        try:
            actualizada = actualizar_visibilidad_observacion(
                ruta,
                proyecto_id,
                nota.id,
                mostrar,
            )
            if actualizada:
                st.toast("Preferencia de informe guardada.")
            else:
                st.warning("La nota ya no existe. Actualiza la pestaña.")
        except (OSError, sqlite3.Error, ValueError) as error:
            st.error(f"No se pudo actualizar la preferencia: {error}")

    confirmar = st.checkbox(
        "Confirmar eliminación",
        key=f"md_confirmar_nota_{proyecto_id}_{nota.id}",
    )
    if st.button(
        "Eliminar nota",
        disabled=not confirmar,
        key=f"md_eliminar_nota_{proyecto_id}_{nota.id}",
    ):
        try:
            if eliminar_observacion(ruta, proyecto_id, nota.id):
                st.rerun()
            else:
                st.warning("La nota ya no existe.")
        except (OSError, sqlite3.Error, ValueError) as error:
            st.error(f"No se pudo eliminar la nota: {error}")


def _mostrar_observaciones(
    ruta: Path,
    proyecto_id: int,
    grafica: str,
    contexto: dict[str, str],
) -> None:
    """Guarda notas, muestra su estado y las enumera consecutivamente."""
    import streamlit as st

    clave = _clave_interfaz(grafica, contexto)
    texto = st.text_area(
        "Interpretación, hallazgos y recomendaciones por verificar",
        max_chars=2000,
        key=f"md_nota_{proyecto_id}_{clave}",
    )

    if st.button(
        "Guardar observación",
        key=f"md_guardar_nota_{proyecto_id}_{clave}",
    ):
        try:
            guardar_observacion(
                ruta,
                proyecto_id,
                "mediciones",
                grafica,
                contexto,
                texto,
            )
            st.success("Observación guardada para la gráfica y el proyecto seleccionados.")
        except (OSError, sqlite3.Error, ValueError) as error:
            st.error(f"No se pudo guardar la observación: {error}")

    try:
        notas = sorted(
            _listar_notas(ruta, proyecto_id, grafica, contexto),
            key=lambda nota: nota.id,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        st.error(f"No se pudieron consultar las observaciones: {error}")
        return

    if notas:
        st.markdown("**Notas guardadas**")
        for posicion, nota in enumerate(notas, start=1):
            with st.expander(f"Nota {posicion}"):
                st.write(nota.texto)
                _controles_nota(ruta, proyecto_id, nota)


def _exportar_tabla(
    registros: list[dict[str, object]],
) -> None:
    """Presenta registros filtrados y exporta un CSV seguro."""
    import pandas as pd
    import streamlit as st

    st.markdown("#### Datos del filtro aplicado")
    tabla = pd.DataFrame(registros)
    st.dataframe(
        tabla,
        width="stretch",
        hide_index=True,
    )

    exportable = tabla.copy()
    for columna in exportable.select_dtypes(include=["object"]).columns:
        exportable[columna] = exportable[columna].map(
            lambda valor: (
                "'" + valor
                if isinstance(valor, str) and valor.startswith(("=", "+", "-", "@"))
                else valor
            )
        )

    st.download_button(
        "Descargar tabla CSV filtrada",
        data=exportable.to_csv(index=False).encode("utf-8-sig"),
        file_name="wattwise_mediciones_filtradas.csv",
        mime="text/csv",
        key="exportar_mediciones_detalladas",
    )


def _resumen_guardable(
    registros: list[dict[str, object]],
    grafica: str,
    contexto: dict[str, str],
    activos: list[str],
    variable_horaria: str,
    referencia: str,
    marcas: tuple[str, ...],
    notas: list[object],
    mostrar_valores: bool,
) -> dict[str, object]:
    """Guarda configuración, estadísticas y notas sin simular PNG."""
    if grafica.startswith("Curvas"):
        tipo = "curvas"
    elif grafica.startswith("Perfil horario"):
        tipo = "perfil"
    elif grafica.startswith("Mapa día-hora"):
        tipo = "mapa"
    else:
        tipo = "diagnostico"

    campos = _campos_para_tipo(
        registros,
        tipo,
        activos,
        variable_horaria,
    )

    resumenes: dict[str, object] = {}
    for campo in campos:
        calculo = estadisticas(registros, campo)
        if calculo is not None:
            resumenes[campo] = {
                "maximo": calculo.maximo,
                "minimo": calculo.minimo,
                "promedio": calculo.promedio,
                "p95": calculo.p95,
                "validos": calculo.validos,
                "total": calculo.total,
                "unidad": _unidad(campo),
            }

    return {
        "version": 2,
        "origen": "mediciones_detalladas",
        "grafica": grafica,
        "tipo_grafica": tipo,
        "contexto": contexto,
        "series_visibles": list(campos),
        "serie_referencia": (referencia if tipo == "curvas" else None),
        "referencias_visibles": (list(marcas) if tipo == "curvas" else []),
        "muestras_filtradas": len(registros),
        "estadisticas": resumenes,
        "observaciones": [
            {
                "id": nota.id,
                "texto": nota.texto,
                "creado_utc": nota.creado_utc,
            }
            for nota in notas
        ],
        "mostrar_datos_numericos": mostrar_valores,
        "captura_png_incluida": False,
    }


def _mostrar_guardado_analisis(
    ruta: Path,
    proyecto_id: int,
    grafica: str,
    contexto: dict[str, str],
    registros: list[dict[str, object]],
    activos: list[str],
    variable_horaria: str,
    referencia: str,
    marcas: tuple[str, ...],
    mostrar_valores: bool,
) -> None:
    """Guarda el análisis seleccionado y sus notas actuales."""
    import streamlit as st

    st.markdown("#### Guardar este análisis")
    identificador = _clave_interfaz(grafica, contexto)

    titulo = st.text_input(
        "Título del análisis",
        value=f"Mediciones · {grafica}"[:120],
        max_chars=120,
        key=f"md_titulo_{proyecto_id}_{identificador}",
    )

    st.caption(
        "Se guardan la configuración, los indicadores y las "
        "observaciones. Para incluir la imagen en el PDF, "
        "exporta el PNG desde ECharts y adjúntalo en Informes."
    )

    if not st.button(
        "Guardar análisis",
        key=f"md_guardar_analisis_{proyecto_id}_{identificador}",
    ):
        return

    try:
        notas = _listar_notas(
            ruta,
            proyecto_id,
            grafica,
            contexto,
        )
        resultado = _resumen_guardable(
            registros,
            grafica,
            contexto,
            activos,
            variable_horaria,
            referencia,
            marcas,
            notas,
            mostrar_valores,
        )
        guardar_analisis(
            ruta,
            proyecto_id,
            "mediciones",
            titulo,
            resultado,
        )
        st.success("Análisis guardado con su configuración y las observaciones actuales.")
    except (
        OSError,
        sqlite3.Error,
        ValueError,
        TypeError,
    ) as error:
        st.error(f"No se pudo guardar el análisis: {error}")


def _mostrar_resumen_importacion(
    importado: MedicionesImportadas,
) -> None:
    """Muestra los resultados de lectura y advertencias."""
    import streamlit as st

    st.success(
        f"{len(importado.registros):,} registros importados; "
        f"{sum(bool(n) for n in importado.cobertura.values())} "
        "variables con datos."
    )

    if importado.problemas:
        st.warning(
            f"Se detectaron {importado.problemas} problemas; "
            f"{importado.filas_omitidas} filas con fechas inutilizables."
        )
        with st.expander("Ver observaciones de calidad"):
            for aviso in importado.advertencias:
                st.write(aviso)

            if importado.problemas > len(importado.advertencias):
                st.caption("Solo se muestran las primeras 20 observaciones.")


def _mostrar_cierre(
    filtrados: list[dict[str, object]],
    titulo_grupo: str,
    activos: list[str],
    variable_horaria: str,
    referencia: str,
    marcas: tuple[str, ...],
    ruta: Path,
    mostrar_valores: bool,
) -> None:
    """Mantiene notas, datos filtrados y guardado debajo de las gráficas."""
    import streamlit as st

    st.markdown("#### Observaciones del ingeniero")
    opciones = _graficas_disponibles(
        filtrados,
        titulo_grupo,
        variable_horaria,
    )
    grafica = st.selectbox(
        "Gráfica para observaciones y análisis",
        list(opciones),
        key="md_grafica_para_guardar",
    )

    contexto = _contexto_grafica(
        filtrados,
        titulo_grupo,
        opciones[grafica],
        activos,
        variable_horaria,
    )

    proyecto_id = _elegir_proyecto(ruta)
    if proyecto_id is not None:
        _mostrar_observaciones(
            ruta,
            proyecto_id,
            grafica,
            contexto,
        )

    _exportar_tabla(filtrados)

    if proyecto_id is not None:
        _mostrar_guardado_analisis(
            ruta,
            proyecto_id,
            grafica,
            contexto,
            filtrados,
            activos,
            variable_horaria,
            referencia,
            marcas,
            mostrar_valores,
        )


def _mostrar_seleccion(
    filtrados: list[dict[str, object]],
    ruta: Path,
) -> None:
    """Conserva los controles y enlaza las nuevas gráficas complementarias."""
    import streamlit as st

    grupos = {
        nombre: tuple(campo for campo in campos if estadisticas(filtrados, campo) is not None)
        for nombre, campos in GRUPOS.items()
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
            format_func=_etiqueta,
            key=f"series_{titulo_grupo}",
        )

        if not activos:
            st.info("Selecciona al menos una serie.")
            return

        referencia = st.selectbox(
            "Serie de referencia",
            activos,
            format_func=_etiqueta,
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

    with izquierda:
        st.echarts_chart(
            grafico_temporal(
                filtrados,
                activos,
                titulo_grupo,
                marcas,
                referencia,
            ),
            height=510,
            key="grafico_detallado",
            alt=f"Curvas de {titulo_grupo}",
        )
        st.caption(
            "Curva del punto seleccionado. Los valores "
            "faltantes no se sustituyen. Las referencias "
            "corresponden a la serie y el período elegidos."
        )

    st.subheader("Indicadores del período seleccionado")
    for campo in activos:
        _mostrar_kpi(
            filtrados,
            campo,
        )

    st.markdown("#### Gráficas adicionales")
    variable_horaria = st.selectbox(
        "Variable para análisis horario",
        activos,
        format_func=_etiqueta,
        key=f"variable_horaria_{titulo_grupo}",
    )
    mostrar_valores = st.checkbox(
        "Visualización de datos numéricos",
        value=False,
        key=f"md_valores_{titulo_grupo}",
    )

    _mostrar_graficas_horarias(
        filtrados,
        variable_horaria,
        mostrar_valores,
    )
    _mostrar_cierre(
        filtrados,
        titulo_grupo,
        activos,
        variable_horaria,
        referencia,
        marcas,
        ruta,
        mostrar_valores,
    )


def mostrar_panel_mediciones_detalladas(
    importado: MedicionesImportadas,
    ruta: Path | None = None,
) -> None:
    """Muestra curvas, diagnósticos y observaciones persistentes."""
    import streamlit as st

    _mostrar_resumen_importacion(importado)
    filtrados = _filtrar_registros(importado)

    if not filtrados:
        st.info("No hay registros en el período seleccionado.")
        return

    _mostrar_seleccion(
        filtrados,
        ruta if ruta is not None else _ruta_proyectos(),
    )
