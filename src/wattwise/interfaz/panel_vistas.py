"""Vistas reproducibles con gráficos y KPI de los módulos originales."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from pathlib import Path

from wattwise.dominio.calidad_integral import auditar_excel
from wattwise.dominio.inventario import analizar_inventario
from wattwise.dominio.motores import analizar_motores
from wattwise.dominio.vistas import FILTROS, GRAFICAS, MARCAS, SERIES
from wattwise.infraestructura.archivos_proyecto import (
    ArchivoProyecto,
    listar_archivos,
    recuperar_archivo,
)
from wattwise.infraestructura.lector_inventario_excel import leer_inventario_excel
from wattwise.infraestructura.lector_mediciones_detalladas import leer_mediciones_detalladas
from wattwise.infraestructura.lector_motores_excel import leer_motores_excel
from wattwise.infraestructura.observaciones_sqlite import (
    actualizar_visibilidad_observacion,
    eliminar_observacion,
    guardar_observacion,
    listar_observaciones,
)
from wattwise.infraestructura.proyectos_sqlite import listar_proyectos
from wattwise.infraestructura.vistas_sqlite import (
    VistaGuardada,
    eliminar_vistas,
    guardar_vista,
    listar_vistas,
)
from wattwise.interfaz.exportacion_html import mostrar_exportar_html
from wattwise.interfaz.graficos_completos import (
    barras_areas,
    barras_motores,
    corrientes_motores,
    dona_cargas,
    mapa_revision_motores,
    matriz_inventario,
    pareto_inventario,
)
from wattwise.interfaz.graficos_mediciones_adaptativos import (
    grafico_barras_horarias,
    grafico_diagnostico,
)
from wattwise.interfaz.mediciones_avanzadas import (
    GRUPOS,
    _contexto_grafica,
    _etiqueta,
    _graficas_disponibles,
    _mostrar_kpi,
    _texto_diagnostico,
    estadisticas,
    grafico_temporal,
)
from wattwise.interfaz.paneles_completos import (
    VISTAS_INVENTARIO,
    VISTAS_MOTORES,
    _kpis_inventario,
    _kpis_motores,
    registros_inventario,
    registros_motores,
)
from wattwise.interfaz.reproduccion_vistas import VistaReconstruida, reconstruir_vista
from wattwise.interfaz.vistas_calidad import (
    mostrar_guardar_calidad_en_vistas,
    mostrar_notas_vista_calidad,
    mostrar_vistas_calidad,
)


def _normalizar(texto: str) -> str:
    """Empareja nombres heredados sin alterar los contratos guardados."""
    base = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in base if not unicodedata.combining(c))
    return " ".join(sin_tildes.casefold().split())


def _nombre_original(tipo: str, nombre: str) -> str:
    """Usa el nombre visible de la pestaña de origen cuando coincide."""
    if tipo == "inventario":
        nombres = VISTAS_INVENTARIO
    elif tipo == "motores":
        nombres = VISTAS_MOTORES
    else:
        nombres = tuple(GRUPOS)
        if nombre in SERIES:
            nombres_series = tuple(SERIES[nombre])
            for grupo, campos in GRUPOS.items():
                if set(nombres_series) == set(campos):
                    return grupo
    return next(
        (n for n in nombres if _normalizar(n) == _normalizar(nombre)),
        nombre,
    )


def _opciones_grafica(tipo: str) -> dict[str, str]:
    """Presenta nombres originales y persiste el nombre válido del dominio."""
    return {_nombre_original(tipo, nombre): nombre for nombre in GRAFICAS[tipo]}


def _cargar_registros(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int,
    tipo: str,
) -> list[dict[str, object]]:
    """Lee el original con el mismo lector de la pestaña de origen."""
    metadatos, contenido = recuperar_archivo(ruta, proyecto_id, archivo_id)
    if metadatos.tipo != tipo:
        raise ValueError("El archivo corresponde a otro módulo.")
    if tipo == "inventario":
        inventario = leer_inventario_excel(contenido, metadatos.nombre)
        resultado = analizar_inventario(inventario)
        return registros_inventario(resultado)
    if tipo == "motores":
        motores = leer_motores_excel(contenido, metadatos.nombre)
        resultado = analizar_motores(motores)
        return registros_motores(resultado)
    if not metadatos.nombre.lower().endswith(".xlsx"):
        raise ValueError("La vista de mediciones requiere el XLSX detallado.")
    return leer_mediciones_detalladas(contenido, metadatos.nombre).registros


def _elegir_archivo(
    ruta: Path,
    proyecto_id: int,
    tipo: str,
) -> ArchivoProyecto | None:
    """Limita la selección a archivos originales del proyecto activo."""
    import streamlit as st

    archivos = listar_archivos(ruta, proyecto_id, tipo)
    if tipo == "mediciones":
        archivos = [a for a in archivos if a.nombre.lower().endswith(".xlsx")]
    if not archivos:
        st.info("Guarda primero un Excel original compatible en este proyecto.")
        return None
    opciones = {f"{a.nombre} (archivo {a.id})": a for a in archivos}
    elegido = st.selectbox(
        "Archivo de origen",
        list(opciones),
        key=f"vista_origen_{proyecto_id}_{tipo}",
    )
    return opciones[elegido]


def _filtros_nuevos(
    registros: list[dict[str, object]],
    tipo: str,
    prefijo: str,
) -> dict[str, str]:
    """Conserva los filtros definidos en el contrato de vistas."""
    import streamlit as st

    filtros: dict[str, str] = {}
    columnas = st.columns(len(FILTROS[tipo]))
    for indice, campo in enumerate(FILTROS[tipo]):
        valores = sorted({str(fila.get(campo) or "Sin especificar") for fila in registros})
        with columnas[indice]:
            filtros[campo] = st.selectbox(
                campo.replace("_", " ").capitalize(),
                ["Todos", *valores],
                key=f"{prefijo}_{campo}",
            )
    return filtros


def _registros_filtrados(
    registros: list[dict[str, object]],
    filtros: dict[str, str],
) -> list[dict[str, object]]:
    """Filtra sin mezclar fuentes, puntos ni equipos."""
    for campo, valor in filtros.items():
        if valor != "Todos":
            registros = [
                fila for fila in registros if str(fila.get(campo) or "Sin especificar") == valor
            ]
    return registros


def _opciones_nuevas(
    tipo: str,
    grafica: str,
    registros: list[dict[str, object]],
    prefijo: str,
) -> dict[str, object]:
    """Solicita únicamente los controles que conoce el contrato vigente."""
    import streamlit as st

    if tipo == "inventario":
        if not grafica.startswith("Pareto"):
            return {"linea_barras": True, "acumulado": True, "umbral_80": True}
        return {
            "linea_barras": st.checkbox("Línea de cumbre", True, key=f"{prefijo}_linea"),
            "acumulado": st.checkbox("Porcentaje acumulado", True, key=f"{prefijo}_acu"),
            "umbral_80": st.checkbox("Referencia del 80 %", True, key=f"{prefijo}_80"),
        }
    if tipo == "motores":
        variables = ["relacion"]
        if any(fila.get("horas_operacion_mes") is not None for fila in registros):
            variables.append("horas")
        variable = (
            st.selectbox("Variable del mapa", variables, key=f"{prefijo}_mapa")
            if _normalizar(grafica) == _normalizar(VISTAS_MOTORES[1])
            else "relacion"
        )
        return {"mapa_variable": variable}
    return {}


def _config_mediciones(
    registros: list[dict[str, object]],
    grafica: str,
    prefijo: str,
) -> dict[str, object]:
    """Usa las mismas series y referencias del contrato de mediciones."""
    import streamlit as st

    disponibles = [campo for campo in SERIES[grafica] if estadisticas(registros, campo) is not None]
    if not disponibles:
        raise ValueError("El grupo no contiene series con datos utilizables.")

    fechas = [fila["fecha_hora"].date() for fila in registros]
    inicio = st.date_input("Desde", min(fechas), key=f"{prefijo}_desde")
    fin = st.date_input("Hasta", max(fechas), key=f"{prefijo}_hasta")

    series = st.multiselect(
        "Series visibles",
        disponibles,
        default=disponibles,
        format_func=_etiqueta,
        key=f"{prefijo}_series",
    )
    if not series:
        raise ValueError("Selecciona al menos una serie antes de guardar.")

    referencia = st.selectbox(
        "Serie de referencia",
        series,
        format_func=_etiqueta,
        key=f"{prefijo}_referencia",
    )
    marcas = st.multiselect(
        "Líneas estadísticas",
        MARCAS,
        default=[],
        key=f"{prefijo}_marcas",
    )
    return {
        "periodo": {
            "desde": inicio.isoformat(),
            "hasta": fin.isoformat(),
        },
        "series": series,
        "referencia": referencia,
        "marcas": marcas,
    }


def _elegir_grafica(tipo: str, prefijo: str) -> str:
    """Evita renombrar la configuración que valida dominio.vistas."""
    import streamlit as st

    opciones = _opciones_grafica(tipo)
    etiqueta = st.selectbox(
        "Gráfica",
        list(opciones),
        key=f"{prefijo}_grafica",
    )
    return opciones[etiqueta]


def _grafica_inventario(
    registros: list[dict[str, object]],
    nombre: str,
    opciones: dict[str, object],
    mostrar_valores: bool,
) -> dict[str, object] | None:
    """Llama exactamente a los gráficos del panel Inventario."""
    indice = next(
        (
            indice
            for indice, etiqueta in enumerate(VISTAS_INVENTARIO)
            if _normalizar(etiqueta) == _normalizar(nombre)
        ),
        None,
    )
    if indice is None:
        return None
    if indice in (0, 1):
        return pareto_inventario(
            registros,
            "tipo_carga" if indice == 0 else "equipo",
            linea_barras=bool(opciones.get("linea_barras", True)),
            acumulado=bool(opciones.get("acumulado", True)),
            umbral_80=bool(opciones.get("umbral_80", True)),
            mostrar_valores=mostrar_valores,
        )
    graficas = (barras_areas, dona_cargas, matriz_inventario)
    return graficas[indice - 2](registros, mostrar_valores=mostrar_valores)


def _mostrar_echarts(
    grafico: dict[str, object] | None,
    titulo: str,
    clave: str,
    altura: int,
    *,
    exportar: bool = True,
) -> None:
    """Presenta una gráfica sin sustituir los renderizadores originales."""
    import streamlit as st

    if grafico is None:
        st.info("No hay datos suficientes para mostrar esta gráfica.")
        return
    st.echarts_chart(grafico, height=altura, key=clave, alt=titulo)
    if exportar:
        mostrar_exportar_html(grafico, titulo, clave)


def _vista_inventario(
    resultado: VistaReconstruida,
    configuracion: dict[str, object],
    clave: str,
) -> None:
    """Conserva nombres, gráfico y los cuatro KPI con desgloses originales."""
    import streamlit as st

    nombre = _nombre_original("inventario", str(configuracion["grafica"]))
    opciones = configuracion.get("opciones", {})
    izquierda, derecha = st.columns([3, 1], gap="large")
    with derecha:
        st.markdown("#### Controles")
        st.write(nombre)
        mostrar = st.checkbox(
            "Visualización de datos numéricos",
            value=True,
            key=f"vista_valores_inv_{clave}",
        )
        st.caption("Leyenda interactiva, zoom, restauración y descarga PNG.")
        espacio_html = st.empty()

    with izquierda:
        grafico = _grafica_inventario(
            resultado.registros,
            nombre,
            opciones,
            mostrar,
        )
        if grafico is None:
            st.warning("La vista usa un nombre anterior que no coincide con Inventario.")
            grafico = resultado.grafico
        _mostrar_echarts(
            grafico,
            nombre,
            f"vista_inv_{clave}",
            570,
            exportar=False,
        )

    with espacio_html.container():
        mostrar_exportar_html(
            grafico,
            nombre,
            f"vista_inv_{clave}",
        )

    st.markdown("#### Indicadores del inventario filtrado")
    _kpis_inventario(resultado.registros)


def _vista_motores(
    resultado: VistaReconstruida,
    configuracion: dict[str, object],
    clave: str,
) -> None:
    """Reutiliza gráficos y KPI 2x2 del panel Motores."""
    import streamlit as st

    nombre = _nombre_original("motores", str(configuracion["grafica"]))
    indice = next(
        (
            indice
            for indice, etiqueta in enumerate(VISTAS_MOTORES)
            if _normalizar(etiqueta) == _normalizar(nombre)
        ),
        None,
    )
    izquierda, derecha = st.columns([3, 1], gap="large")

    with derecha:
        st.markdown("#### Controles")
        st.write(nombre)
        mostrar = st.checkbox(
            "Visualización de datos numéricos",
            value=True,
            key=f"vista_valores_motor_{clave}",
        )
        st.caption("Relación de corrientes: indicador descriptivo, no diagnóstico.")
        espacio_html = st.empty()

    with izquierda:
        grafico = _graficos_motores(
            resultado,
            indice,
            nombre,
            mostrar,
            clave,
        )

    with espacio_html.container():
        mostrar_exportar_html(
            grafico,
            nombre,
            f"vista_m_principal_{clave}",
        )

    st.markdown("#### Indicadores de motores filtrados")
    _kpis_motores(resultado.registros)


def _graficos_motores(
    resultado: VistaReconstruida,
    indice: int | None,
    nombre: str,
    mostrar: bool,
    clave: str,
) -> dict[str, object] | None:
    """Devuelve el gráfico principal realmente visible para exportación HTML."""
    import streamlit as st

    registros = resultado.registros

    if indice == 0:
        grafico = corrientes_motores(registros, mostrar_valores=mostrar)
        _mostrar_echarts(
            grafico,
            nombre,
            f"vista_m_corr_{clave}",
            540,
            exportar=False,
        )
        return grafico

    if indice == 1:
        principal = mapa_revision_motores(
            registros,
            "relacion",
            mostrar_valores=mostrar,
        )
        _mostrar_echarts(
            principal,
            nombre,
            f"vista_m_map_rel_{clave}",
            520,
            exportar=False,
        )

        horas = mapa_revision_motores(
            registros,
            "horas",
            mostrar_valores=mostrar,
        )
        if horas is not None:
            st.caption("Horas: mapa independiente, con escala distinta al porcentaje.")
            _mostrar_echarts(
                horas,
                "Horas por motor",
                f"vista_m_map_h_{clave}",
                520,
                exportar=False,
            )
        return principal

    if indice in (2, 3):
        campo = "potencia_nominal_hp" if indice == 2 else "horas_operacion_mes"
        grafico = barras_motores(
            registros,
            campo,
            mostrar_valores=mostrar,
        )
        _mostrar_echarts(
            grafico,
            nombre,
            f"vista_m_barras_{clave}",
            530,
            exportar=False,
        )
        return grafico

    st.warning("Esta vista usa un nombre anterior diferente al de Motores.")
    _mostrar_echarts(
        resultado.grafico,
        nombre,
        f"vista_m_legacy_{clave}",
        520,
        exportar=False,
    )
    return resultado.grafico


def _grupo_mediciones(
    grafica: str,
    activos: list[str],
) -> str:
    """Identifica el grupo original de Mediciones sin inferir magnitudes."""
    for nombre in GRUPOS:
        if _normalizar(nombre) == _normalizar(grafica):
            return nombre
    for nombre, campos in GRUPOS.items():
        if activos and set(activos).issubset(set(campos)):
            return nombre
    raise ValueError("La vista no corresponde a un grupo de mediciones del panel actual.")


def _vista_mediciones(
    resultado: VistaReconstruida,
    configuracion: dict[str, object],
    clave: str,
) -> tuple[str, list[str], str]:
    """Reproduce curvas, KPI, perfil horario y diagnóstico del panel original."""
    import streamlit as st

    activos = list(configuracion["series"])
    grupo = _grupo_mediciones(str(configuracion["grafica"]), activos)
    referencia = str(configuracion["referencia"])
    marcas = tuple(configuracion.get("marcas", ()))
    izquierda, derecha = st.columns([3, 1], gap="large")

    with derecha:
        st.markdown("#### Controles")
        st.write(grupo)
        st.caption("Series: " + ", ".join(_etiqueta(c) for c in activos))
        st.caption("Serie de referencia: " + _etiqueta(referencia))
        st.caption("Referencias: " + (", ".join(marcas) if marcas else "Ninguna"))
        st.caption("Leyenda, zoom, restauración y descarga PNG.")
        espacio_html = st.empty()

    with izquierda:
        grafico = grafico_temporal(
            resultado.registros,
            activos,
            grupo,
            marcas,
            referencia,
        )
        _mostrar_echarts(
            grafico,
            f"Curvas de {grupo}",
            f"vista_med_curva_{clave}",
            510,
            exportar=False,
        )
        st.caption("No se completan muestras ausentes. Referencias del período guardado.")

    with espacio_html.container():
        mostrar_exportar_html(
            grafico,
            f"Curvas de {grupo}",
            f"vista_med_curva_{clave}",
        )

    st.subheader("Indicadores del período seleccionado")
    for campo in activos:
        _mostrar_kpi(resultado.registros, campo)

    variable = st.selectbox(
        "Variable para análisis horario",
        activos,
        format_func=_etiqueta,
        key=f"vista_variable_horaria_{clave}",
    )
    valores = st.checkbox(
        "Visualización de datos numéricos",
        value=False,
        key=f"vista_valores_med_{clave}",
    )

    st.markdown("#### Gráficas adicionales")
    st.subheader("Exploración por horarios y diagnóstico")
    st.caption(_texto_diagnostico(variable))
    a, b = st.columns(2, gap="large")

    with a:
        st.markdown("#### Comportamiento horario")
        grafico_h = grafico_barras_horarias(
            resultado.registros,
            variable,
            mostrar_valores=valores,
        )
        _mostrar_echarts(
            grafico_h,
            f"Comportamiento horario de {_etiqueta(variable)}",
            f"vista_med_h_{clave}",
            420,
        )

    with b:
        st.markdown("#### Diagnóstico de ingeniería")
        grafico_d = grafico_diagnostico(
            resultado.registros,
            variable,
            mostrar_valores=valores,
        )
        _mostrar_echarts(
            grafico_d,
            f"Diagnóstico de {_etiqueta(variable)}",
            f"vista_med_d_{clave}",
            420,
        )

    return grupo, activos, variable


def _mostrar_tabla(
    registros: list[dict[str, object]],
    clave: str,
) -> None:
    """Mismos datos filtrados, sin compartir claves entre pestañas."""
    import pandas as pd
    import streamlit as st

    st.markdown("#### Datos del filtro aplicado")
    tabla = pd.DataFrame(registros)
    st.dataframe(
        tabla,
        hide_index=True,
        width="stretch",
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
        "Descargar tabla CSV",
        data=exportable.to_csv(index=False).encode("utf-8-sig"),
        file_name="wattwise_vista_reproducida.csv",
        mime="text/csv",
        key=f"vista_csv_{clave}",
    )


def _contexto_guardado(
    tipo: str,
    configuracion: dict[str, object],
) -> dict[str, str]:
    filtros = configuracion.get("filtros", {})
    if tipo == "inventario":
        claves = ("frontera", "area", "tipo_carga", "equipo")
    else:
        claves = ("area", "numero_fases", "equipo")

    contexto = {campo: str(filtros.get(campo, "Todos")) for campo in claves}
    if tipo == "motores":
        contexto["fases"] = str(filtros.get("fases", contexto.pop("numero_fases")))
    return contexto


def _clave_texto(*valores: object) -> str:
    contenido = json.dumps(
        valores,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]


def _observaciones_vista(
    ruta: Path,
    proyecto_id: int,
    tipo: str,
    grafica: str,
    contexto: dict[str, str],
    clave: str,
) -> None:
    """Consulta las mismas notas por contexto, con claves UI independientes."""
    import streamlit as st

    st.markdown("#### Observaciones")
    entrada = f"vista_nota_{clave}_{_clave_texto(tipo, grafica, contexto)}"
    texto = st.text_area(
        "Observación",
        max_chars=2000,
        key=entrada,
    )
    incluir_pdf = st.checkbox(
        "Incluir esta observación en el informe PDF",
        value=True,
        key=f"{entrada}_pdf_nueva",
    )

    if st.button(
        "Guardar observación",
        key=f"{entrada}_guardar",
    ):
        if not texto.strip():
            st.warning("Escribe una observación antes de guardarla.")
        else:
            guardar_observacion(
                ruta,
                proyecto_id,
                tipo,
                grafica,
                contexto,
                texto.strip(),
                mostrar_en_informe=incluir_pdf,
            )
            st.success("Observación guardada.")

    notas = sorted(
        listar_observaciones(
            ruta,
            proyecto_id,
            tipo,
            grafica,
            contexto,
        ),
        key=lambda nota: nota.id,
    )

    if not notas:
        return

    with st.expander(f"Notas guardadas ({len(notas)})"):
        for posicion, nota in enumerate(notas, start=1):
            st.markdown(f"**Nota {posicion}**")
            st.write(nota.texto)

            visible = st.checkbox(
                "Incluir en PDF",
                value=nota.mostrar_en_informe,
                key=f"{entrada}_pdf_{nota.id}",
            )

            if visible != nota.mostrar_en_informe and actualizar_visibilidad_observacion(
                ruta,
                proyecto_id,
                nota.id,
                visible,
            ):
                st.success("Preferencia para informes guardada.")
                st.rerun()

            confirmar = st.checkbox(
                "Confirmar eliminación",
                key=f"{entrada}_confirmar_{nota.id}",
            )
            if st.button(
                "Eliminar nota",
                disabled=not confirmar,
                key=f"{entrada}_eliminar_{nota.id}",
            ):
                if eliminar_observacion(
                    ruta,
                    proyecto_id,
                    nota.id,
                ):
                    st.rerun()
                st.warning("La nota ya no existe.")


def _notas_vista_guardada(
    ruta: Path,
    proyecto_id: int,
    tipo: str,
    resultado: VistaReconstruida,
    configuracion: dict[str, object],
    clave: str,
    mediciones: tuple[str, list[str], str] | None,
) -> None:
    """Conserva el contexto original de cada pestaña al recuperar notas."""
    import streamlit as st

    if tipo == "mediciones":
        if mediciones is None or not resultado.registros:
            return

        grupo, activos, variable = mediciones
        opciones = _graficas_disponibles(
            resultado.registros,
            grupo,
            variable,
        )
        grafica = st.selectbox(
            "Gráfica para observaciones",
            list(opciones),
            key=f"vista_med_nota_grafica_{clave}",
        )
        contexto = _contexto_grafica(
            resultado.registros,
            grupo,
            opciones[grafica],
            activos,
            variable,
        )
    else:
        grafica = _nombre_original(
            tipo,
            str(configuracion["grafica"]),
        )
        contexto = _contexto_guardado(
            tipo,
            configuracion,
        )

    _observaciones_vista(
        ruta,
        proyecto_id,
        tipo,
        grafica,
        contexto,
        clave,
    )


def _mostrar_resultado(
    resultado: VistaReconstruida,
    tipo: str,
    configuracion: dict[str, object],
    clave: str,
    ruta: Path,
    proyecto_id: int,
    con_notas: bool,
) -> None:
    """Comparte los mismos renderizadores de Inventario, Motores y Mediciones."""
    import streamlit as st

    mediciones = None
    if tipo == "inventario":
        _vista_inventario(resultado, configuracion, clave)
    elif tipo == "motores":
        _vista_motores(resultado, configuracion, clave)
    else:
        mediciones = _vista_mediciones(
            resultado,
            configuracion,
            clave,
        )

    st.caption(f"Registros del filtro guardado: {len(resultado.registros):,}.")

    if con_notas:
        _notas_vista_guardada(
            ruta,
            proyecto_id,
            tipo,
            resultado,
            configuracion,
            clave,
            mediciones,
        )

    _mostrar_tabla(resultado.registros, clave)


def _crear_vista_calidad(
    ruta: Path,
    proyecto_id: int,
) -> None:
    """Permite preparar una vista de Calidad sin entrar en esa pestaña."""
    import streamlit as st

    archivos = [
        archivo
        for archivo in listar_archivos(ruta, proyecto_id)
        if archivo.nombre.lower().endswith(".xlsx")
    ]
    if not archivos:
        st.info("Guarda primero un archivo Excel original para revisar su calidad.")
        return

    opciones = {f"{item.nombre} · #{item.id}": item for item in archivos}
    elegido = st.selectbox(
        "Archivo para auditoría de calidad",
        list(opciones),
        key=f"ww_vista_calidad_origen_{proyecto_id}",
    )
    archivo = opciones[elegido]

    _metadatos, contenido = recuperar_archivo(
        ruta,
        proyecto_id,
        archivo.id,
    )
    informe = auditar_excel(
        archivo.tipo,
        archivo.nombre,
        contenido,
    )

    from wattwise.interfaz.panel_calidad_integral import _mostrar_informe

    _mostrar_informe(
        informe,
        archivo.id,
        prefijo=f"ww_nueva_calidad_{proyecto_id}",
    )
    mostrar_notas_vista_calidad(
        ruta,
        proyecto_id,
        archivo.id,
        f"creacion_{proyecto_id}_{archivo.id}",
    )
    mostrar_guardar_calidad_en_vistas(
        ruta,
        proyecto_id,
        archivo.id,
        informe,
        prefijo="creacion",
    )


def _crear_vista(
    ruta: Path,
    proyecto_id: int,
) -> None:
    """Previsualiza gráficos y KPI antes de guardar su configuración."""
    import streamlit as st

    tipo = st.selectbox(
        "Módulo",
        [*GRAFICAS, "calidad"],
        key=f"vista_tipo_{proyecto_id}",
        format_func=lambda valor: "Calidad de datos" if valor == "calidad" else valor.capitalize(),
    )
    if tipo == "calidad":
        _crear_vista_calidad(ruta, proyecto_id)
        return

    archivo = _elegir_archivo(
        ruta,
        proyecto_id,
        tipo,
    )
    if archivo is None:
        return

    registros = _cargar_registros(
        ruta,
        proyecto_id,
        archivo.id,
        tipo,
    )
    prefijo = f"vista_nueva_{proyecto_id}_{archivo.id}_{tipo}"
    filtros = _filtros_nuevos(
        registros,
        tipo,
        prefijo,
    )
    filtrados = _registros_filtrados(
        registros,
        filtros,
    )

    if not filtrados:
        st.info("Los filtros seleccionados no contienen registros.")
        return

    st.markdown("#### Controles de la vista")
    grafica = _elegir_grafica(tipo, prefijo)

    configuracion: dict[str, object] = {
        "version": 1,
        "grafica": grafica,
        "filtros": filtros,
        "opciones": _opciones_nuevas(
            tipo,
            grafica,
            filtrados,
            prefijo,
        ),
    }
    if tipo == "mediciones":
        configuracion.update(_config_mediciones(filtrados, grafica, prefijo))

    resultado = reconstruir_vista(
        tipo,
        registros,
        configuracion,
    )
    _mostrar_resultado(
        resultado,
        tipo,
        configuracion,
        prefijo,
        ruta,
        proyecto_id,
        True,
    )

    titulo = st.text_input(
        "Nombre de esta vista",
        value=f"{_nombre_original(tipo, grafica)} · {archivo.nombre}"[:120],
        max_chars=120,
        key=f"{prefijo}_{_clave_texto(grafica)}_titulo",
    )

    if st.button(
        "Guardar vista reproducible",
        key=f"{prefijo}_guardar",
    ):
        guardada_id = guardar_vista(
            ruta,
            proyecto_id,
            archivo.id,
            tipo,
            titulo,
            configuracion,
        )
        st.success(f"Vista guardada correctamente (ID interno {guardada_id}).")


def _abrir_vista(
    ruta: Path,
    proyecto_id: int,
    vista: VistaGuardada,
) -> None:
    """Comprueba origen y hash antes de reconstruir una vista."""
    import streamlit as st

    metadatos, _contenido = recuperar_archivo(
        ruta,
        proyecto_id,
        vista.archivo_id,
    )
    if metadatos.tipo != vista.tipo or metadatos.sha256 != vista.sha256_archivo:
        raise ValueError("El archivo original ya no coincide con la vista guardada.")

    registros = _cargar_registros(
        ruta,
        proyecto_id,
        vista.archivo_id,
        vista.tipo,
    )
    resultado = reconstruir_vista(
        vista.tipo,
        registros,
        vista.configuracion,
    )
    st.markdown(f"#### {_nombre_original(vista.tipo, str(vista.configuracion['grafica']))}")
    _mostrar_resultado(
        resultado,
        vista.tipo,
        vista.configuracion,
        f"guardada_{proyecto_id}_{vista.id}",
        ruta,
        proyecto_id,
        True,
    )


def _eliminar_varias(
    ruta: Path,
    proyecto_id: int,
    vistas: list[VistaGuardada],
) -> None:
    """Selecciona muchas vistas y confirma un borrado atómico."""
    import streamlit as st

    st.markdown("#### Eliminar vistas guardadas")
    etiquetas = {f"{vista.titulo} ({vista.tipo}) · vista {vista.id}": vista.id for vista in vistas}
    clave = f"vista_eliminar_seleccion_{proyecto_id}"
    reiniciar = f"vista_eliminar_reiniciar_{proyecto_id}"

    if st.session_state.pop(reiniciar, False):
        st.session_state[clave] = []

    anteriores = st.session_state.get(clave, [])
    if anteriores:
        st.session_state[clave] = [etiqueta for etiqueta in anteriores if etiqueta in etiquetas]

    a, b = st.columns(2)
    if a.button(
        "Seleccionar todas",
        key=f"vista_todas_{proyecto_id}",
    ):
        st.session_state[clave] = list(etiquetas)

    if b.button(
        "Limpiar selección",
        key=f"vista_ninguna_{proyecto_id}",
    ):
        st.session_state[clave] = []

    seleccion = st.multiselect(
        "Vistas que deseas eliminar",
        list(etiquetas),
        key=clave,
        placeholder="Elige una o varias vistas",
    )
    if not seleccion:
        return

    st.warning(
        f"Se eliminarán {len(seleccion)} vista(s) seleccionadas del proyecto activo. "
        "No se borrarán los archivos originales ni los análisis guardados."
    )

    firma = _clave_texto(sorted(etiquetas[item] for item in seleccion))
    confirmar = st.checkbox(
        f"Confirmo la eliminación de {len(seleccion)} vista(s)",
        key=f"vista_eliminar_confirmar_{proyecto_id}_{firma}",
    )

    if st.button(
        "Eliminar seleccionadas",
        disabled=not confirmar,
        key=f"vista_eliminar_ejecutar_{proyecto_id}",
    ):
        ids = [etiquetas[etiqueta] for etiqueta in seleccion]
        borradas = eliminar_vistas(ruta, proyecto_id, ids)
        st.session_state[reiniciar] = True
        st.success(f"{borradas} vista(s) eliminada(s).")
        st.rerun()


def _mostrar_guardadas(
    ruta: Path,
    proyecto_id: int,
) -> None:
    """Permite abrir vistas existentes y administrar varias a la vez."""
    import streamlit as st

    vistas = listar_vistas(ruta, proyecto_id)

    if vistas:
        _eliminar_varias(
            ruta,
            proyecto_id,
            vistas,
        )
        st.divider()
        st.markdown("#### Abrir una vista guardada")

        opciones = {f"{vista.titulo} ({vista.tipo}) · vista {vista.id}": vista for vista in vistas}
        etiqueta = st.selectbox(
            "Vista guardada",
            list(opciones),
            key=f"vista_guardada_{proyecto_id}",
        )
        vista = opciones[etiqueta]

        try:
            _abrir_vista(
                ruta,
                proyecto_id,
                vista,
            )
        except (ValueError, KeyError, OSError, sqlite3.Error) as error:
            st.warning(f"No fue posible reconstruir esta vista: {error}")
    else:
        st.info("No hay vistas eléctricas guardadas en este proyecto.")

    mostrar_vistas_calidad(ruta, proyecto_id)


def mostrar_vistas(ruta: Path) -> None:
    """Crea y recupera vistas del proyecto activo, sin selector redundante."""
    import streamlit as st

    st.header("Vistas reproducibles")
    st.caption(
        "Las vistas conservan el archivo original, sus filtros y su configuración. "
        "Los gráficos e indicadores se vuelven a calcular desde el archivo verificado."
    )
    proyecto_id = st.session_state.get("wattwise_proyecto_id")

    if not isinstance(proyecto_id, int) or isinstance(proyecto_id, bool) or proyecto_id <= 0:
        st.info("Selecciona un proyecto activo en la barra lateral.")
        return

    try:
        if proyecto_id not in {proyecto.id for proyecto in listar_proyectos(ruta)}:
            st.error("El proyecto activo ya no existe.")
            return

        modo = st.radio(
            "Acción",
            ("Abrir y eliminar vistas guardadas", "Crear vista"),
            horizontal=True,
            key=f"vistas_modo_{proyecto_id}",
        )

        if modo == "Crear vista":
            _crear_vista(ruta, proyecto_id)
        else:
            _mostrar_guardadas(ruta, proyecto_id)

    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        sqlite3.Error,
    ) as error:
        st.error(f"No fue posible preparar las vistas: {error}")
