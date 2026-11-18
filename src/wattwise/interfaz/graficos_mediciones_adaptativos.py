"""Gráficas horarias y diagnósticos descriptivos de mediciones eléctricas."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import isfinite
from statistics import median
from typing import Any

AZUL = "#2563eb"
VERDE = "#16a34a"
NARANJA = "#f59e0b"
ROJO = "#dc2626"

REFERENCIA_FP = 0.90
REFERENCIA_DESBALANCE = 10.0
CARGA_MINIMA_KW = 0.1
FRACCION_PICO = 0.01

FASES_CORRIENTE = (
    ("i_l1_a", "L1 (A)", VERDE),
    ("i_l2_a", "L2 (A)", NARANJA),
    ("i_l3_a", "L3 (A)", ROJO),
)
FASES_TENSION = (
    ("v_l1_v", "L1 (V)", VERDE),
    ("v_l2_v", "L2 (V)", NARANJA),
    ("v_l3_v", "L3 (V)", ROJO),
)


def _numero(fila: dict[str, object], campo: str) -> float | None:
    """Acepta números finitos sin transformar valores faltantes en ceros."""
    valor = fila.get(campo)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    numero = float(valor)
    return numero if isfinite(numero) else None


def _fechados(
    registros: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Utiliza únicamente registros con fecha válida."""
    return [fila for fila in registros if isinstance(fila.get("fecha_hora"), datetime)]


def _horas() -> list[str]:
    """Genera las 24 categorías horarias."""
    return [f"{hora:02d}:00" for hora in range(24)]


def _base(
    titulo: str,
    *,
    eje_tiempo: bool = False,
) -> dict[str, Any]:
    """Mantiene el estilo blanco, zoom y exportación PNG."""
    return {
        "backgroundColor": "#ffffff",
        "title": {
            "text": titulo,
            "left": "center",
            "textStyle": {"fontSize": 15},
        },
        "tooltip": {"trigger": "axis"},
        "legend": {"type": "scroll", "top": 35},
        "grid": {
            "left": 65,
            "right": 48,
            "top": 85,
            "bottom": 75,
            "containLabel": True,
        },
        "toolbox": {
            "right": 8,
            "feature": {
                "saveAsImage": {
                    "type": "png",
                    "pixelRatio": 2,
                    "name": "wattwise_diagnostico",
                },
                "restore": {},
            },
        },
        "animation": False,
        "xAxis": (
            {"type": "time", "name": "Fecha y hora"}
            if eje_tiempo
            else {"type": "category", "data": _horas()}
        ),
        "dataZoom": [
            {"type": "inside"},
            {"type": "slider", "bottom": 28},
        ],
    }


def _serie_barras(
    nombre: str,
    valores: list[float | None],
    unidad: str,
    color: str,
    mostrar_valores: bool,
) -> dict[str, Any]:
    """Agrega etiquetas opcionales sin modificar la serie numérica."""
    datos: list[object] = [round(valor, 4) if valor is not None else None for valor in valores]

    if mostrar_valores:
        datos = [
            {
                "value": round(valor, 4),
                "label": {
                    "formatter": f"{valor:,.2f} {unidad}".strip(),
                },
            }
            if valor is not None
            else None
            for valor in valores
        ]

    return {
        "name": nombre,
        "type": "bar",
        "data": datos,
        "itemStyle": {"color": color},
        "label": {
            "show": mostrar_valores,
            "position": "top",
            "fontSize": 10,
        },
    }


def _por_hora(
    registros: list[dict[str, object]],
    campo: str,
) -> dict[int, list[float]]:
    """Agrupa muestras por hora sin inventar registros."""
    grupos: dict[int, list[float]] = defaultdict(list)

    for fila in _fechados(registros):
        valor = _numero(fila, campo)
        if valor is not None:
            grupos[fila["fecha_hora"].hour].append(valor)

    return grupos


def _promedios(
    grupos: dict[int, list[float]],
) -> list[float | None]:
    """Calcula promedio solamente en horas con datos."""
    return [
        sum(grupos[hora]) / len(grupos[hora]) if grupos.get(hora) else None for hora in range(24)
    ]


def _umbral_carga(
    registros: list[dict[str, object]],
) -> float:
    """Define un umbral descriptivo de carga activa significativa."""
    potencias = [
        potencia
        for fila in registros
        if (potencia := _numero(fila, "p_total_kw")) is not None and potencia > 0
    ]
    return max(
        CARGA_MINIMA_KW,
        max(potencias, default=0) * FRACCION_PICO,
    )


def _fp_validos(
    registros: list[dict[str, object]],
) -> list[tuple[datetime, float, float]]:
    """Empareja FP y potencia activa del mismo registro."""
    umbral = _umbral_carga(registros)
    datos = []

    for fila in _fechados(registros):
        fp = _numero(fila, "fp_total")
        potencia = _numero(fila, "p_total_kw")

        if fp is not None and 0 <= fp <= 1 and potencia is not None and potencia > umbral:
            datos.append((fila["fecha_hora"], fp, potencia))

    return datos


def _potencia_barras(
    registros: list[dict[str, object]],
    campo: str,
    etiquetas: bool,
) -> dict[str, Any] | None:
    """Barras de potencia promedio y puntos de máximo por hora."""
    grupos = _por_hora(registros, campo)
    if not grupos:
        return None

    grafico = _base("Potencia por hora: promedio y pico máximo (kW)")
    grafico["yAxis"] = {
        "type": "value",
        "name": "kW",
        "scale": True,
    }

    datos_picos = []
    for hora, valores in sorted(grupos.items()):
        maximo = max(valores)
        punto: Any = [hora, round(maximo, 4)]
        if etiquetas:
            punto = {
                "value": punto,
                "label": {
                    "formatter": f"{maximo:,.2f} kW",
                },
            }
        datos_picos.append(punto)

    grafico["series"] = [
        _serie_barras(
            "Promedio (kW)",
            _promedios(grupos),
            "kW",
            AZUL,
            etiquetas,
        ),
        {
            "name": "Pico registrado (kW)",
            "type": "scatter",
            "data": datos_picos,
            "symbolSize": 11,
            "itemStyle": {"color": NARANJA},
            "label": {
                "show": etiquetas,
                "position": "top",
                "fontSize": 10,
            },
        },
    ]
    return grafico


def _fp_barras(
    registros: list[dict[str, object]],
    etiquetas: bool,
) -> dict[str, Any] | None:
    """Promedio horario del FP ponderado por potencia activa."""
    datos = _fp_validos(registros)
    if not datos:
        return None

    grupos: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for fecha, fp, potencia in datos:
        grupos[fecha.hour].append((fp, potencia))

    valores = [
        (sum(fp * kw for fp, kw in grupos[hora]) / sum(kw for _, kw in grupos[hora]))
        if grupos.get(hora)
        else None
        for hora in range(24)
    ]

    grafico = _base("Factor de potencia ponderado por hora")
    grafico["yAxis"] = {
        "type": "value",
        "name": "FP",
        "min": 0,
        "max": 1,
    }

    barra = _serie_barras(
        "FP ponderado",
        valores,
        "",
        AZUL,
        etiquetas,
    )
    barra["markLine"] = {
        "silent": True,
        "symbol": "none",
        "label": {"formatter": "Referencia 0,90"},
        "data": [{"yAxis": REFERENCIA_FP}],
        "lineStyle": {
            "color": ROJO,
            "type": "dashed",
        },
    }
    grafico["series"] = [barra]
    return grafico


def _tension_barras(
    registros: list[dict[str, object]],
    campo: str,
    etiquetas: bool,
) -> dict[str, Any] | None:
    """Barras de tensión con bigotes de mínimo y máximo horarios."""
    grupos = _por_hora(registros, campo)
    if not grupos:
        return None

    valores = [valor for muestras in grupos.values() for valor in muestras]
    inferior = min(valores)
    superior = max(valores)
    margen = max(
        abs(median(valores)) * 0.10,
        (superior - inferior) * 0.05,
        0.1,
    )

    grafico = _base("Tensión por hora: promedio y mínimo–máximo (V)")
    grafico["yAxis"] = {
        "type": "value",
        "name": "V",
        "scale": True,
        "min": round(inferior - margen, 4),
        "max": round(superior + margen, 4),
    }

    promedios = _promedios(grupos)
    grafico["series"] = [
        _serie_barras(
            "Promedio (V)",
            promedios,
            "V",
            AZUL,
            etiquetas,
        ),
        {
            "name": "Bigotes mínimo–máximo (V)",
            "type": "candlestick",
            "barWidth": 8,
            "itemStyle": {
                "color": NARANJA,
                "color0": NARANJA,
                "borderColor": NARANJA,
                "borderColor0": NARANJA,
            },
            "data": [
                [
                    round(promedios[hora], 4),
                    round(promedios[hora], 4),
                    round(min(grupos[hora]), 4),
                    round(max(grupos[hora]), 4),
                ]
                if grupos.get(hora)
                else None
                for hora in range(24)
            ],
        },
    ]
    return grafico


def _corriente_barras(
    registros: list[dict[str, object]],
    etiquetas: bool,
) -> dict[str, Any] | None:
    """Tres barras agrupadas por hora para las fases disponibles."""
    series = []

    for campo, nombre, color in FASES_CORRIENTE:
        grupos = _por_hora(registros, campo)
        if grupos:
            series.append(
                _serie_barras(
                    nombre,
                    _promedios(grupos),
                    "A",
                    color,
                    etiquetas,
                )
            )

    if not series:
        return None

    grafico = _base("Corriente promedio por hora y fase (A)")
    grafico["yAxis"] = {
        "type": "value",
        "name": "A",
        "min": 0,
    }
    grafico["series"] = series
    return grafico


def grafico_barras_horarias(
    registros: list[dict[str, object]],
    campo: str,
    *,
    mostrar_valores: bool = False,
) -> dict[str, Any] | None:
    """Construye el comportamiento horario de la magnitud elegida."""
    if campo.startswith("p_") and campo.endswith("_kw"):
        return _potencia_barras(registros, campo, mostrar_valores)
    if campo == "fp_total":
        return _fp_barras(registros, mostrar_valores)
    if campo.startswith("v_") and campo.endswith("_v"):
        return _tension_barras(registros, campo, mostrar_valores)
    if campo.startswith("i_") and campo.endswith("_a"):
        return _corriente_barras(registros, mostrar_valores)

    raise ValueError("La variable horaria no pertenece a un grupo conocido.")


def _potencia_mapa(
    registros: list[dict[str, object]],
    campo: str,
    etiquetas: bool,
) -> dict[str, Any] | None:
    """Mapa día-hora de potencia promedio de un mismo punto."""
    grupos: dict[tuple[str, int], list[float]] = defaultdict(list)

    for fila in _fechados(registros):
        valor = _numero(fila, campo)
        if valor is not None:
            fecha = fila["fecha_hora"]
            grupos[(fecha.date().isoformat(), fecha.hour)].append(valor)

    if not grupos:
        return None

    dias = sorted({dia for dia, _ in grupos})
    indice_dias = {dia: indice for indice, dia in enumerate(dias)}

    datos: list[object] = []
    for (dia, hora), valores in sorted(grupos.items()):
        potencia = sum(valores) / len(valores)
        celda = [
            hora,
            indice_dias[dia],
            round(potencia, 4),
        ]

        dato: Any = celda
        if etiquetas:
            dato = {
                "value": celda,
                "label": {
                    "formatter": f"{potencia:,.1f} kW",
                },
            }
        datos.append(dato)

    potencias = [sum(muestras) / len(muestras) for muestras in grupos.values()]

    grafico = _base("Potencia media por día y hora (kW)")
    grafico["tooltip"] = {"trigger": "item"}
    grafico["grid"] = {
        "left": 95,
        "right": 110,
        "top": 65,
        "bottom": 70,
        "containLabel": True,
    }
    grafico["xAxis"] = {
        "type": "category",
        "data": _horas(),
    }
    grafico["yAxis"] = {
        "type": "category",
        "data": dias,
        "inverse": True,
    }
    grafico["visualMap"] = {
        "min": min(potencias),
        "max": max(
            max(potencias),
            min(potencias) + 0.001,
        ),
        "calculable": True,
        "right": 8,
        "top": "middle",
    }
    grafico["series"] = [
        {
            "name": "Potencia media (kW)",
            "type": "heatmap",
            "data": datos,
            "label": {
                "show": etiquetas,
                "position": "inside",
                "fontSize": 10,
                "color": "#ffffff",
                "textBorderColor": "#111827",
                "textBorderWidth": 2,
            },
        }
    ]
    grafico["dataZoom"] = [
        {"type": "inside", "yAxisIndex": 0},
        {
            "type": "slider",
            "yAxisIndex": 0,
            "right": 5,
            "end": min(
                100,
                1400 / max(len(dias), 1),
            ),
        },
    ]
    return grafico


def _dispersion_fp(
    registros: list[dict[str, object]],
    etiquetas: bool,
) -> dict[str, Any] | None:
    """Compara potencia y FP de cada muestra sin inferir multas."""
    datos = _fp_validos(registros)
    if not datos:
        return None

    bajos: list[dict[str, Any]] = []
    normales: list[dict[str, Any]] = []

    for fecha, fp, potencia in datos:
        punto = {
            "name": fecha.isoformat(),
            "value": [
                round(potencia, 5),
                round(fp, 5),
            ],
        }
        if etiquetas:
            punto["label"] = {
                "formatter": f"{potencia:.1f} kW; FP {fp:.2f}",
            }

        if fp < REFERENCIA_FP:
            bajos.append(punto)
        else:
            normales.append(punto)

    grafico = _base("Dispersión: potencia activa frente a FP")
    grafico["tooltip"] = {
        "trigger": "item",
        "formatter": "{b}: {c}",
    }
    grafico["xAxis"] = {
        "type": "value",
        "name": "Potencia activa (kW)",
        "scale": True,
    }
    grafico["yAxis"] = {
        "type": "value",
        "name": "FP",
        "min": 0,
        "max": 1,
    }
    grafico["series"] = [
        {
            "name": "FP < 0,90 (revisión)",
            "type": "scatter",
            "data": bajos,
            "symbolSize": 9,
            "itemStyle": {"color": ROJO},
            "label": {
                "show": etiquetas,
                "position": "top",
                "fontSize": 10,
            },
            "markLine": {
                "silent": True,
                "symbol": "none",
                "data": [{"yAxis": REFERENCIA_FP}],
                "lineStyle": {
                    "color": NARANJA,
                    "type": "dashed",
                },
            },
        },
        {
            "name": "FP ≥ 0,90",
            "type": "scatter",
            "data": normales,
            "symbolSize": 9,
            "itemStyle": {"color": VERDE},
            "label": {
                "show": etiquetas,
                "position": "top",
                "fontSize": 10,
            },
        },
    ]
    grafico["dataZoom"] = [{"type": "inside", "xAxisIndex": 0}]
    return grafico


def _tension_minima_curva(
    registros: list[dict[str, object]],
    etiquetas: bool,
) -> dict[str, Any] | None:
    """Curvas del mínimo observado por hora para cada fase disponible."""
    series = []

    for campo, nombre, color in FASES_TENSION:
        grupos = _por_hora(registros, campo)
        if not grupos:
            continue

        valores = [min(grupos[hora]) if grupos.get(hora) else None for hora in range(24)]
        datos: list[object] = [round(valor, 4) if valor is not None else None for valor in valores]

        if etiquetas:
            datos = [
                {
                    "value": round(valor, 4),
                    "label": {
                        "formatter": f"{valor:,.2f} V",
                    },
                }
                if valor is not None
                else None
                for valor in valores
            ]

        series.append(
            {
                "name": nombre,
                "type": "line",
                "data": datos,
                "connectNulls": False,
                "showSymbol": True,
                "symbolSize": 6,
                "itemStyle": {"color": color},
                "lineStyle": {"width": 2},
                "label": {
                    "show": etiquetas,
                    "position": "top",
                    "fontSize": 10,
                },
            }
        )

    if not series:
        return None

    grafico = _base("Tensión mínima registrada por fase y hora (V)")
    grafico["yAxis"] = {
        "type": "value",
        "name": "V",
        "scale": True,
    }
    grafico["series"] = series
    return grafico


def _desbalance(
    fila: dict[str, object],
) -> float | None:
    """Variación máxima respecto a la media de tres corrientes simultáneas."""
    valores = [_numero(fila, campo) for campo, _, _ in FASES_CORRIENTE]

    if any(valor is None or valor < 0 for valor in valores):
        return None

    promedio = sum(valores) / 3
    if promedio <= 0:
        return None

    return 100 * max(abs(valor - promedio) for valor in valores) / promedio


def _curva_desbalance(
    registros: list[dict[str, object]],
    etiquetas: bool,
) -> dict[str, Any] | None:
    """Curva del desbalance con referencia de revisión del 10 %."""
    datos = []
    alertas = []

    ordenados = sorted(
        _fechados(registros),
        key=lambda fila: fila["fecha_hora"],
    )
    for fila in ordenados:
        valor = _desbalance(fila)
        if valor is None:
            continue

        muestra = [
            fila["fecha_hora"].isoformat(),
            round(valor, 4),
        ]
        punto: Any = muestra

        if etiquetas:
            punto = {
                "value": muestra,
                "label": {
                    "formatter": f"{valor:,.1f} %",
                },
            }

        datos.append(punto)
        if valor > REFERENCIA_DESBALANCE:
            alertas.append(punto)

    if not datos:
        return None

    grafico = _base(
        "Desbalance de corriente entre fases (%)",
        eje_tiempo=True,
    )
    grafico["yAxis"] = {
        "type": "value",
        "name": "Desbalance (%)",
        "min": 0,
    }
    grafico["series"] = [
        {
            "name": "Desbalance (%)",
            "type": "line",
            "data": datos,
            "connectNulls": False,
            "showSymbol": False,
            "itemStyle": {"color": AZUL},
            "lineStyle": {"width": 2},
            "label": {
                "show": etiquetas,
                "position": "top",
                "fontSize": 10,
            },
            "markLine": {
                "silent": True,
                "symbol": "none",
                "data": [
                    {
                        "name": "Referencia 10 %",
                        "yAxis": REFERENCIA_DESBALANCE,
                    }
                ],
                "lineStyle": {
                    "type": "dashed",
                    "color": NARANJA,
                },
            },
        },
        {
            "name": "Por encima de referencia",
            "type": "scatter",
            "data": alertas,
            "symbolSize": 10,
            "itemStyle": {"color": ROJO},
            "label": {
                "show": etiquetas,
                "position": "top",
                "fontSize": 10,
            },
        },
    ]
    return grafico


def grafico_diagnostico(
    registros: list[dict[str, object]],
    campo: str,
    *,
    mostrar_valores: bool = False,
) -> dict[str, Any] | None:
    """Devuelve el diagnóstico específico de la magnitud seleccionada."""
    if campo.startswith("p_") and campo.endswith("_kw"):
        return _potencia_mapa(registros, campo, mostrar_valores)

    if campo == "fp_total":
        return _dispersion_fp(registros, mostrar_valores)

    if campo.startswith("v_") and campo.endswith("_v"):
        return _tension_minima_curva(registros, mostrar_valores)

    if campo.startswith("i_") and campo.endswith("_a"):
        return _curva_desbalance(registros, mostrar_valores)

    raise ValueError("La variable no pertenece a un grupo eléctrico conocido.")


def grafico_mapa_horario(
    registros: list[dict[str, object]],
    campo: str,
    *,
    mostrar_valores: bool = False,
) -> dict[str, Any] | None:
    """Conserva el acceso al mapa exclusivamente para potencia."""
    if campo.startswith("p_") and campo.endswith("_kw"):
        return _potencia_mapa(registros, campo, mostrar_valores)
    return None
