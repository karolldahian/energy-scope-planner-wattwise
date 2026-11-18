"""Exportación HTML y guardado de vistas sin sustituir ECharts nativo."""

from __future__ import annotations

import hashlib
import html
import json
import sqlite3
from pathlib import Path

from wattwise.dominio.vistas import validar_vista
from wattwise.infraestructura.archivos_proyecto import listar_archivos
from wattwise.infraestructura.vistas_sqlite import guardar_vista
from wattwise.interfaz.guardado_inventario_capturado import originales_coincidentes

_MOTOR_ECHARTS = "https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"


def nombre_exportacion(titulo: str) -> str:
    """Genera un nombre de descarga simple, sin rutas ni separadores."""
    nombre = "".join(
        caracter if caracter.isalnum() or caracter in ("-", "_") else "_"
        for caracter in titulo.strip()
    )
    return nombre.strip("._")[:80] or "grafica_wattwise"


def html_grafica(grafico: dict[str, object], titulo: str) -> bytes:
    """Exporta las opciones visibles sin alterar la instancia ECharts en pantalla.

    El archivo resultante requiere Internet para cargar la biblioteca ECharts.
    No captura ajustes hechos directamente dentro del navegador (zoom/leyenda).
    """
    if not isinstance(grafico, dict) or not isinstance(grafico.get("series"), list):
        raise ValueError("La gráfica ECharts no contiene series válidas.")
    if not isinstance(titulo, str) or not titulo.strip():
        raise ValueError("La gráfica debe tener un nombre.")

    try:
        opciones = json.dumps(grafico, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("La configuración ECharts no se puede exportar.") from error

    # El JSON jamás debe poder cerrar la etiqueta <script> del documento.
    opciones = (
        opciones.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    titulo_html = html.escape(titulo, quote=True)
    documento = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{titulo_html} · WattWise</title>
  <style>
    html, body {{ margin: 0; padding: 0; height: 100%; background: #fff; }}
    #grafica {{ height: 100vh; min-height: 570px; width: 100%; }}
    #aviso {{ font: 14px sans-serif; margin: 12px; color: #a00; }}
  </style>
</head>
<body>
  <div id="grafica" role="img" aria-label="Gráfica de WattWise"></div>
  <p id="aviso" role="status"></p>
  <script src="{_MOTOR_ECHARTS}"></script>
  <script>
    "use strict";
    const opciones = {opciones};
    if (typeof echarts === "undefined") {{
      document.getElementById("aviso").textContent =
        "Se necesita conexión a Internet para cargar ECharts.";
    }} else {{
      const grafica = echarts.init(document.getElementById("grafica"));
      grafica.setOption(opciones, {{ notMerge: true }});
      window.addEventListener("resize", () => grafica.resize());
    }}
  </script>
</body>
</html>
"""
    return documento.encode("utf-8")


def mostrar_exportacion_inventario(grafico: dict[str, object], vista: str) -> None:
    """Añade exportación sin tocar el tamaño o componente de la gráfica nativa."""
    import streamlit as st

    with st.popover("⋮ Exportar"):
        st.caption(
            "PNG: utiliza el icono de descarga de la esquina superior derecha "
            "de la gráfica. Exporta la vista que tienes en pantalla."
        )
        st.download_button(
            "Descargar HTML",
            data=html_grafica(grafico, vista),
            file_name=f"{nombre_exportacion(vista)}.html",
            mime="text/html",
            key="ww_inv_exportar_html",
            width="stretch",
        )
        st.caption(
            "El HTML conserva los filtros y opciones actuales de la gráfica, "
            "no el zoom ni las series ocultas manualmente. Requiere Internet al abrirlo."
        )


def guardar_configuracion_inventario(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int,
    resultado: object,
    vista: str,
    filtros: dict[str, str],
    opciones: dict[str, bool],
    titulo: str,
) -> int:
    """Guarda una vista reproducible únicamente con su Excel íntegro original."""
    if type(proyecto_id) is not int or proyecto_id <= 0:
        raise ValueError("Selecciona un proyecto válido.")
    if type(archivo_id) is not int or archivo_id <= 0:
        raise ValueError("Selecciona el Excel original del proyecto.")
    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 120:
        raise ValueError("Escribe un nombre de vista entre 1 y 120 caracteres.")

    configuracion = validar_vista(
        "inventario",
        {"version": 1, "grafica": vista, "filtros": filtros, "opciones": opciones},
    )
    compatibles = originales_coincidentes(ruta, proyecto_id, resultado)
    if archivo_id not in {archivo.id for archivo in compatibles}:
        raise ValueError("El Excel seleccionado no coincide con el inventario actual.")
    return guardar_vista(ruta, proyecto_id, archivo_id, "inventario", titulo.strip(), configuracion)


def _clave_formulario(
    proyecto_id: int, resultado: object, vista: str, filtros: dict[str, str]
) -> str:
    """Aísla formularios de proyectos, inventarios y filtros diferentes."""
    datos = (proyecto_id, repr(resultado), vista, filtros)
    texto = json.dumps(datos, ensure_ascii=False, sort_keys=True)
    huella = hashlib.sha256(texto.encode("utf-8")).hexdigest()[:14]
    return f"ww_inv_vista_{huella}"


def mostrar_guardado_inventario(
    ruta: Path,
    resultado: object,
    vista: str,
    filtros: dict[str, str],
    opciones: dict[str, bool],
) -> None:
    """Muestra un formulario lateral; ECharts nunca se renderiza aquí."""
    import streamlit as st

    with st.popover("📌 Guardar como vista"):
        proyecto_id = st.session_state.get("wattwise_proyecto_id")
        if type(proyecto_id) is not int or proyecto_id <= 0:
            st.info("Selecciona primero un proyecto activo.")
            return

        try:
            archivos = listar_archivos(ruta, proyecto_id, "inventario")
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(f"No fue posible consultar los Excel del proyecto: {error}")
            return

        if not archivos:
            st.info("Guarda primero el Excel original de este inventario en el proyecto.")
            return

        clave = _clave_formulario(proyecto_id, resultado, vista, filtros)
        etiquetas = {
            archivo.id: f"{archivo.nombre} · archivo #{archivo.id}" for archivo in archivos
        }
        with st.form(f"{clave}_formulario"):
            archivo_id = st.selectbox(
                "Excel original del proyecto",
                list(etiquetas),
                format_func=lambda identificador: etiquetas[identificador],
            )
            titulo = st.text_input("Nombre de la vista", value=vista, max_chars=120)
            confirmar = st.form_submit_button("Confirmar guardado")

        if not confirmar:
            st.caption(
                "Guarda el archivo original, filtros y controles de Pareto. "
                "Las observaciones del proyecto se consultan al reabrirla. "
                "El zoom manual y el PNG no se almacenan."
            )
            return

        try:
            identificador = guardar_configuracion_inventario(
                ruta, proyecto_id, archivo_id, resultado, vista, filtros, opciones, titulo
            )
        except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
            st.error(f"No se pudo guardar la vista: {error}")
        else:
            st.success(f"Vista #{identificador} guardada. Ábrela en Vistas reproducibles.")
