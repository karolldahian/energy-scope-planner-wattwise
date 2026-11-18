"""Indicadores complementarios y energía estimada con controles de integridad."""

from __future__ import annotations

import hashlib

from wattwise.dominio.energia_temporal import ResultadoEnergia, analizar_energia_temporal
from wattwise.dominio.indicadores_complementarios import (
    calcular_desbalance_tension,
    calcular_factor_carga,
)


def grafico_energia_diaria(resultado: ResultadoEnergia) -> dict[str, object] | None:
    """Muestra importación y exportación diarias sin sumar puntos distintos."""
    if not resultado.por_dia:
        return None
    return {
        "backgroundColor": "#ffffff",
        "title": {"text": "Energía diaria estimada (kWh)", "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 35},
        "grid": {"top": 85, "bottom": 85, "left": 75, "right": 45},
        "xAxis": {
            "type": "category",
            "data": [dia.fecha.isoformat() for dia in resultado.por_dia],
        },
        "yAxis": {"type": "value", "name": "kWh"},
        "dataZoom": [{"type": "inside"}, {"type": "slider", "bottom": 25}],
        "toolbox": {
            "right": 8,
            "feature": {
                "saveAsImage": {"type": "png", "pixelRatio": 2},
                "restore": {},
            },
        },
        "series": [
            {
                "name": "Importación estimada (+kWh)",
                "type": "bar",
                "itemStyle": {"color": "#2563eb"},
                "data": [round(dia.importada_kwh, 5) for dia in resultado.por_dia],
            },
            {
                "name": "Exportación estimada (-kWh)",
                "type": "bar",
                "itemStyle": {"color": "#f59e0b"},
                "data": [-round(dia.exportada_kwh, 5) for dia in resultado.por_dia],
            },
        ],
    }


def grafico_energia_acumulada(resultado: ResultadoEnergia) -> dict[str, object] | None:
    """Representa el saldo acumulado de los tramos temporalmente válidos."""
    if not resultado.por_dia:
        return None
    saldo = 0.0
    puntos = []
    for dia in resultado.por_dia:
        saldo += dia.neta_kwh
        puntos.append([dia.fecha.isoformat(), round(saldo, 5)])
    return {
        "backgroundColor": "#ffffff",
        "title": {"text": "Energía neta acumulada estimada", "left": "center"},
        "tooltip": {"trigger": "axis"},
        "grid": {"top": 75, "bottom": 75, "left": 80, "right": 40},
        "xAxis": {"type": "time", "name": "Día"},
        "yAxis": {"type": "value", "name": "kWh"},
        "toolbox": {
            "right": 8,
            "feature": {
                "saveAsImage": {"type": "png", "pixelRatio": 2},
                "restore": {},
            },
        },
        "dataZoom": [{"type": "inside"}, {"type": "slider", "bottom": 18}],
        "series": [
            {
                "name": "Saldo neto acumulado (kWh)",
                "type": "line",
                "data": puntos,
                "showSymbol": True,
                "itemStyle": {"color": "#16a34a"},
            }
        ],
    }


def _clave_datos(registros: list[dict[str, object]]) -> str:
    """Aísla la confirmación de energía por conjunto filtrado y proyecto."""
    import streamlit as st

    identidad = st.session_state.get("wattwise_proyecto_id")
    campos = ("fecha_hora", "frontera", "area", "punto_medicion", "p_total_kw")
    datos = [tuple(fila.get(campo) for campo in campos) for fila in registros]
    material = repr((identidad, datos)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def mostrar_indicadores_complementarios(registros: list[dict[str, object]]) -> None:
    """Muestra desbalance de tensión y acceso a integración de energía."""
    import streamlit as st

    st.subheader("Indicadores energéticos complementarios")
    resumen = calcular_desbalance_tension(registros)
    if resumen is None:
        st.info("Desbalance de tensión: no calculable sin tres tensiones positivas válidas.")
    else:
        a, b, c = st.columns(3)
        a.metric("Desbalance de tensión · promedio", f"{resumen.promedio_pct:,.2f} %")
        b.metric("Desbalance de tensión · P95", f"{resumen.p95_pct:,.2f} %")
        c.metric("Desbalance de tensión · máximo", f"{resumen.maximo_pct:,.2f} %")
        st.caption(
            f"Muestras trifásicas válidas: {resumen.muestras_validas} de "
            f"{resumen.muestras_totales}. Se calcula la desviación máxima respecto "
            "al promedio de tres tensiones simultáneas comparables. Confirmar "
            "si corresponden a fase-neutro o línea-línea; no se aplica un "
            "umbral normativo universal."
        )

    with st.expander("Energía estimada y factor de carga · cálculo condicionado"):
        mostrar_panel_energia(registros, clave=_clave_datos(registros))


def _mostrar_metricas_energia(
    resultado: ResultadoEnergia,
    registros: list[dict[str, object]],
) -> None:
    """Muestra kWh y el factor de carga solo si corresponde calcularlo."""
    import streamlit as st

    columnas = st.columns(2)
    columnas[0].metric("Energía importada estimada", f"{resultado.importada_kwh:,.3f} kWh")
    columnas[1].metric("Energía exportada estimada", f"{resultado.exportada_kwh:,.3f} kWh")
    columnas = st.columns(2)
    columnas[0].metric("Saldo neto estimado", f"{resultado.neta_kwh:,.3f} kWh")
    columnas[1].metric("Tiempo integrado", f"{resultado.horas_integradas:,.2f} h")

    factor = calcular_factor_carga(registros, resultado)
    if factor is None:
        st.info(
            "Factor de carga: no calculable con los tramos disponibles. "
            "Requiere continuidad temporal, potencia no negativa, "
            "ausencia de muestras duplicadas y un máximo positivo."
        )
    else:
        st.metric("Factor de carga muestral estimado", f"{factor:,.2f} %")
        st.caption(
            "Energía importada estimada / (máxima potencia muestral × horas "
            "integradas). No equivale al factor de carga de facturación "
            "ni demuestra eficiencia energética."
        )


def _mostrar_graficos_energia(resultado: ResultadoEnergia, clave: str) -> None:
    """Reutiliza las visualizaciones de energía diaria y acumulada."""
    import streamlit as st

    diario = grafico_energia_diaria(resultado)
    acumulado = grafico_energia_acumulada(resultado)
    if diario is not None:
        st.echarts_chart(
            diario,
            height=380,
            key=f"grafico_energia_diaria_{clave}",
            alt="Energía importada y exportada estimada por día",
        )
    if acumulado is not None:
        st.echarts_chart(
            acumulado,
            height=340,
            key=f"grafico_energia_acumulada_{clave}",
            alt="Saldo de energía neta acumulada estimada",
        )


def _mostrar_tabla_energia(resultado: ResultadoEnergia, clave: str) -> None:
    """Ofrece detalle por día para auditar la energía integrada."""
    import pandas as pd
    import streamlit as st

    tabla = pd.DataFrame(
        [
            {
                "Día": dia.fecha,
                "Importada estimada (kWh)": dia.importada_kwh,
                "Exportada estimada (kWh)": dia.exportada_kwh,
                "Neta estimada (kWh)": dia.neta_kwh,
            }
            for dia in resultado.por_dia
        ]
    )
    st.dataframe(tabla, hide_index=True, width="stretch")
    st.download_button(
        "Descargar energía diaria estimada (CSV)",
        data=tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name="wattwise_energia_diaria_estimada.csv",
        mime="text/csv",
        key=f"exportar_energia_diaria_{clave}",
    )


def mostrar_panel_energia(registros: list[dict[str, object]], *, clave: str = "mediciones") -> None:
    """Solo estima kWh cuando el ingeniero confirma el modelo de muestras."""
    import streamlit as st

    st.markdown("#### Energía estimada por integración temporal")
    st.caption(
        "Requiere potencia activa total de un mismo punto, muestras instantáneas "
        "y límites de huecos temporales. No equivale a facturación."
    )
    if sum(registro.get("p_total_kw") is not None for registro in registros) < 2:
        st.info("No hay suficientes valores de potencia activa total para integrar.")
        return
    confirmado = st.checkbox(
        "Confirmo que P_total corresponde a muestras instantáneas comparables "
        "del mismo punto, no promedios de intervalos.",
        key=f"confirmar_modelo_energia_{clave}",
    )
    if not confirmado:
        st.info("Confirma la interpretación del analizador para habilitar los kWh.")
        return
    hueco = st.number_input(
        "Intervalo máximo admisible entre muestras (minutos)",
        min_value=1,
        max_value=1440,
        value=60,
        step=1,
        key=f"hueco_maximo_energia_{clave}",
    )
    try:
        resultado = analizar_energia_temporal(registros, hueco_maximo_minutos=int(hueco))
    except ValueError as error:
        st.warning(f"No se puede estimar energía: {error}")
        return
    if not resultado.tramos_validos:
        st.info("No existen intervalos consecutivos confiables para estimar kWh.")
        return
    _mostrar_metricas_energia(resultado, registros)
    st.caption(
        f"Intervalos aceptados: {resultado.tramos_validos}. "
        f"Descartados: {resultado.tramos_descartados}. "
        f"Fechas duplicadas: {resultado.fechas_duplicadas}. "
        "Los intervalos descartados no se extrapolan ni rellenan."
    )
    _mostrar_graficos_energia(resultado, clave)
    _mostrar_tabla_energia(resultado, clave)
    st.warning(
        "La energía estimada usa interpolación lineal entre muestras "
        "instantáneas válidas. Si el instrumento registra promedios por "
        "intervalo, debe utilizarse otro método. Revisa la cobertura temporal."
    )
