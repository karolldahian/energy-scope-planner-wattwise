"""Opciones Apache ECharts para inventarios y motores electricos."""

from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any

AZUL = "#2563eb"
VERDE = "#16a34a"
NARANJA = "#f59e0b"
MORADO = "#9333ea"


def _nombre(valor: object) -> str:
    """Normaliza etiquetas vacias sin modificar la fuente."""
    if isinstance(valor, str) and valor.strip():
        return valor.strip()
    return "Sin especificar"


def _numero(valor: object) -> float:
    """Valida magnitudes para no presentar datos no finitos."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not isfinite(valor):
        raise ValueError("El resultado contiene una magnitud numerica invalida.")
    return float(valor)


def _base(titulo: str, *, orientacion: str = "horizontal") -> dict[str, Any]:
    """Estilo reutilizable, tooltip seguro y exportacion PNG."""
    return {
        "backgroundColor": "#ffffff",
        "title": {"text": titulo, "left": "center", "textStyle": {"fontSize": 16}},
        "tooltip": {"trigger": "axis", "renderMode": "richText"},
        "legend": {"type": "scroll", "top": 36},
        "grid": {"top": 82, "left": 85, "right": 75, "bottom": 95, "containLabel": True},
        "toolbox": {
            "right": 8,
            "feature": {
                "saveAsImage": {"type": "png", "pixelRatio": 2, "name": "wattwise"},
                "restore": {},
            },
        },
        "animation": False,
        "dataZoom": [
            {"type": "inside", "orient": orientacion},
            {"type": "slider", "orient": orientacion, "bottom": 30},
        ],
    }


def _mostrar_etiqueta_barra(serie: dict[str, Any], posicion: str, unidad: str) -> None:
    """Agrega valores visibles manteniendo las magnitudes de cada barra."""
    serie["label"] = {"show": True, "position": posicion, "fontSize": 11}
    serie["data"] = [
        {
            "value": numero,
            "label": {"formatter": f"{numero:,.2f} {unidad}"},
        }
        for numero in serie["data"]
    ]


def _mostrar_etiquetas_mapa(serie: dict[str, Any], unidad: str) -> None:
    """Presenta solo el valor de la celda, no sus coordenadas ECharts."""
    serie["label"] = {
        "show": True,
        "position": "inside",
        "color": "#ffffff",
        "fontSize": 10,
        "textBorderColor": "#1f2937",
        "textBorderWidth": 2,
    }
    serie["data"] = [
        {
            "value": dato,
            "label": {"formatter": f"{dato[2]:,.2f} {unidad}".strip()},
        }
        for dato in serie["data"]
    ]


def _agrupar_kw(registros: list[dict[str, object]], campo: str) -> list[tuple[str, float]]:
    """Acumula potencia declarada, sin inferir consumo energetico."""
    totales: dict[str, float] = defaultdict(float)
    for registro in registros:
        clave = _nombre(registro.get(campo))
        potencia = _numero(registro["potencia_instalada_kw"])
        if potencia < 0:
            raise ValueError("La potencia instalada no puede ser negativa.")
        totales[clave] += potencia
    return sorted(totales.items(), key=lambda par: (-par[1], par[0]))


def indicadores_inventario(registros: list[dict[str, object]]) -> dict[str, object]:
    """Calcula cuatro KPI a partir de los registros filtrados."""
    agrupados = _agrupar_kw(registros, "tipo_carga")
    areas = {_nombre(registro.get("area")) for registro in registros}
    areas.discard("Sin especificar")
    return {
        "potencia_kw": sum(valor for _, valor in agrupados),
        "equipos": sum(int(_numero(registro["cantidad"])) for registro in registros),
        "areas": len(areas),
        "tipo_predominante": agrupados[0][0] if agrupados else "No disponible",
    }


def _cargas_por_potencia(
    registros: list[dict[str, object]],
) -> list[tuple[str, float, int]]:
    """Agrupa potencia instalada y unidades sin interpretarlas como consumo."""
    potencia: dict[str, float] = defaultdict(float)
    unidades: dict[str, int] = defaultdict(int)
    for registro in registros:
        nombre = _nombre(registro.get("tipo_carga"))
        potencia[nombre] += _numero(registro["potencia_instalada_kw"])
        unidades[nombre] += int(_numero(registro["cantidad"]))
    return sorted(
        ((nombre, valor, unidades[nombre]) for nombre, valor in potencia.items()),
        key=lambda item: (-item[1], item[0]),
    )


def _pareto_por_areas(areas: list[tuple[str, float]], total_kw: float) -> tuple[int, float] | None:
    """Calcula el minimo numero de areas para alcanzar 80% del total conocido."""
    if total_kw <= 0 or any(
        nombre == "Sin especificar" and potencia > 0 for nombre, potencia in areas
    ):
        return None
    acumulado = 0.0
    for cantidad, (nombre, potencia) in enumerate(areas, start=1):
        if nombre == "Sin especificar":
            continue
        acumulado += potencia
        if acumulado + 1e-9 >= 0.8 * total_kw:
            return cantidad, acumulado
    return None


def _equipos_por_unidad(
    registros: list[dict[str, object]],
) -> list[tuple[str, str, float, int]]:
    """Ordena registros por kW de UNA unidad, sin usar potencia del lote."""
    equipos = [
        (
            _nombre(fila.get("equipo")),
            _nombre(fila.get("area")),
            _numero(fila["potencia_unitaria_kw"]),
            int(_numero(fila.get("id_fila", indice))),
        )
        for indice, fila in enumerate(registros, start=1)
    ]
    return sorted(equipos, key=lambda item: (-item[2], item[0], item[3]))[:5]


def resumen_estrategico_inventario(
    registros: list[dict[str, object]],
) -> dict[str, object]:
    """Calcula los cuatro KPI sin alterar el contrato de indicadores existente."""
    cargas = _cargas_por_potencia(registros)
    areas = _agrupar_kw(registros, "area")
    total_kw = sum(valor for _, valor, _ in cargas)
    identificadas = [item for item in areas if item[0] != "Sin especificar"]
    return {
        "total_kw": total_kw,
        "unidades": sum(int(_numero(fila["cantidad"])) for fila in registros),
        "areas_cantidad": len(identificadas),
        "cargas": cargas,
        "areas": identificadas,
        "pareto": _pareto_por_areas(areas, total_kw),
        "top_equipos": _equipos_por_unidad(registros),
    }


def pareto_inventario(
    registros: list[dict[str, object]],
    campo: str,
    *,
    linea_barras: bool = True,
    acumulado: bool = True,
    umbral_80: bool = True,
    mostrar_valores: bool = False,
) -> dict[str, Any]:
    """Barras, linea de cumbres en kW y porcentaje acumulado independiente."""
    agrupados = _agrupar_kw(registros, campo)
    nombres = [nombre for nombre, _ in agrupados]
    valores = [round(valor, 6) for _, valor in agrupados]
    total = sum(valores)
    avance = 0.0
    porcentajes = []
    for valor in valores:
        avance += valor
        porcentajes.append(round(100 * avance / total, 4) if total > 0 else 0.0)
    grafico = _base(f"Pareto de potencia instalada por {campo}")
    grafico["xAxis"] = {
        "type": "category",
        "data": nombres,
        "axisLabel": {"rotate": 35},
    }
    grafico["yAxis"] = [
        {"type": "value", "name": "Potencia (kW)", "min": 0},
        {"type": "value", "name": "Acumulado (%)", "min": 0, "max": 100},
    ]
    series: list[dict[str, Any]] = [
        {
            "name": "Potencia instalada (kW)",
            "type": "bar",
            "data": valores,
            "itemStyle": {"color": AZUL},
            "yAxisIndex": 0,
        }
    ]
    if linea_barras:
        series.append(
            {
                "name": "Linea de cumbres (kW)",
                "type": "line",
                "data": valores,
                "yAxisIndex": 0,
                "symbolSize": 5,
                "itemStyle": {"color": NARANJA},
            }
        )
    if acumulado:
        serie: dict[str, Any] = {
            "name": "Porcentaje acumulado",
            "type": "line",
            "data": porcentajes,
            "yAxisIndex": 1,
            "symbolSize": 5,
            "itemStyle": {"color": VERDE},
        }
        if umbral_80:
            serie["markLine"] = {
                "silent": True,
                "symbol": "none",
                "data": [{"name": "Referencia 80 %", "yAxis": 80}],
            }
        series.append(serie)
    if mostrar_valores:
        _mostrar_etiqueta_barra(series[0], "top", "kW")
    grafico["series"] = series
    grafico["dataZoom"][1]["end"] = min(100, 2000 / max(len(nombres), 1))
    return grafico


def barras_areas(
    registros: list[dict[str, object]], *, mostrar_valores: bool = False
) -> dict[str, Any]:
    """Potencia declarada por area en barras horizontales."""
    agrupados = _agrupar_kw(registros, "area")
    grafico = _base("Potencia instalada por area (kW)", orientacion="vertical")
    grafico["xAxis"] = {"type": "value", "name": "kW", "min": 0}
    grafico["yAxis"] = {
        "type": "category",
        "data": [nombre for nombre, _ in agrupados],
        "inverse": True,
    }
    grafico["series"] = [
        {
            "name": "Potencia (kW)",
            "type": "bar",
            "data": [valor for _, valor in agrupados],
            "itemStyle": {"color": AZUL},
        }
    ]
    if mostrar_valores:
        _mostrar_etiqueta_barra(grafico["series"][0], "right", "kW")
    grafico["dataZoom"][1].pop("bottom")
    grafico["dataZoom"][1]["right"] = 12
    grafico["dataZoom"][1]["end"] = min(100, 2000 / max(len(agrupados), 1))
    return grafico


def dona_cargas(
    registros: list[dict[str, object]], *, mostrar_valores: bool = False
) -> dict[str, Any]:
    """Porcentaje de potencia nominal por categoria declarada."""
    agrupados = _agrupar_kw(registros, "tipo_carga")
    grafico = _base("Distribucion de potencia por tipo de carga")
    grafico.pop("dataZoom")
    grafico["tooltip"] = {"trigger": "item", "renderMode": "richText"}
    grafico["legend"] = {
        "type": "scroll",
        "orient": "vertical",
        "right": 4,
        "top": 90,
    }
    grafico["series"] = [
        {
            "name": "Potencia (kW)",
            "type": "pie",
            "radius": ["42%", "68%"],
            "center": ["40%", "57%"],
            "data": [{"name": nombre, "value": round(valor, 6)} for nombre, valor in agrupados],
            "label": {"show": False},
            "emphasis": {"label": {"show": True}},
        }
    ]
    if mostrar_valores:
        total_kw = sum(potencia for _, potencia in agrupados)
        serie = grafico["series"][0]
        serie["avoidLabelOverlap"] = True
        serie["label"] = {
            "show": True,
            "position": "outside",
            "color": "#1f2937",
            "fontSize": 11,
            "width": 150,
            "overflow": "break",
        }
        serie["labelLine"] = {"show": True, "length": 13, "length2": 12}
        serie["labelLayout"] = {"hideOverlap": True}
        for dato, (nombre, potencia) in zip(serie["data"], agrupados, strict=True):
            porcentaje = 100 * potencia / total_kw if total_kw > 0 else 0.0
            dato["label"] = {"formatter": f"{nombre}\n{potencia:,.2f} kW · {porcentaje:.1f} %"}
    return grafico


def matriz_inventario(
    registros: list[dict[str, object]], *, mostrar_valores: bool = False
) -> dict[str, Any]:
    """Mapa de calor area por tipo, con suma de kW de la muestra."""
    por_celda: dict[tuple[str, str], float] = defaultdict(float)
    for registro in registros:
        clave = (
            _nombre(registro.get("area")),
            _nombre(registro.get("tipo_carga")),
        )
        por_celda[clave] += _numero(registro["potencia_instalada_kw"])
    areas = sorted({clave[0] for clave in por_celda})
    tipos = sorted({clave[1] for clave in por_celda})
    mapa_areas = {nombre: indice for indice, nombre in enumerate(areas)}
    mapa_tipos = {nombre: indice for indice, nombre in enumerate(tipos)}
    datos = [
        [mapa_tipos[tipo], mapa_areas[area], round(valor, 6)]
        for (area, tipo), valor in por_celda.items()
    ]
    grafico = _base(
        "Matriz de potencia instalada: area por carga",
        orientacion="vertical",
    )
    grafico["tooltip"] = {"trigger": "item", "renderMode": "richText"}
    grafico["xAxis"] = {
        "type": "category",
        "data": tipos,
        "axisLabel": {"rotate": 35},
    }
    grafico["yAxis"] = {
        "type": "category",
        "data": areas,
        "inverse": True,
    }
    grafico["visualMap"] = {
        "min": 0,
        "max": max(por_celda.values(), default=0),
        "calculable": True,
        "right": 3,
        "top": "middle",
    }
    grafico["series"] = [{"type": "heatmap", "name": "kW declarados", "data": datos}]
    if mostrar_valores:
        _mostrar_etiquetas_mapa(grafico["series"][0], "")
    grafico["dataZoom"][1].pop("bottom")
    grafico["dataZoom"][1]["right"] = 25
    grafico["dataZoom"][1]["end"] = min(100, 2000 / max(len(areas), 1))
    return grafico


def _etiquetas_motores(registros: list[dict[str, object]]) -> list[str]:
    """Distingue motores con nombres repetidos mediante identificador interno."""
    return [
        f"{_nombre(registro.get('equipo'))} · fila {registro['id_fila']}" for registro in registros
    ]


def _relacion(registro: dict[str, object]) -> float:
    """Relacion entre corrientes, nunca carga mecanica ni eficiencia."""
    nominal = _numero(registro["corriente_nominal_a"])
    if nominal <= 0:
        raise ValueError("La corriente nominal debe ser positiva.")
    return 100 * _numero(registro["corriente_medida_a"]) / nominal


def indicadores_motores(registros: list[dict[str, object]]) -> dict[str, float | int]:
    """Cuatro KPI de motores presentes en el filtro."""
    relaciones = [_relacion(registro) for registro in registros]
    return {
        "motores": len(registros),
        "sobre_nominal": sum(valor > 100 for valor in relaciones),
        "relacion_media_pct": (sum(relaciones) / len(relaciones) if relaciones else 0.0),
        "potencia_hp": sum(_numero(registro["potencia_nominal_hp"]) for registro in registros),
    }


def corrientes_motores(
    registros: list[dict[str, object]], *, mostrar_valores: bool = False
) -> dict[str, Any]:
    """Barras de amperios y linea de relacion porcentual en eje distinto."""
    nombres = _etiquetas_motores(registros)
    nominales = [_numero(registro["corriente_nominal_a"]) for registro in registros]
    medidas = [_numero(registro["corriente_medida_a"]) for registro in registros]
    relaciones = [round(_relacion(registro), 3) for registro in registros]
    grafico = _base("Corriente nominal frente a medida")
    grafico["xAxis"] = {
        "type": "category",
        "data": nombres,
        "axisLabel": {"rotate": 35},
    }
    grafico["yAxis"] = [
        {"type": "value", "name": "Corriente (A)", "min": 0},
        {"type": "value", "name": "Relacion (%)", "min": 0},
    ]
    grafico["series"] = [
        {
            "name": "Nominal (A)",
            "type": "bar",
            "data": nominales,
            "itemStyle": {"color": AZUL},
            "yAxisIndex": 0,
        },
        {
            "name": "Medida (A)",
            "type": "bar",
            "data": medidas,
            "itemStyle": {"color": NARANJA},
            "yAxisIndex": 0,
        },
        {
            "name": "Medida / nominal (%)",
            "type": "line",
            "data": relaciones,
            "yAxisIndex": 1,
            "itemStyle": {"color": VERDE},
            "markLine": {
                "silent": True,
                "symbol": "none",
                "data": [{"name": "Referencia nominal", "yAxis": 100}],
            },
        },
    ]
    if mostrar_valores:
        for serie in grafico["series"][:2]:
            _mostrar_etiqueta_barra(serie, "top", "A")
    grafico["dataZoom"][1]["end"] = min(100, 2000 / max(len(nombres), 1))
    return grafico


def mapa_revision_motores(
    registros: list[dict[str, object]],
    variable: str,
    *,
    mostrar_valores: bool = False,
) -> dict[str, Any] | None:
    """Mapa independiente para porcentaje u horas, nunca escala compartida."""
    if variable not in {"relacion", "horas"}:
        raise ValueError("Variable no admitida para el mapa de motores.")
    valores = [
        _relacion(registro) if variable == "relacion" else registro.get("horas_operacion_mes")
        for registro in registros
    ]
    datos = [
        [0, indice, round(_numero(valor), 3)]
        for indice, valor in enumerate(valores)
        if valor is not None
    ]
    if not datos:
        return None
    titulo = (
        "Relacion de corrientes (%)" if variable == "relacion" else "Horas de operacion (h/mes)"
    )
    grafico = _base(
        f"Mapa de revision: {titulo}",
        orientacion="vertical",
    )
    grafico["tooltip"] = {"trigger": "item", "renderMode": "richText"}
    grafico["xAxis"] = {"type": "category", "data": [titulo]}
    grafico["yAxis"] = {
        "type": "category",
        "data": _etiquetas_motores(registros),
        "inverse": True,
    }
    grafico["visualMap"] = {
        "min": 0,
        "max": max(1.0, max(punto[2] for punto in datos)),
        "calculable": True,
        "right": 3,
        "top": "middle",
    }
    grafico["series"] = [{"type": "heatmap", "name": titulo, "data": datos}]
    if mostrar_valores:
        unidad = "%" if variable == "relacion" else "h"
        _mostrar_etiquetas_mapa(grafico["series"][0], unidad)
    grafico["dataZoom"][1].pop("bottom")
    grafico["dataZoom"][1]["right"] = 28
    grafico["dataZoom"][1]["end"] = min(100, 2000 / max(len(registros), 1))
    return grafico


def barras_motores(
    registros: list[dict[str, object]],
    variable: str,
    *,
    mostrar_valores: bool = False,
) -> dict[str, Any] | None:
    """Barras ordenadas de potencia mecanica HP u horas disponibles."""
    if variable not in {"potencia_nominal_hp", "horas_operacion_mes"}:
        raise ValueError("Variable de motores no reconocida.")
    elegidos = [registro for registro in registros if registro.get(variable) is not None]
    if not elegidos:
        return None
    elegidos.sort(key=lambda registro: -_numero(registro[variable]))
    unidad = "HP mecanicos" if variable == "potencia_nominal_hp" else "h/mes"
    grafico = _base(f"Motores por {unidad}", orientacion="vertical")
    grafico["xAxis"] = {"type": "value", "name": unidad, "min": 0}
    grafico["yAxis"] = {
        "type": "category",
        "data": _etiquetas_motores(elegidos),
        "inverse": True,
    }
    grafico["series"] = [
        {
            "type": "bar",
            "name": unidad,
            "data": [_numero(registro[variable]) for registro in elegidos],
            "itemStyle": {"color": AZUL},
        }
    ]
    if mostrar_valores:
        _mostrar_etiqueta_barra(
            grafico["series"][0], "right", "HP" if variable == "potencia_nominal_hp" else "h"
        )
    grafico["dataZoom"][1].pop("bottom")
    grafico["dataZoom"][1]["right"] = 15
    grafico["dataZoom"][1]["end"] = min(100, 2000 / max(len(elegidos), 1))
    return grafico
