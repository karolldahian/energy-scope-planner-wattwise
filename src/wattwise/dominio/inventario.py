"""Calcula indicadores de inventarios electricos WattWise."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class RegistroInventario:
    """Representa un equipo o grupo de equipos."""

    equipo: str
    tipo_carga: str
    cantidad: int
    potencia_unitaria_kw: float
    area: str = ""
    frontera: str = ""
    ubicacion_detalle: str = ""

    @property
    def potencia_instalada_kw(self) -> float:
        """Calcula potencia instalada, no demanda ni energia."""
        return self.cantidad * self.potencia_unitaria_kw


@dataclass(frozen=True, slots=True)
class ResultadoInventario:
    """Agrupa registros y resultados verificables."""

    registros: tuple[RegistroInventario, ...]
    potencia_total_kw: float
    cantidad_equipos: int
    cantidad_areas: int
    tipo_carga_predominante: str


def _texto(valor: object, nombre: str, obligatorio: bool) -> str:
    """Valida textos sin inventar datos faltantes."""
    if valor is None and not obligatorio:
        return ""

    if not isinstance(valor, str):
        raise ValueError(f"{nombre} debe ser texto.")

    resultado = valor.strip()

    if obligatorio and not resultado:
        raise ValueError(f"{nombre} es obligatorio.")

    return resultado


def _cantidad(valor: object) -> int:
    """Exige una cantidad positiva y entera."""
    if isinstance(valor, bool):
        raise ValueError("cantidad no admite booleanos.")

    if isinstance(valor, int):
        resultado = valor
    elif isinstance(valor, float) and isfinite(valor) and valor.is_integer():
        resultado = int(valor)
    else:
        raise ValueError("cantidad debe ser un entero.")

    if resultado <= 0:
        raise ValueError("cantidad debe ser mayor que cero.")

    return resultado


def _potencia(valor: object) -> float:
    """Valida potencia unitaria nominal en kW."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError("potencia_unitaria_kw debe ser numerica.")

    resultado = float(valor)

    if not isfinite(resultado) or resultado < 0:
        raise ValueError("potencia_unitaria_kw debe ser finita y no negativa.")

    return resultado


def validar_registro(fila: Mapping[str, object]) -> RegistroInventario:
    """Valida una fila de inventario normalizada."""
    return RegistroInventario(
        equipo=_texto(fila.get("equipo"), "equipo", True),
        tipo_carga=_texto(fila.get("tipo_carga"), "tipo_carga", True),
        cantidad=_cantidad(fila.get("cantidad")),
        potencia_unitaria_kw=_potencia(fila.get("potencia_unitaria_kw")),
        area=_texto(fila.get("area"), "area", False),
        frontera=_texto(fila.get("frontera"), "frontera", False),
        ubicacion_detalle=_texto(
            fila.get("ubicacion_detalle"),
            "ubicacion_detalle",
            False,
        ),
    )


def analizar_inventario(
    filas: list[dict[str, object]],
) -> ResultadoInventario:
    """Valida el inventario completo antes de calcular resultados."""
    if not filas:
        raise ValueError("El inventario no contiene registros.")

    if len(filas) > 100_000:
        raise ValueError("Se supera el limite de 100000 registros.")

    registros: list[RegistroInventario] = []

    for numero, fila in enumerate(filas, start=2):
        try:
            registros.append(validar_registro(fila))
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError(f"Fila Excel {numero}: {error}") from error

    potencia_total = sum(registro.potencia_instalada_kw for registro in registros)

    if not isfinite(potencia_total):
        raise ValueError("La potencia total excede el rango numerico.")

    cantidad_total = sum(registro.cantidad for registro in registros)

    areas = {registro.area for registro in registros if registro.area}

    potencia_por_tipo: dict[str, float] = {}

    for registro in registros:
        potencia_por_tipo[registro.tipo_carga] = (
            potencia_por_tipo.get(registro.tipo_carga, 0.0) + registro.potencia_instalada_kw
        )

    tipo_predominante = max(
        potencia_por_tipo,
        key=lambda nombre: potencia_por_tipo[nombre],
    )

    return ResultadoInventario(
        registros=tuple(registros),
        potencia_total_kw=potencia_total,
        cantidad_equipos=cantidad_total,
        cantidad_areas=len(areas),
        tipo_carga_predominante=tipo_predominante,
    )
