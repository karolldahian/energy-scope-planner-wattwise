"""Puente ECharts capturable para Vistas, sin duplicar controles de exportación."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from wattwise.infraestructura.capturas_vistas_sqlite import (
    MAXIMO_ESTADO_BYTES,
    MAXIMO_PNG_BYTES,
    _estado_json,
    _validar_png,
)

_HTML = """
<div class="ww-captura">
  <div class="ww-grafica" role="img" aria-label="Gráfica interactiva"></div>
  <p class="ww-aviso" role="alert" aria-live="assertive"></p>
  <button class="ww-capturar" type="button" hidden>Capturar estado (prueba)</button>
</div>
"""

_CSS = """
.ww-captura { width: 100%; height: 570px; position: relative; }
.ww-grafica { width: 100%; height: 570px; min-height: 240px; }
.ww-aviso {
  position: absolute; top: 6px; left: 6px; z-index: 9;
  margin: 0; padding: 5px; font: 13px sans-serif;
  color: #9b1c1c; background: #fff; display: none;
}
.ww-capturar {
  position: absolute; right: 12px; bottom: 8px;
  background: #fff; border: 1px solid #999; border-radius: 6px;
  padding: 5px 9px; cursor: pointer;
}
"""

_JS = r"""
const MOTOR_URL = "https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js";
const memoria = (globalThis.__wwEchartsMemoria ??= new Map());
const solicitudes = (globalThis.__wwEchartsSolicitudes ??= new Map());

function cargarMotor() {
  if (globalThis.echarts) return Promise.resolve(globalThis.echarts);
  if (!globalThis.__wwEchartsCarga) {
    globalThis.__wwEchartsCarga = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = MOTOR_URL;
      script.async = true;
      script.onload = () => {
        if (globalThis.echarts) resolve(globalThis.echarts);
        else reject(new Error("ECharts no se inicializó."));
      };
      script.onerror = () => reject(new Error("No se pudo cargar ECharts."));
      document.head.appendChild(script);
    }).catch(error => {
      globalThis.__wwEchartsCarga = null;
      throw error;
    });
  }
  return globalThis.__wwEchartsCarga;
}

function nombreSeguro(valor) {
  const base = String(valor || "grafica").trim()
    .replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_")
    .replace(/\.+$/g, "").replace(/\.(png|html)$/i, "").slice(0, 120);
  return base || "grafica";
}

export default function({ parentElement, data, setTriggerValue }) {
  const raiz = parentElement.querySelector(".ww-captura");
  const contenedor = parentElement.querySelector(".ww-grafica");
  const aviso = parentElement.querySelector(".ww-aviso");
  const boton = parentElement.querySelector(".ww-capturar");
  const altura = Number(data.altura);
  const alto = Number.isFinite(altura) && altura >= 240 && altura <= 1600
    ? altura : 570;
  raiz.style.height = `${alto}px`;
  contenedor.style.height = `${alto}px`;

  const clave = data.clave_grafica;
  const firma = data.firma_opciones;
  const solicitud = data.solicitud_captura;
  const anterior = memoria.get(clave);
  const nombre = nombreSeguro(data.titulo_predeterminado || "Gráfica");
  let destruido = false;
  let grafica = null;
  let observador = null;

  boton.hidden = !data.mostrar_boton_prueba;

  function errorVisible(error) {
    if (destruido) return;
    aviso.textContent = error instanceof Error ? error.message : String(error);
    aviso.style.display = "block";
  }

  function capturar() {
    if (destruido || !grafica || grafica.isDisposed()) return;
    try {
      const opciones = grafica.getOption();
      const imagen = grafica.getDataURL({
        type: "png", pixelRatio: 2, backgroundColor: "#ffffff",
        excludeComponents: ["toolbox"]
      });
      const prefijo = "data:image/png;base64,";
      if (!imagen.startsWith(prefijo)) {
        throw new Error("ECharts no produjo una imagen PNG.");
      }
      if (imagen.length > 28_000_000) {
        throw new Error("La imagen supera el tamaño admitido.");
      }
      setTriggerValue("captura", {
        estado_echarts: opciones,
        imagen_png_base64: imagen.slice(prefijo.length),
        nombre_archivo: nombre,
        solicitud_captura: solicitud
      });
    } catch (error) {
      errorVisible(error);
    }
  }

  boton.onclick = capturar;

  cargarMotor().then(echarts => {
    if (destruido) return;
    grafica = echarts.getInstanceByDom(contenedor) ||
      echarts.init(contenedor, null, { renderer: "canvas" });
    if (anterior && anterior.firma === firma) {
      grafica.setOption(anterior.estado, { notMerge: true });
    } else {
      grafica.setOption(data.opciones, { notMerge: true });
    }
    requestAnimationFrame(() => {
      if (!destruido && !grafica.isDisposed()) grafica.resize();
    });
    observador = new ResizeObserver(() => {
      if (!grafica.isDisposed()) grafica.resize();
    });
    observador.observe(contenedor);
    if (solicitud > 0 && solicitudes.get(clave) !== solicitud) {
      solicitudes.set(clave, solicitud);
      requestAnimationFrame(() => {
        if (!destruido) capturar();
      });
    }
  }).catch(errorVisible);

  return () => {
    destruido = true;
    boton.onclick = null;
    if (observador) observador.disconnect();
    if (grafica && !grafica.isDisposed()) {
      try {
        memoria.set(clave, { firma, estado: grafica.getOption() });
      } finally {
        grafica.dispose();
      }
    }
  };
}
"""


@dataclass(frozen=True, slots=True)
class CapturaEcharts:
    """Imagen PNG, opciones interactivas y nombre del archivo."""

    estado_echarts: dict[str, object]
    imagen_png: bytes
    nombre_archivo: str = ""
    solicitud_captura: int = 0


def _validar_opciones(opciones: dict[str, object]) -> str:
    """Rechaza opciones no serializables antes de enviarlas al navegador."""
    if not isinstance(opciones, dict):
        raise ValueError("Las opciones ECharts deben ser un diccionario.")
    if not isinstance(opciones.get("series"), list) or not opciones["series"]:
        raise ValueError("La gráfica necesita al menos una serie ECharts.")
    try:
        serializada = json.dumps(opciones, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Las opciones ECharts no son JSON válido.") from error
    if len(serializada.encode("utf-8")) > MAXIMO_ESTADO_BYTES:
        raise ValueError("La configuración de la gráfica excede el límite.")
    return serializada


def _titulo_inicial(opciones: dict[str, object]) -> str:
    """Extrae el nombre visible original cuando existe en ECharts."""
    titulo = opciones.get("title")
    if isinstance(titulo, list) and titulo:
        titulo = titulo[0]
    if isinstance(titulo, dict):
        texto = titulo.get("text")
        if isinstance(texto, str) and texto.strip():
            return texto.strip()[:120]
    return "Gráfica"


def decodificar_captura(valor: object) -> CapturaEcharts | None:
    """Rechaza cargas malformadas y reutiliza los límites del almacenamiento."""
    if valor is None:
        return None
    if not isinstance(valor, dict):
        raise ValueError("La captura recibida no es válida.")
    estado = valor.get("estado_echarts")
    imagen_base64 = valor.get("imagen_png_base64")
    _estado_json(estado)
    if not isinstance(imagen_base64, str):
        raise ValueError("La captura no incluye una imagen PNG válida.")
    if len(imagen_base64) > (MAXIMO_PNG_BYTES * 4 // 3) + 8:
        raise ValueError("La imagen de la captura supera el límite permitido.")
    try:
        imagen = base64.b64decode(imagen_base64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("La imagen de la captura no es Base64 válido.") from error
    _validar_png(imagen)

    solicitud = valor.get("solicitud_captura", 0)
    if isinstance(solicitud, bool) or not isinstance(solicitud, int) or solicitud < 0:
        raise ValueError("La solicitud asociada a la captura no es válida.")

    nombre = valor.get("nombre_archivo", "")
    if not isinstance(nombre, str) or len(nombre) > 120:
        raise ValueError("El nombre recibido para la gráfica no es válido.")

    return CapturaEcharts(
        estado_echarts=estado,
        imagen_png=imagen,
        nombre_archivo=nombre,
        solicitud_captura=solicitud,
    )


@lru_cache(maxsize=1)
def _componente() -> Any:
    """Registra una sola vez el puente de componentes v2."""
    import streamlit as st

    return st.components.v2.component(
        "wattwise_echarts_capturable_v2", html=_HTML, css=_CSS, js=_JS
    )


def mostrar_echarts_capturable(
    opciones: dict[str, object],
    *,
    clave: str,
    altura: int = 540,
    solicitud_captura: int = 0,
    mostrar_boton_prueba: bool = False,
    titulo_predeterminado: str | None = None,
) -> CapturaEcharts | None:
    """Dibuja ECharts a altura estable y devuelve la captura solicitada.

    La exportación HTML se presenta en los controles de Inventarios.
    El PNG visible se obtiene del toolbox nativo de ECharts.
    """
    if not isinstance(clave, str) or not clave.strip() or len(clave) > 128:
        raise ValueError("La clave del gráfico no es válida.")
    if isinstance(altura, bool) or not isinstance(altura, int) or not 240 <= altura <= 1600:
        raise ValueError("La altura del gráfico no es válida.")
    if (
        isinstance(solicitud_captura, bool)
        or not isinstance(solicitud_captura, int)
        or solicitud_captura < 0
    ):
        raise ValueError("La solicitud de captura debe ser un entero no negativo.")
    if not isinstance(mostrar_boton_prueba, bool):
        raise ValueError("La opción de prueba debe ser un booleano.")
    if titulo_predeterminado is not None and (
        not isinstance(titulo_predeterminado, str)
        or not 1 <= len(titulo_predeterminado.strip()) <= 120
    ):
        raise ValueError("El título predeterminado no es válido.")
    serializada = _validar_opciones(opciones)
    firma = hashlib.sha256(serializada.encode("utf-8")).hexdigest()
    titulo = titulo_predeterminado or _titulo_inicial(opciones)
    resultado: Any = _componente()(
        key=f"ww_echarts_{clave}",
        height=altura,
        width="stretch",
        data={
            "opciones": opciones,
            "altura": altura,
            "clave_grafica": clave,
            "firma_opciones": firma,
            "solicitud_captura": solicitud_captura,
            "mostrar_boton_prueba": mostrar_boton_prueba,
            "titulo_predeterminado": titulo,
        },
        on_captura_change=lambda: None,
    )
    return decodificar_captura(resultado.captura)
