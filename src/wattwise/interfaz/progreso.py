"""Registro explícito de hitos verificables del desarrollo WattWise."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Hito:
    """Unidad ponderada de avance confirmada mediante verificaciones."""

    nombre: str
    peso: int
    completo: bool


# Marcar completo solo cuando la funcionalidad este integrada y comprobada.
HITOS = (
    Hito("Arquitectura y pruebas base", 10, True),
    Hito("Importacion y analisis de inventarios", 7, True),
    Hito("Importacion y analisis de motores", 7, True),
    Hito("Mediciones del formato inicial", 5, True),
    Hito("Proyectos y resultados en SQLite", 8, True),
    Hito("Importador flexible de mediciones", 6, True),
    Hito("Conexion y filtros de mediciones detalladas", 8, True),
    Hito("Dashboard dinamico ECharts de mediciones", 12, False),
    Hito("Cinco graficas de inventarios y cuatro de motores", 10, True),
    Hito("Archivos originales, edicion y observaciones", 10, False),
    Hito("Comparacion validada y aprendizaje automatico", 9, False),
    Hito("Informes PDF y capturas ECharts", 8, False),
)


def porcentaje_avance() -> int:
    """Calcula un avance ponderado; no estima horas restantes."""
    total = sum(hito.peso for hito in HITOS)
    terminado = sum(hito.peso for hito in HITOS if hito.completo)
    return round(100 * terminado / total) if total else 0


def proximos_hitos() -> tuple[str, ...]:
    """Recoge los pendientes para mantener trazabilidad en pantalla."""
    return tuple(hito.nombre for hito in HITOS if not hito.completo)
