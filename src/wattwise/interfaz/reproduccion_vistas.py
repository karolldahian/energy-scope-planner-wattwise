"""Reconstruye graficas existentes desde filtros y originales verificados."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from wattwise.dominio.vistas import validar_vista
from wattwise.interfaz.graficos_completos import (
    barras_areas,
    barras_motores,
    corrientes_motores,
    dona_cargas,
    indicadores_inventario,
    indicadores_motores,
    mapa_revision_motores,
    matriz_inventario,
    pareto_inventario,
)
from wattwise.interfaz.mediciones_avanzadas import estadisticas, grafico_temporal


@dataclass(frozen=True, slots=True)
class VistaReconstruida:
    """Grafica, datos filtrados e indicadores ligados a la misma fuente."""

    grafico: dict[str, Any]
    registros: list[dict[str, object]]
    indicadores: dict[str, object]


def _filtrar(
    registros: list[dict[str, object]],
    filtros: dict[str, str],
) -> list[dict[str, object]]:
    """Aplica coincidencia exacta sin interpretar nombres como circuitos."""
    resultado = registros
    for campo, valor in filtros.items():
        if valor != "Todos":
            resultado = [
                fila for fila in resultado if str(fila.get(campo) or "Sin especificar") == valor
            ]
    return resultado


def _inventario(
    registros: list[dict[str, object]],
    grafica: str,
    opciones: dict[str, object],
) -> dict[str, Any]:
    """Selecciona una de las cinco graficas originales de inventario."""
    if grafica in ("Pareto por tipo de carga", "Pareto por equipo"):
        campo = "tipo_carga" if grafica == "Pareto por tipo de carga" else "equipo"
        return pareto_inventario(
            registros,
            campo,
            linea_barras=opciones["linea_barras"],
            acumulado=opciones["acumulado"],
            umbral_80=opciones["umbral_80"],
        )
    if grafica == "Potencia por area":
        return barras_areas(registros)
    if grafica == "Distribucion por tipo de carga":
        return dona_cargas(registros)
    return matriz_inventario(registros)


def _motores(
    registros: list[dict[str, object]],
    grafica: str,
    opciones: dict[str, object],
) -> dict[str, Any]:
    """Respeta la ausencia de horas y la diferencia entre A, HP y horas."""
    if grafica == "Corriente nominal vs medida":
        return corrientes_motores(registros)
    if grafica == "Mapa de revision":
        resultado = mapa_revision_motores(registros, opciones["mapa_variable"])
    else:
        campo = (
            "potencia_nominal_hp"
            if grafica == "Potencia nominal por motor"
            else "horas_operacion_mes"
        )
        resultado = barras_motores(registros, campo)
    if resultado is None:
        raise ValueError("No existen valores disponibles para esta grafica de motores.")
    return resultado


def _mediciones(
    registros: list[dict[str, object]],
    configuracion: dict[str, object],
) -> VistaReconstruida:
    """Rechaza alcance mezclado y no revive series que carezcan de datos."""
    identidades = {
        tuple(
            str(fila.get(campo) or "Sin especificar")
            for campo in ("frontera", "area", "punto_medicion")
        )
        for fila in registros
    }
    if len(identidades) != 1:
        raise ValueError("La vista mezclaria puntos o fronteras de medicion diferentes.")
    periodo = configuracion["periodo"]
    registros = [
        fila
        for fila in registros
        if isinstance(fila.get("fecha_hora"), datetime)
        and periodo["desde"] <= fila["fecha_hora"].date().isoformat() <= periodo["hasta"]
    ]
    if not registros:
        raise ValueError("La vista no tiene mediciones dentro del periodo guardado.")
    indicadores: dict[str, object] = {}
    for campo in configuracion["series"]:
        resumen = estadisticas(registros, campo)
        if resumen is None:
            raise ValueError(f"La variable {campo} no tiene datos en esta vista.")
        indicadores[campo] = {
            "maximo": resumen.maximo,
            "minimo": resumen.minimo,
            "promedio": resumen.promedio,
            "p95": resumen.p95,
            "validos": resumen.validos,
            "total": resumen.total,
        }
    grafico = grafico_temporal(
        registros,
        configuracion["series"],
        configuracion["grafica"],
        tuple(configuracion["marcas"]),
        configuracion["referencia"],
    )
    return VistaReconstruida(grafico, registros, indicadores)


def reconstruir_vista(
    tipo: str,
    registros: list[dict[str, object]],
    configuracion: dict[str, object],
) -> VistaReconstruida:
    """Recalcula una vista validada sin confiar en un grafico JSON almacenado."""
    config = validar_vista(tipo, configuracion)
    filtrados = _filtrar(registros, config["filtros"])
    if not filtrados:
        raise ValueError("El filtro guardado ya no contiene registros.")
    if tipo == "inventario":
        return VistaReconstruida(
            _inventario(filtrados, config["grafica"], config["opciones"]),
            filtrados,
            indicadores_inventario(filtrados),
        )
    if tipo == "motores":
        return VistaReconstruida(
            _motores(filtrados, config["grafica"], config["opciones"]),
            filtrados,
            indicadores_motores(filtrados),
        )
    return _mediciones(filtrados, config)
