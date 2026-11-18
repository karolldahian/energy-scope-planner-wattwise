"""Exportación HTML independiente del renderizador ECharts nativo de WattWise."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from html import escape
from math import isfinite

import numpy as np
import pandas as pd

_CDN_ECHARTS = "https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"


def nombre_html(nombre: str) -> str:
    """Normaliza un nombre editable para descargar un archivo local .html."""
    if not isinstance(nombre, str):
        raise ValueError("El nombre del archivo debe ser texto.")

    normalizado = unicodedata.normalize("NFKC", nombre.strip())
    normalizado = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", normalizado)
    normalizado = normalizado.strip(" ._")

    if normalizado.lower().endswith(".html"):
        normalizado = normalizado[:-5]

    normalizado = normalizado[:100].rstrip(" ._")

    if not normalizado:
        raise ValueError("Escribe un nombre válido para el archivo HTML.")

    return f"{normalizado}.html"


def _normalizar_especial(valor: object, profundidad: int) -> object:
    """Convierte arreglos y objetos de pandas preservando fechas y nulos."""
    if isinstance(valor, pd.DataFrame):
        return json.loads(valor.to_json(orient="records", date_format="iso"))

    if isinstance(valor, pd.Series):
        return json.loads(valor.to_json(orient="values", date_format="iso"))

    if isinstance(valor, np.ndarray):
        return _normalizar_datos(valor.tolist(), profundidad + 1)

    if isinstance(valor, np.generic):
        return _normalizar_datos(valor.item(), profundidad + 1)

    raise ValueError("Tipo especial no admitido.")


def _normalizar_datos(valor: object, profundidad: int = 0) -> object:
    """Convierte tipos admitidos por Streamlit a JSON seguro para ECharts."""
    if profundidad > 20:
        raise ValueError("La gráfica tiene una estructura demasiado profunda.")

    if isinstance(valor, (pd.DataFrame, pd.Series, np.ndarray, np.generic)):
        return _normalizar_especial(valor, profundidad)

    if isinstance(valor, (datetime, date)):
        return valor.isoformat()

    if valor is None or isinstance(valor, (str, bool, int)):
        return valor

    if isinstance(valor, float):
        return valor if isfinite(valor) else None

    if isinstance(valor, (list, tuple)):
        return [_normalizar_datos(item, profundidad + 1) for item in valor]

    if isinstance(valor, dict):
        return _normalizar_diccionario(valor, profundidad)

    raise ValueError("La gráfica contiene datos de tipo no compatible con HTML.")


def _normalizar_diccionario(
    valor: dict[object, object],
    profundidad: int,
) -> object:
    """Exige claves de texto y normaliza las opciones de un diccionario."""
    if not all(isinstance(clave, str) for clave in valor):
        raise ValueError("La gráfica contiene claves que no son texto.")

    return {clave: _normalizar_datos(item, profundidad + 1) for clave, item in valor.items()}


def construir_html_echarts(
    grafico: dict[str, object],
    titulo: str,
) -> bytes:
    """Crea un HTML sin ejecutar contenido del título como HTML o JavaScript."""
    if not isinstance(grafico, dict) or not grafico:
        raise ValueError("La configuración de ECharts está vacía o es inválida.")

    if not isinstance(titulo, str) or not titulo.strip() or len(titulo.strip()) > 120:
        raise ValueError("El título debe contener entre 1 y 120 caracteres.")

    try:
        opciones = json.dumps(
            _normalizar_datos(grafico),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("La gráfica contiene datos que no se pueden exportar a HTML.") from error

    if len(opciones.encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("La gráfica supera el tamaño máximo de exportación HTML.")

    # No insertar cadenas que puedan cerrar una etiqueta <script>.
    opciones = (
        opciones.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    nombre = escape(titulo.strip(), quote=True)

    documento = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{nombre} | WattWise</title>
<style>
  body {{ margin: 0; padding: 20px; font-family: Arial, sans-serif; background: #fff; }}
  h1 {{ font-size: 20px; color: #17324f; }}
  #grafica {{ width: 100%; height: 78vh; min-height: 480px; }}
  .aviso {{ color: #64748b; font-size: 12px; }}
</style>
<script src="{_CDN_ECHARTS}"></script>
</head>
<body>
<h1>{nombre}</h1>
<div id="grafica" role="img" aria-label="Gráfica interactiva de WattWise"></div>
<p class="aviso">Exportación de la configuración seleccionada. Requiere conexión
 a Internet para cargar ECharts. El zoom o las series cambiadas manualmente
 en el navegador original no se transfieren; para conservarlos usa el PNG.</p>
<script>
(function () {{
  const opciones = {opciones};
  const contenedor = document.getElementById('grafica');

  if (!window.echarts) {{
    contenedor.textContent = 'No fue posible cargar ECharts. Comprueba tu conexión.';
    return;
  }}

  const grafica = echarts.init(contenedor);
  grafica.setOption(opciones);
  window.addEventListener('resize', () => grafica.resize());
}})();
</script>
</body>
</html>"""

    return documento.encode("utf-8")


def mostrar_exportar_html(
    grafico: dict[str, object] | None,
    titulo: str,
    clave: str,
) -> None:
    """Muestra exportación y nombre editable sin modificar ECharts."""
    import streamlit as st

    if not grafico:
        return

    with st.popover("Exportar HTML"):
        nombre = st.text_input(
            "Nombre del archivo",
            value=titulo[:100],
            key=f"ww_html_nombre_{clave}",
            max_chars=100,
        )

        try:
            archivo = nombre_html(nombre)
            contenido = construir_html_echarts(grafico, titulo)
        except ValueError as error:
            st.warning(str(error))
            return

        st.download_button(
            "Descargar HTML",
            data=contenido,
            file_name=archivo,
            mime="text/html",
            key=f"ww_html_descargar_{clave}",
        )
