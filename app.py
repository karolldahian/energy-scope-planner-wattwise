"""Interfaz local de Energy Scope Planner | WattWise."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

import pandas as pd
import streamlit as st

from wattwise.dominio.inventario import analizar_inventario
from wattwise.dominio.mediciones import ResumenMediciones, analizar_mediciones
from wattwise.dominio.motores import analizar_motores
from wattwise.infraestructura.analisis_sqlite import guardar_analisis
from wattwise.infraestructura.lector_inventario_excel import (
    MAXIMO_BYTES as MAXIMO_INVENTARIO,
    leer_inventario_excel,
)
from wattwise.infraestructura.lector_mediciones_csv import (
    MAXIMO_BYTES as MAXIMO_MEDICIONES_CSV,
    leer_mediciones_csv,
)
from wattwise.infraestructura.lector_mediciones_detalladas import (
    leer_mediciones_detalladas,
)
from wattwise.infraestructura.lector_mediciones_excel import (
    MAXIMO_BYTES as MAXIMO_MEDICIONES_EXCEL,
    leer_mediciones_excel,
)
from wattwise.infraestructura.lector_motores_excel import (
    MAXIMO_BYTES as MAXIMO_MOTORES,
    leer_motores_excel,
)
from wattwise.infraestructura.plantillas_completas import crear_plantilla_completa
from wattwise.infraestructura.proyectos_sqlite import (
    Proyecto,
    crear_proyecto,
    eliminar_proyecto,
    listar_proyectos,
)
from wattwise.interfaz.exportacion_html import mostrar_exportar_html
from wattwise.interfaz.graficos import grafico_mediciones
from wattwise.interfaz.informe_secciones_ui import mostrar_informe_por_secciones
from wattwise.interfaz.mediciones_botones_vistas import (
    mostrar_panel_mediciones_detalladas,
)
from wattwise.interfaz.panel_archivos import (
    mostrar_guardado_original,
    seleccionar_fuente,
)
from wattwise.interfaz.panel_calidad_integral import mostrar_calidad_integral
from wattwise.interfaz.panel_vistas import mostrar_vistas
from wattwise.interfaz.paneles_botones_vistas import (
    mostrar_inventario_completo,
    mostrar_motores_completo,
)

RUTA_PROYECTOS = Path(__file__).resolve().parent / "data" / "proyectos.sqlite3"
MIME_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ArchivoMediciones(Protocol):
    """Datos mínimos del archivo CSV o XLSX recibido por Streamlit."""

    name: str
    size: int

    def getvalue(self) -> bytes:
        """Devuelve los bytes originales del archivo."""
        ...


def configurar_pagina() -> None:
    """Configura la apariencia general de WattWise."""
    st.set_page_config(
        page_title="Energy Scope Planner | WattWise",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1550px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        h1, h2, h3 { letter-spacing: -0.025em; }
        [data-testid="stSidebar"] { border-right: 1px solid #80808033; }
        [data-testid="stMetric"] {
            padding: 14px;
            border: 1px solid #80808033;
            border-radius: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def mostrar_barra_lateral() -> None:
    """Presenta información breve y una guía; no selecciona proyectos."""
    with st.sidebar:
        st.title("Energy Scope Planner")
        st.caption("⚡ WattWise")
        st.write(
            "Herramienta en desarrollo para integrar, analizar y documentar "
            "información eléctrica de instalaciones comerciales y de servicios."
        )

        st.divider()
        st.subheader("Cómo trabajar")
        st.markdown(
            "1. Selecciona el proyecto en **Proyectos**.\n"
            "2. Importa archivos de inventarios, mediciones o motores.\n"
            "3. Revisa la calidad de los datos y explora los resultados.\n"
            "4. Guarda las vistas y las observaciones relevantes.\n"
            "5. Organiza tus hallazgos en un informe técnico."
        )

        st.divider()
        st.subheader("Alcance actual")
        st.write(
            "Inventarios, mediciones, motores, calidad de datos, "
            "vistas reproducibles e informes personalizados."
        )

        st.divider()
        st.caption(
            "WattWise apoya la interpretación de información eléctrica, "
            "pero no sustituye el criterio profesional ni certifica instalaciones."
        )


def _tarjeta_inicio(titulo: str, descripcion: str, icono: str) -> None:
    """Dibuja una tarjeta de capacidades sin datos inventados."""
    with st.container(border=True):
        st.markdown(f"#### {icono} {titulo}")
        st.write(descripcion)


def _capacidades_inicio() -> None:
    """Resume las seis áreas de trabajo implementadas actualmente."""
    st.subheader("¿Qué puedes hacer con WattWise?")
    primera = st.columns(3, gap="medium")
    segunda = st.columns(3, gap="medium")

    with primera[0]:
        _tarjeta_inicio(
            "Inventarios",
            "Organizar cargas, áreas y equipos; comparar potencias instaladas "
            "y localizar concentraciones mediante indicadores y gráficas.",
            "📋",
        )
    with primera[1]:
        _tarjeta_inicio(
            "Mediciones",
            "Explorar el comportamiento temporal de potencia activa, "
            "corriente, tensión y factor de potencia, según los registros disponibles.",
            "📈",
        )
    with primera[2]:
        _tarjeta_inicio(
            "Motores",
            "Comparar corrientes nominales y medidas, potencias nominales "
            "y horas de operación declaradas.",
            "⚙️",
        )
    with segunda[0]:
        _tarjeta_inicio(
            "Calidad de datos",
            "Localizar vacíos, ceros, registros inválidos y otras señales "
            "que requieren revisar los archivos originales.",
            "🔎",
        )
    with segunda[1]:
        _tarjeta_inicio(
            "Vistas",
            "Guardar y recuperar configuraciones de análisis, "
            "filtros, indicadores y observaciones del proyecto.",
            "📊",
        )
    with segunda[2]:
        _tarjeta_inicio(
            "Informes",
            "Preparar documentos técnicos con imágenes, "
            "textos y observaciones elegidas por el profesional.",
            "📄",
        )


def _guia_inventarios() -> None:
    with st.expander("Inventarios · ¿para qué sirven las gráficas?"):
        st.markdown(
            "- **Pareto por tipo de carga:** muestra qué categorías concentran "
            "mayor potencia instalada.\n"
            "- **Pareto por equipo:** identifica equipos de mayor capacidad "
            "instalada para orientar la revisión.\n"
            "- **Potencia por área:** compara áreas y ayuda a localizar "
            "concentraciones de potencia.\n"
            "- **Distribución por tipo de carga:** representa la participación "
            "relativa de cada categoría.\n"
            "- **Matriz de potencia instalada:** relaciona áreas y tipos "
            "de carga para revelar concentraciones."
        )
        st.caption(
            "La potencia instalada no equivale al consumo de energía (kWh). "
            "Los indicadores describen el inventario declarado."
        )


def _guia_mediciones() -> None:
    with st.expander("Mediciones · ¿para qué sirven las gráficas?"):
        st.markdown(
            "- **Potencia activa:** muestra máximos, variaciones y "
            "periodos de mayor demanda registrada.\n"
            "- **Corrientes:** permite comparar fases y revisar "
            "cambios en el tiempo, cuando esas mediciones existen.\n"
            "- **Tensiones:** ayuda a localizar variaciones y "
            "valores extremos registrados.\n"
            "- **Factor de potencia:** facilita explorar su comportamiento "
            "durante el periodo medido.\n"
            "- **Exploración horaria y diagnóstico gráfico:** permite "
            "examinar patrones temporales y relaciones entre variables."
        )
        st.caption(
            "Máximos, mínimos, promedios y percentiles son indicadores "
            "descriptivos. Una gráfica no establece por sí sola una falla "
            "ni un incumplimiento normativo."
        )


def _guia_motores() -> None:
    with st.expander("Motores · ¿para qué sirven las gráficas?"):
        st.markdown(
            "- **Corriente nominal frente a medida:** identifica relaciones "
            "que merecen revisión del profesional.\n"
            "- **Mapa de revisión:** ayuda a localizar motores con valores "
            "de corriente u horas de operación llamativos.\n"
            "- **Potencia nominal por motor:** compara capacidades "
            "mecánicas declaradas, expresadas en HP.\n"
            "- **Horas de operación por motor:** destaca equipos con "
            "mayor tiempo mensual registrado."
        )
        st.caption(
            "La relación entre corriente medida y nominal no determina "
            "directamente la eficiencia, el consumo de energía ni una falla."
        )


def _guias_inicio() -> None:
    """Explica gráficas y límites sin afirmar diagnósticos automáticos."""
    st.subheader("¿Para qué sirven las gráficas y los indicadores?")
    st.write(
        "Cada visualización responde a una pregunta distinta. "
        "El profesional decide qué gráfica utilizar y cómo interpretar "
        "sus resultados a partir del objetivo del proyecto."
    )
    _guia_inventarios()
    _guia_mediciones()
    _guia_motores()


def _evolucion_inicio() -> None:
    """Separa explícitamente la visión futura de las funciones actuales."""
    st.subheader("Visión de Energy Scope Planner")
    st.caption(
        "Energy Scope Planner podrá crecer con otros módulos especializados. "
        "Las siguientes capacidades son líneas futuras de desarrollo y no "
        "se presentan como funciones disponibles actualmente en WattWise."
    )
    primera = st.columns(2, gap="medium")
    segunda = st.columns(2, gap="medium")

    with primera[0]:
        _tarjeta_inicio(
            "IA para analizar mediciones",
            "Evaluar detección de comportamientos atípicos con Isolation Forest "
            "y agrupación de perfiles operativos con K-Means, "
            "si existen datos suficientes y comparables.",
            "🧠",
        )
    with primera[1]:
        _tarjeta_inicio(
            "Fuentes de energía",
            "Explorar la integración de red, generación solar y eólica, "
            "generación de respaldo y sistemas térmicos, "
            "con balances y fronteras bien definidos.",
            "☀️",
        )
    with segunda[0]:
        _tarjeta_inicio(
            "Desempeño energético",
            "Desarrollar indicadores energéticos definidos por el usuario, "
            "líneas base y comparaciones entre periodos a partir "
            "de consumos históricos y variables pertinentes.",
            "📉",
        )
    with segunda[1]:
        _tarjeta_inicio(
            "Planificación y asistencia contextual",
            "Documentar oportunidades y objetivos, y evaluar un asistente "
            "que consulte resultados rastreables sin sustituir "
            "el criterio profesional.",
            "🎯",
        )


def mostrar_inicio() -> None:
    """Presenta origen, alcance, criterios técnicos y futuro de WattWise."""
    st.caption("⚡ WattWise")
    st.title("ENERGY SCOPE PLANNER")
    st.subheader("Módulo de planificación y revisión energética")
    st.markdown(
        "**Desarrollo de una plataforma auditable para la integración "
        "y análisis de información energética en instalaciones "
        "comerciales y de servicios.**"
    )
    st.write(
        "WattWise es la primera implementación funcional de Energy Scope Planner. "
        "Está orientado a organizar, validar, analizar y documentar información "
        "eléctrica para apoyar la planificación y revisión energética en "
        "instalaciones comerciales y de servicios, sin sustituir el criterio profesional."
    )

    st.divider()
    motivo, objetivo = st.columns(2, gap="large")
    with motivo, st.container(border=True):
        st.markdown("### ¿Por qué nació WattWise?")
        st.write(
            "En las revisiones energéticas, los datos suelen encontrarse "
            "dispersos en inventarios, hojas de cálculo y registros de medición "
            "con estructuras, unidades y niveles de calidad diferentes. "
            "Prepararlos e interpretarlos dificulta mantener un análisis trazable."
        )
    with objetivo, st.container(border=True):
        st.markdown("### Nuestro objetivo")
        st.write(
            "Apoyar la planificación y revisión energética mediante un módulo "
            "auditable que conserva los archivos originales, facilita el análisis "
            "técnico y permite documentar observaciones e informes."
        )
        st.markdown(
            "**WattWise no reemplaza la interpretación del ingeniero; "
            "busca proporcionarle mejores herramientas.**"
        )

    st.divider()
    _capacidades_inicio()

    st.divider()
    st.subheader("Del archivo al informe")
    st.markdown("**Organizar → Verificar → Visualizar → Interpretar → Documentar**")
    st.write(
        "Las plantillas estructuran la información; Calidad de datos "
        "ayuda a localizar inconsistencias; los filtros, indicadores "
        "y gráficas facilitan la exploración; y las vistas e informes "
        "permiten conservar los resultados y comentarios del ingeniero."
    )

    st.divider()
    _guias_inicio()

    st.divider()
    _evolucion_inicio()

    st.divider()
    with st.container(border=True):
        st.markdown("### Relación con la gestión energética")
        st.write(
            "WattWise, como primer módulo de Energy Scope Planner, apoya "
            "actividades de organización y revisión de datos vinculadas con "
            "la planificación energética. ISO 50001 es un referente conceptual "
            "para orientar su evolución."
        )
        st.caption(
            "La versión actual no implementa un Sistema de Gestión de "
            "la Energía completo ni constituye evidencia de conformidad "
            "o certificación ISO 50001."
        )

    with st.expander("Acerca del desarrollo"):
        st.write(
            "Energy Scope Planner es la plataforma general proyectada para "
            "integrar distintas soluciones de análisis energético. WattWise es "
            "su primera implementación, dedicada a la planificación y revisión "
            "energética. En etapas posteriores podrán incorporarse otros módulos "
            "especializados, según las necesidades técnicas y la validación de datos."
        )


def _preparar_datos(valor: object) -> object:
    """Convierte resultados del dominio a datos compatibles con JSON."""
    if is_dataclass(valor) and not isinstance(valor, type):
        return _preparar_datos(asdict(valor))

    if isinstance(valor, (date, datetime)):
        return valor.isoformat()

    if isinstance(valor, dict):
        return {str(clave): _preparar_datos(item) for clave, item in valor.items()}

    if isinstance(valor, (tuple, list)):
        return [_preparar_datos(item) for item in valor]

    return valor


def mostrar_guardado(tipo: str, resultado: object) -> None:
    """Conserva el guardado heredado para mediciones del formato inicial."""
    st.markdown("#### Guardar resultados")
    proyecto_id = st.session_state.get("wattwise_proyecto_id")

    if not isinstance(proyecto_id, int):
        st.info("Selecciona un proyecto de trabajo en la pestaña Proyectos.")
        return

    titulo = st.text_input(
        "Título del análisis",
        value=f"Análisis de {tipo}",
        key=f"titulo_{tipo}",
    )

    if st.button(
        "Guardar resultados",
        key=f"guardar_{tipo}",
    ):
        try:
            guardar_analisis(
                RUTA_PROYECTOS,
                proyecto_id,
                tipo,
                titulo,
                _preparar_datos(resultado),
            )
            st.success("Análisis guardado en el proyecto activo.")
        except (ValueError, OSError, sqlite3.Error) as error:
            st.error(f"No se pudo guardar el análisis: {error}")


def _sincronizar_contexto_proyecto() -> str | None:
    """Aísla los widgets al cambiar de proyecto sin borrar datos de SQLite.

    Se ejecuta antes de crear los widgets de las ocho pestañas para impedir
    que un archivo, filtro, texto o captura de otro proyecto permanezca activo.
    """
    actual = st.session_state.get("wattwise_proyecto_id")
    try:
        nombres = {proyecto.id: proyecto.nombre for proyecto in listar_proyectos(RUTA_PROYECTOS)}
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No se pudieron verificar los proyectos: {error}")
        nombres = {}

    if type(actual) is not int or actual not in nombres:
        actual = None
        st.session_state["wattwise_proyecto_id"] = None

    clave_contexto = "_ww_contexto_proyecto"
    if clave_contexto not in st.session_state or st.session_state[clave_contexto] != actual:
        conservar = {
            "wattwise_proyecto_id",
            "wattwise_proyecto_elegido",
            clave_contexto,
        }
        for clave in list(st.session_state):
            if clave not in conservar:
                del st.session_state[clave]
        st.session_state[clave_contexto] = actual

    return nombres.get(actual)


def _seleccionar_proyecto(proyectos: list[Proyecto]) -> int | None:
    """Elige el proyecto en Proyectos y conserva el ID usado por las pestañas."""
    opciones = {proyecto.id: proyecto.nombre for proyecto in proyectos}
    actual = st.session_state.get("wattwise_proyecto_id")
    if type(actual) is not int or actual not in opciones:
        actual = None
        st.session_state["wattwise_proyecto_id"] = None

    if not opciones:
        st.info("Crea tu primer proyecto para comenzar.")
        return None

    clave = "wattwise_proyecto_elegido"
    if st.session_state.get(clave) not in opciones:
        st.session_state[clave] = actual if actual is not None else next(iter(opciones))

    st.subheader("Proyecto de trabajo")
    elegido = st.selectbox(
        "Selecciona un proyecto",
        list(opciones),
        format_func=lambda identificador: opciones[identificador],
        key=clave,
    )

    if st.button("Trabajar en este proyecto", key="ww_proyectos_activar"):
        st.session_state["wattwise_proyecto_id"] = elegido
        st.rerun()

    if actual is None:
        st.info(
            "No hay un proyecto de trabajo seleccionado. "
            "Elige uno y pulsa «Trabajar en este proyecto» "
            "para asociarle archivos, vistas, notas e informes."
        )
    else:
        st.success(f"Estamos trabajando en: {opciones[actual]}")
        if elegido != actual:
            st.caption("El proyecto de trabajo cambiará solamente cuando pulses el botón.")

    return actual


def _formulario_crear_proyecto() -> None:
    """Conserva la creación de proyectos y sus validaciones originales."""
    with st.form("crear_proyecto", clear_on_submit=True):
        nombre = st.text_input("Nombre del proyecto", max_chars=120)
        descripcion = st.text_area("Descripción (opcional)", max_chars=1000)
        enviado = st.form_submit_button("Crear proyecto")

    if enviado:
        try:
            crear_proyecto(RUTA_PROYECTOS, nombre, descripcion)
            st.success("Proyecto creado correctamente.")
            st.rerun()
        except (ValueError, OSError, sqlite3.Error) as error:
            st.error(f"No se pudo crear el proyecto: {error}")


def _eliminar_proyecto(opciones: dict[str, int]) -> None:
    """Confirma el borrado y desactiva el proyecto si fue eliminado."""
    with st.expander("Eliminar proyecto"):
        seleccionado = st.selectbox("Proyecto", options=list(opciones))
        confirmar = st.checkbox("Confirmo que deseo eliminar este proyecto")
        st.warning(
            "Se eliminarán sus análisis, notas, comparaciones históricas, "
            "vistas, capturas y archivos originales."
        )

        if st.button("Eliminar proyecto", disabled=not confirmar):
            try:
                proyecto_eliminado = opciones[seleccionado]
                if eliminar_proyecto(RUTA_PROYECTOS, proyecto_eliminado):
                    if st.session_state.get("wattwise_proyecto_id") == proyecto_eliminado:
                        st.session_state["wattwise_proyecto_id"] = None
                    if st.session_state.get("wattwise_proyecto_elegido") == proyecto_eliminado:
                        del st.session_state["wattwise_proyecto_elegido"]
                    st.rerun()
                else:
                    st.warning("El proyecto ya no existe.")
            except (ValueError, OSError, sqlite3.Error) as error:
                st.error(f"No se pudo eliminar el proyecto: {error}")


def mostrar_proyectos() -> None:
    """Centraliza selección, creación, consulta y eliminación de proyectos."""
    st.header("Mis proyectos")
    st.caption(
        "Selecciona aquí el proyecto en el que vas a trabajar. "
        "Los archivos, análisis, vistas y notas se guardan en SQLite local."
    )

    try:
        proyectos = listar_proyectos(RUTA_PROYECTOS)
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No se pudieron consultar los proyectos: {error}")
        return

    _seleccionar_proyecto(proyectos)
    st.divider()
    st.subheader("Crear un proyecto")
    _formulario_crear_proyecto()

    if not proyectos:
        return

    st.divider()
    opciones = {f"{proyecto.id} - {proyecto.nombre}": proyecto.id for proyecto in proyectos}
    _eliminar_proyecto(opciones)


def _boton_plantilla(tipo: str) -> None:
    """Ofrece XLSX con las columnas oficiales."""
    st.download_button(
        "Descargar plantilla",
        data=crear_plantilla_completa(tipo),
        file_name=f"wattwise_plantilla_{tipo}.xlsx",
        mime=MIME_EXCEL,
        key=f"plantilla_completa_{tipo}",
    )


def mostrar_inventarios() -> None:
    """Importa inventario y muestra sus cinco visualizaciones."""
    st.header("Inventarios eléctricos")
    _boton_plantilla("inventario")

    archivo = seleccionar_fuente(
        RUTA_PROYECTOS,
        "inventario",
        ["xlsx"],
    )

    if archivo is None:
        st.info("Importa un inventario para comenzar el análisis.")
        return

    if archivo.size > MAXIMO_INVENTARIO:
        st.error("Archivo mayor que 25 MB.")
        return

    try:
        resultado = analizar_inventario(
            leer_inventario_excel(
                archivo.getvalue(),
                archivo.name,
            )
        )
    except ValueError as error:
        st.error(f"Archivo rechazado: {error}")
        return

    st.success("Inventario validado.")
    mostrar_guardado_original(
        RUTA_PROYECTOS,
        "inventario",
        archivo,
    )
    mostrar_inventario_completo(
        resultado,
        RUTA_PROYECTOS,
    )


def _leer_archivo_mediciones(
    archivo: ArchivoMediciones,
) -> list[dict[str, object]]:
    """Selecciona CSV o Excel del formato inicial según extensión."""
    nombre = archivo.name
    extension = nombre.rsplit(".", maxsplit=1)[-1].lower()

    if extension == "csv":
        if archivo.size > MAXIMO_MEDICIONES_CSV:
            raise ValueError("CSV mayor que el límite permitido.")
        return leer_mediciones_csv(
            archivo.getvalue(),
            nombre,
        )

    if extension == "xlsx":
        if archivo.size > MAXIMO_MEDICIONES_EXCEL:
            raise ValueError("Excel mayor que 25 MB.")
        return leer_mediciones_excel(
            archivo.getvalue(),
            nombre,
        )

    raise ValueError("Solo se admiten archivos CSV o XLSX.")


def _mostrar_mediciones_iniciales(
    resultado: ResumenMediciones,
) -> None:
    """Conserva la interfaz del formato inicial de cinco columnas."""
    st.success("Mediciones del formato inicial validadas.")

    a, b, c = st.columns(3)
    a.metric(
        "Potencia máxima registrada",
        f"{resultado.potencia_maxima_kw:,.3f} kW",
    )
    b.metric(
        "Tensión mínima",
        f"{resultado.tension_minima_v:,.2f} V",
    )
    c.metric(
        "Tensión máxima",
        f"{resultado.tension_maxima_v:,.2f} V",
    )

    if resultado.energia_estimada_kwh is not None:
        st.metric(
            "Energía estimada",
            f"{resultado.energia_estimada_kwh:,.3f} kWh",
        )
    else:
        st.info("Se necesitan dos muestras para estimar energía.")

    st.caption(
        "La integración supone interpolación lineal entre muestras. "
        "No sustituye un contador de energía certificado."
    )
    grafico = grafico_mediciones(resultado)
    st.echarts_chart(
        grafico,
        height=470,
        key="mediciones_potencia",
        alt="Potencia activa en kW a lo largo del tiempo",
    )
    mostrar_exportar_html(
        grafico,
        "Potencia activa (kW)",
        "mediciones_iniciales",
    )

    tabla = pd.DataFrame(
        [
            {
                "Fecha y hora": m.fecha_hora,
                "Tensión (V)": m.tension_v,
                "Corriente (A)": m.corriente_a,
                "Factor de potencia": m.factor_potencia,
                "Potencia activa (kW)": m.potencia_activa_kw,
            }
            for m in resultado.registros
        ]
    )
    st.dataframe(
        tabla,
        width="stretch",
        hide_index=True,
    )

    # El CSV / XLSX inicial no tiene los campos requeridos
    # por el contrato de Vistas para mediciones detalladas.
    # Se conserva el guardado anterior sin inventar filtros.
    mostrar_guardado("mediciones", resultado)


def mostrar_mediciones() -> None:
    """Conserva CSV inicial y Excel detallado de 17 columnas."""
    st.header("Mediciones eléctricas")
    _boton_plantilla("mediciones")

    archivo = seleccionar_fuente(
        RUTA_PROYECTOS,
        "mediciones",
        ["csv", "xlsx"],
    )

    if archivo is None:
        st.info("Importa mediciones para comenzar el análisis.")
        return

    if archivo.name.lower().endswith(".xlsx"):
        try:
            importado = leer_mediciones_detalladas(
                archivo.getvalue(),
                archivo.name,
            )
        except ValueError as error_detallado:
            try:
                resultado = analizar_mediciones(_leer_archivo_mediciones(archivo))
            except ValueError:
                st.error(f"Archivo rechazado: {error_detallado}")
                return
        else:
            mostrar_guardado_original(
                RUTA_PROYECTOS,
                "mediciones",
                archivo,
            )
            mostrar_panel_mediciones_detalladas(importado)
            return
    else:
        try:
            resultado = analizar_mediciones(_leer_archivo_mediciones(archivo))
        except ValueError as error:
            st.error(f"Archivo rechazado: {error}")
            return

    mostrar_guardado_original(
        RUTA_PROYECTOS,
        "mediciones",
        archivo,
    )
    _mostrar_mediciones_iniciales(resultado)


def mostrar_motores() -> None:
    """Importa motores y presenta sus cuatro visualizaciones."""
    st.header("Motores eléctricos")
    _boton_plantilla("motores")

    archivo = seleccionar_fuente(
        RUTA_PROYECTOS,
        "motores",
        ["xlsx"],
    )

    if archivo is None:
        st.info("Importa motores para comenzar el análisis.")
        return

    if archivo.size > MAXIMO_MOTORES:
        st.error("Archivo mayor que 25 MB.")
        return

    try:
        resultado = analizar_motores(
            leer_motores_excel(
                archivo.getvalue(),
                archivo.name,
            )
        )
    except ValueError as error:
        st.error(f"Archivo rechazado: {error}")
        return

    st.success("Motores validados.")
    mostrar_guardado_original(
        RUTA_PROYECTOS,
        "motores",
        archivo,
    )
    mostrar_motores_completo(
        resultado,
        RUTA_PROYECTOS,
    )


def main() -> None:
    """Organiza las ocho pestañas principales."""
    configurar_pagina()
    nombre_proyecto = _sincronizar_contexto_proyecto()
    mostrar_barra_lateral()
    st.caption("ENERGY SCOPE PLANNER / WATTWISE")
    if nombre_proyecto is None:
        st.caption("📂 Proyecto de trabajo: sin seleccionar · Actívalo en Proyectos")
    else:
        st.caption(f"📂 Estamos trabajando en: {nombre_proyecto}")

    pestanas = st.tabs(
        [
            "Inicio",
            "Proyectos",
            "Inventarios",
            "Mediciones",
            "Motores",
            "Calidad de datos",
            "Vistas",
            "Informes",
        ]
    )

    with pestanas[0]:
        mostrar_inicio()

    with pestanas[1]:
        mostrar_proyectos()

    with pestanas[2]:
        mostrar_inventarios()

    with pestanas[3]:
        mostrar_mediciones()

    with pestanas[4]:
        mostrar_motores()

    with pestanas[5]:
        mostrar_calidad_integral(RUTA_PROYECTOS)

    with pestanas[6]:
        mostrar_vistas(RUTA_PROYECTOS)

    with pestanas[7]:
        mostrar_informe_por_secciones(RUTA_PROYECTOS)

    st.divider()
    st.caption("Energy Scope Planner | WattWise · Análisis sujeto a revisión profesional")


if __name__ == "__main__":
    main()
