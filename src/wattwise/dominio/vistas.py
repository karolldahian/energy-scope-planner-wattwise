"""Contrato versionado de configuraciones reproducibles para graficas WattWise."""

from __future__ import annotations

import json
from datetime import date

GRAFICAS = {
    "inventario": (
        "Pareto por tipo de carga",
        "Pareto por equipo",
        "Potencia por area",
        "Distribucion por tipo de carga",
        "Matriz de potencia instalada",
    ),
    "motores": (
        "Corriente nominal vs medida",
        "Mapa de revision",
        "Potencia nominal por motor",
        "Horas de operacion por motor",
    ),
    "mediciones": (
        "Potencia activa (kW)",
        "Corrientes (A)",
        "Tensiones (V)",
        "Factor de potencia",
    ),
}
FILTROS = {
    "inventario": ("frontera", "area", "tipo_carga", "equipo"),
    "motores": ("area", "numero_fases", "equipo"),
    "mediciones": ("frontera", "area", "punto_medicion"),
}
SERIES = {
    "Potencia activa (kW)": ("p_total_kw", "p_l1_kw", "p_l2_kw", "p_l3_kw"),
    "Corrientes (A)": ("i_total_a", "i_l1_a", "i_l2_a", "i_l3_a"),
    "Tensiones (V)": ("v_total_v", "v_l1_v", "v_l2_v", "v_l3_v"),
    "Factor de potencia": ("fp_total",),
}
MARCAS = ("Máximo", "Mínimo", "Promedio", "P95")
MAXIMO_CONFIG_BYTES = 4096


def _filtros(tipo: str, valor: object) -> dict[str, str]:
    """Rechaza claves inesperadas y filtros excesivamente largos."""
    if not isinstance(valor, dict) or set(valor) != set(FILTROS[tipo]):
        raise ValueError("La vista tiene filtros incompletos o desconocidos.")
    if any(
        not isinstance(item, str) or not 1 <= len(item.strip()) <= 120 for item in valor.values()
    ):
        raise ValueError("Cada filtro debe contener texto valido de hasta 120 caracteres.")
    return {clave: valor[clave].strip() for clave in FILTROS[tipo]}


def _opciones_inventario(valor: dict[str, object]) -> dict[str, object]:
    """Exige opciones booleanas y nunca coerces valores numericos a booleanos."""
    claves = ("linea_barras", "acumulado", "umbral_80")
    if set(valor) != set(claves) or any(type(valor[clave]) is not bool for clave in claves):
        raise ValueError("Opciones de Pareto incorrectas.")
    return {clave: valor[clave] for clave in claves}


def _opciones_motores(valor: dict[str, object]) -> dict[str, object]:
    """Solo admite relacion de corriente u horas de operacion."""
    if set(valor) != {"mapa_variable"} or valor["mapa_variable"] not in (
        "relacion",
        "horas",
    ):
        raise ValueError("La variable del mapa de motores no es valida.")
    return {"mapa_variable": valor["mapa_variable"]}


def _opciones(tipo: str, valor: object) -> dict[str, object]:
    """Valida exclusivamente controles compatibles con cada tipo de grafica."""
    if not isinstance(valor, dict):
        raise ValueError("Las opciones de la vista deben ser un diccionario.")
    if tipo == "inventario":
        return _opciones_inventario(valor)
    if tipo == "motores":
        return _opciones_motores(valor)
    if valor:
        raise ValueError("Las series de mediciones se configuran fuera de opciones.")
    return {}


def _periodo(valor: object) -> dict[str, str]:
    """Requiere fechas ISO reales y un rango que no retroceda."""
    if not isinstance(valor, dict) or set(valor) != {"desde", "hasta"}:
        raise ValueError("El periodo debe incluir desde y hasta.")
    try:
        desde = date.fromisoformat(valor["desde"])
        hasta = date.fromisoformat(valor["hasta"])
    except (TypeError, ValueError) as error:
        raise ValueError("Las fechas del periodo no son validas.") from error
    if desde > hasta:
        raise ValueError("El inicio del periodo es posterior al final.")
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat()}


def _series_validas(valor: object, grafica: str) -> list[str]:
    """Rechaza series duplicadas, de otra magnitud o con tipos extraños."""
    if not isinstance(valor, list) or not valor:
        raise ValueError("Las series no pertenecen a la grafica elegida.")
    if any(not isinstance(serie, str) for serie in valor):
        raise ValueError("Las series no pertenecen a la grafica elegida.")
    if len(valor) != len(set(valor)) or any(serie not in SERIES[grafica] for serie in valor):
        raise ValueError("Las series no pertenecen a la grafica elegida.")
    return list(valor)


def _marcas_validas(valor: object) -> list[str]:
    """Conserva solo referencias estadisticas declaradas en el contrato."""
    if not isinstance(valor, list):
        raise ValueError("Las referencias estadisticas son invalidas.")
    if any(not isinstance(marca, str) for marca in valor):
        raise ValueError("Las referencias estadisticas son invalidas.")
    if len(valor) != len(set(valor)) or any(marca not in MARCAS for marca in valor):
        raise ValueError("Las referencias estadisticas son invalidas.")
    return list(valor)


def _mediciones(configuracion: dict[str, object], grafica: str) -> dict[str, object]:
    """Valida fechas y series sin sustituir fases o periodos ausentes."""
    campos = {
        "version",
        "grafica",
        "filtros",
        "opciones",
        "periodo",
        "series",
        "referencia",
        "marcas",
    }
    if set(configuracion) != campos:
        raise ValueError("El contrato de mediciones es incompleto o desconocido.")
    series = _series_validas(configuracion["series"], grafica)
    referencia = configuracion["referencia"]
    if referencia is not None and referencia not in series:
        raise ValueError("La serie de referencia no esta seleccionada.")
    return {
        "periodo": _periodo(configuracion["periodo"]),
        "series": series,
        "referencia": referencia,
        "marcas": _marcas_validas(configuracion["marcas"]),
    }


def _identificar_vista(tipo: str, configuracion: object) -> str:
    """Comprueba version, modulo y nombre de grafica sin conversiones implicitas."""
    if not isinstance(tipo, str) or tipo not in GRAFICAS or not isinstance(configuracion, dict):
        raise ValueError("Tipo o configuracion de vista no admitidos.")
    if type(configuracion.get("version")) is not int or configuracion["version"] != 1:
        raise ValueError("Version de vista no admitida.")
    grafica = configuracion.get("grafica")
    if grafica not in GRAFICAS[tipo]:
        raise ValueError("Grafica no admitida para este modulo.")
    return grafica


def validar_vista(tipo: str, configuracion: object) -> dict[str, object]:
    """Devuelve una copia canonica sin aceptar instrucciones ni claves arbitrarias."""
    grafica = _identificar_vista(tipo, configuracion)
    esperadas = {"version", "grafica", "filtros", "opciones"}
    if tipo != "mediciones" and set(configuracion) != esperadas:
        raise ValueError("La vista contiene campos desconocidos o incompletos.")
    normalizada: dict[str, object] = {
        "version": 1,
        "grafica": grafica,
        "filtros": _filtros(tipo, configuracion.get("filtros")),
        "opciones": _opciones(tipo, configuracion.get("opciones")),
    }
    if tipo == "mediciones":
        normalizada.update(_mediciones(configuracion, grafica))
    serializada = json.dumps(normalizada, ensure_ascii=False, allow_nan=False)
    if len(serializada.encode("utf-8")) > MAXIMO_CONFIG_BYTES:
        raise ValueError("La configuracion de la vista es demasiado grande.")
    return normalizada
