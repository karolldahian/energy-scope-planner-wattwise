"""Vista sencilla de calidad de datos y guardado por proyecto."""

from __future__ import annotations

import sqlite3
from html import escape
from pathlib import Path

from wattwise.dominio.calidad_integral import (
    CalidadHoja,
    HallazgoCalidad,
    InformeCalidad,
    auditar_excel,
)
from wattwise.infraestructura.archivos_proyecto import (
    listar_archivos,
    recuperar_archivo,
)
from wattwise.infraestructura.notas_calidad_sqlite import (
    eliminar_nota_calidad,
    guardar_nota_calidad,
    listar_notas_calidad,
)
from wattwise.interfaz.vistas_calidad import mostrar_guardar_calidad_en_vistas

TIPOS = {
    "inventario": "Inventario",
    "mediciones": "Mediciones",
    "motores": "Motores",
}


def _porcentaje(cantidad: int, total: int) -> str:
    return f"{100 * cantidad / total:.1f}%" if total else "0.0%"


def _conteo(cantidad: int, total: int) -> str:
    return f"{cantidad:,} ({_porcentaje(cantidad, total)})"


def _barra_proporcion(columna: object, total: int) -> str:
    """Los ceros válidos pertenecen a válidos; no se duplican en la barra."""
    segmentos = (
        (columna.validos - columna.ceros_validos, "#16a34a"),
        (columna.ceros_validos, "#94a3b8"),
        (columna.faltantes, "#f59e0b"),
        (columna.invalidos, "#dc2626"),
    )
    barras = "".join(
        f'<span style="display:block;height:100%;width:{100 * n / total:.4f}%;'
        f'background:{color}"></span>'
        for n, color in segmentos
        if n > 0 and total > 0
    )
    return (
        '<div style="display:flex;min-width:110px;width:100%;height:12px;'
        'overflow:hidden;border-radius:5px;background:#e5e7eb">'
        f"{barras}</div>"
    )


def _tabla_columnas(hoja: CalidadHoja) -> None:
    """Muestra todas las columnas con sus cantidades y proporciones."""
    import streamlit as st

    cabeceras = (
        "Columna",
        "Válidos",
        "Vacíos",
        "Ceros",
        "Inválidos",
        "Proporción",
    )
    encabezado = "".join(
        '<th style="text-align:left;padding:9px;border-bottom:1px solid #d1d5db;'
        f'background:#f8fafc">{escape(nombre)}</th>'
        for nombre in cabeceras
    )

    filas = []
    for columna in hoja.columnas:
        valores = (
            escape(columna.nombre),
            _conteo(columna.validos, hoja.registros),
            _conteo(columna.faltantes, hoja.registros),
            _conteo(columna.ceros, hoja.registros),
            _conteo(columna.invalidos, hoja.registros),
            _barra_proporcion(columna, hoja.registros),
        )
        celdas = "".join(
            '<td style="padding:8px;border-bottom:1px solid #e5e7eb;'
            f'white-space:nowrap">{valor}</td>'
            for valor in valores
        )
        filas.append(f"<tr>{celdas}</tr>")

    html = (
        '<div style="max-height:490px;overflow:auto;border:1px solid #e5e7eb;'
        'border-radius:10px"><table style="width:100%;border-collapse:collapse;'
        'font-size:13px"><thead><tr>'
        f"{encabezado}</tr></thead><tbody>{''.join(filas)}</tbody></table></div>"
    )
    st.markdown(html, unsafe_allow_html=True)
    st.caption(
        "Barra: 🟩 válidos sin cero · gris: ceros válidos · amarillo: vacíos · "
        "rojo: inválidos. Los ceros válidos están incluidos en el conteo "
        "«Válidos», pero no se suman dos veces en la barra."
    )


def _detalle_hallazgos(
    hallazgos: tuple[HallazgoCalidad, ...],
) -> None:
    """Localiza todos los registros del hallazgo seleccionado."""
    import pandas as pd
    import streamlit as st

    registros = []
    for numero, item in enumerate(hallazgos, start=1):
        registros.append(
            {
                "N.º": numero,
                "Hoja": item.hoja,
                "Fila(s) Excel": (
                    ", ".join(str(f) for f in item.filas) if item.filas else "Columna completa"
                ),
                "Columna": item.columna,
                "Punto": item.punto,
                "Valor": item.valor,
                "Desde": item.fecha_inicio,
                "Hasta": item.fecha_fin,
                "Duración (min)": item.duracion_min,
                "Muestras implicadas": item.cantidad_afectada,
                "Motivo": item.motivo,
            }
        )

    tabla = pd.DataFrame(registros)
    vacias = [nombre for nombre in tabla if tabla[nombre].replace("", pd.NA).isna().all()]
    tabla = tabla.drop(columns=vacias)
    st.dataframe(tabla, hide_index=True, width="stretch")


def _desglose(
    titulo: str,
    hallazgos: tuple[HallazgoCalidad, ...],
) -> None:
    import streamlit as st

    if hallazgos:
        with st.expander(f"Ver desglose: {titulo} ({len(hallazgos)})"):
            _detalle_hallazgos(hallazgos)


def _columna_especifica(
    hoja: CalidadHoja,
    tipo: str,
    clave: str,
) -> None:
    """Conserva cuatro KPI y los desgloses de la columna elegida."""
    import streamlit as st

    with st.expander("Revisar una columna específica"):
        nombres = [columna.nombre for columna in hoja.columnas]
        if not nombres:
            st.info("No hay columnas para revisar.")
            return

        nombre = st.selectbox(
            "Columna",
            nombres,
            key=f"calidad_columna_{clave}",
        )
        columna = next(c for c in hoja.columnas if c.nombre == nombre)
        primera = st.columns(2)
        segunda = st.columns(2)

        primera[0].metric(
            "Ceros",
            _conteo(columna.ceros, hoja.registros),
        )
        primera[1].metric(
            "Negativos",
            _conteo(columna.negativos, hoja.registros),
        )
        segunda[0].metric(
            "Rachas de ceros",
            columna.rachas_ceros if tipo == "mediciones" else "No aplica",
        )
        segunda[1].metric(
            "Rachas constantes",
            columna.rachas_constantes if tipo == "mediciones" else "No aplica",
        )

        st.caption(
            f"Nulos (celda sin dato): {_conteo(columna.nulos, hoja.registros)} · "
            f"Espacios o invisibles: {_conteo(columna.blancos, hoja.registros)} · "
            f"Marcadores de texto: {_conteo(columna.marcadores, hoja.registros)}"
        )

        for titulo, hallazgos in (
            ("ceros", columna.ubicaciones_ceros),
            ("rachas de ceros", columna.ubicaciones_rachas_ceros),
            ("rachas constantes", columna.ubicaciones_rachas_constantes),
            ("valores negativos", columna.ubicaciones_negativos),
            ("vacíos", columna.ubicaciones_vacias),
            ("espacios o invisibles", columna.ubicaciones_blancos),
            ("marcadores de texto", columna.ubicaciones_marcadores),
            ("inválidos", columna.ubicaciones_invalidas),
        ):
            _desglose(titulo, hallazgos)

        st.caption(
            "Las rachas muestran las filas y las fechas extremas; pueden existir "
            "otras filas de otros puntos entre ellas. Son señales para revisión, "
            "no diagnósticos automáticos de fallas eléctricas."
        )


def _mostrar_informe(
    informe: InformeCalidad,
    archivo_id: int,
    *,
    prefijo: str = "calidad",
) -> None:
    """Muestra únicamente tabla por columna y revisión individual."""
    import streamlit as st

    if len(informe.hojas) > 1:
        opciones = {hoja.nombre: hoja for hoja in informe.hojas}
        elegido = st.selectbox(
            "Hoja",
            list(opciones),
            key=f"{prefijo}_hoja_{archivo_id}",
        )
        hoja = opciones[elegido]
    else:
        hoja = informe.hojas[0]

    _tabla_columnas(hoja)
    _columna_especifica(
        hoja,
        informe.tipo,
        f"{prefijo}_{archivo_id}_{hoja.nombre}",
    )


def _observaciones(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int,
) -> None:
    """Guarda y elimina notas con numeración visual consecutiva."""
    import streamlit as st

    st.markdown("#### Observaciones")
    clave = f"calidad_texto_{proyecto_id}_{archivo_id}"
    texto = st.text_area(
        "Observación",
        max_chars=2000,
        key=clave,
    )

    if st.button(
        "Guardar observación",
        key=f"calidad_guardar_nota_{proyecto_id}_{archivo_id}",
    ):
        if not texto.strip():
            st.warning("Escribe una observación antes de guardarla.")
        else:
            try:
                guardar_nota_calidad(
                    ruta,
                    proyecto_id,
                    archivo_id,
                    texto.strip(),
                )
                st.success("Observación guardada.")
            except (ValueError, sqlite3.Error, OSError) as error:
                st.error(f"No se pudo guardar la observación: {error}")

    try:
        notas = sorted(
            listar_notas_calidad(ruta, proyecto_id, archivo_id),
            key=lambda nota: nota.id,
        )
    except (ValueError, sqlite3.Error, OSError) as error:
        st.error(f"No fue posible consultar las notas: {error}")
        return

    if notas:
        st.markdown("**Notas guardadas**")
        for posicion, nota in enumerate(notas, start=1):
            with st.expander(f"Nota {posicion}"):
                st.write(nota.contenido)

                confirmar = st.checkbox(
                    "Confirmar eliminación",
                    key=f"calidad_confirmar_{proyecto_id}_{archivo_id}_{nota.id}",
                )
                if st.button(
                    "Eliminar nota",
                    disabled=not confirmar,
                    key=f"calidad_eliminar_{proyecto_id}_{archivo_id}_{nota.id}",
                ):
                    try:
                        if eliminar_nota_calidad(
                            ruta,
                            proyecto_id,
                            nota.id,
                        ):
                            st.rerun()
                        else:
                            st.warning("La nota ya no existe.")
                    except (ValueError, sqlite3.Error, OSError) as error:
                        st.error(f"No se pudo eliminar la nota: {error}")


def _auditar_archivos(
    ruta: Path,
    proyecto_id: int,
    archivos: list[object],
) -> tuple[list[tuple[int, InformeCalidad]], list[dict[str, str]]]:
    """Audita originales y presenta solamente el seleccionado."""
    import streamlit as st

    auditados: list[tuple[int, InformeCalidad]] = []
    omitidos: list[dict[str, str]] = []
    resultados: dict[int, InformeCalidad] = {}
    errores: dict[int, str] = {}

    for archivo in archivos:
        if not archivo.nombre.lower().endswith(".xlsx"):
            razon = "La auditoría por columnas requiere un archivo XLSX."
            omitidos.append({"archivo_id": str(archivo.id), "motivo": razon})
            errores[archivo.id] = razon
            continue

        try:
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
        except (ValueError, OSError, sqlite3.Error) as error:
            razon = str(error)
            omitidos.append({"archivo_id": str(archivo.id), "motivo": razon})
            errores[archivo.id] = razon
            continue

        auditados.append((archivo.id, informe))
        resultados[archivo.id] = informe

    opciones = {f"{TIPOS.get(a.tipo, a.tipo)} · {a.nombre} · #{a.id}": a.id for a in archivos}
    elegido = st.selectbox(
        "Archivo original",
        list(opciones),
        key=f"calidad_archivo_{proyecto_id}",
    )
    archivo_id = opciones[elegido]

    if archivo_id in resultados:
        _mostrar_informe(
            resultados[archivo_id],
            archivo_id,
        )
    else:
        st.warning(errores[archivo_id])

    _observaciones(
        ruta,
        proyecto_id,
        archivo_id,
    )

    if archivo_id in resultados:
        mostrar_guardar_calidad_en_vistas(
            ruta,
            proyecto_id,
            archivo_id,
            resultados[archivo_id],
        )

    return auditados, omitidos


def mostrar_calidad_integral(ruta: Path) -> None:
    """Revisa el proyecto activo sin volver a seleccionarlo."""
    import streamlit as st

    st.header("Calidad de datos")
    proyecto_id = st.session_state.get("wattwise_proyecto_id")

    if not isinstance(proyecto_id, int):
        st.info("Selecciona un proyecto activo en la barra lateral.")
        return

    try:
        archivos = listar_archivos(ruta, proyecto_id)

        if not archivos:
            st.info("Guarda un archivo original en este proyecto para revisarlo.")
            return

        _auditar_archivos(
            ruta,
            proyecto_id,
            archivos,
        )
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(f"No fue posible revisar la calidad de datos: {error}")
