"""Analisis descriptivo de datos nominales y corrientes de motores."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

HP_A_KW = 0.745699872
MAXIMO_MOTORES = 10_000


@dataclass(frozen=True, slots=True)
class Motor:
    """Motor documentado en el inventario, sin diagnostico de fallas."""

    area: str
    equipo: str
    potencia_nominal_hp: float
    numero_fases: int
    corriente_nominal_a: float
    corriente_medida_a: float
    horas_operacion_mes: float

    @property
    def potencia_salida_nominal_kw(self) -> float:
        """Convierte HP mecanicos de placa a kW de salida nominal."""
        return self.potencia_nominal_hp * HP_A_KW

    @property
    def relacion_corriente_pct(self) -> float:
        """Porcentaje de corriente medida respecto a la nominal."""
        return 100 * self.corriente_medida_a / self.corriente_nominal_a


@dataclass(frozen=True, slots=True)
class ResumenMotores:
    """Agregados nominales sin estimar demanda ni energia electrica."""

    registros: tuple[Motor, ...]
    potencia_salida_nominal_total_kw: float
    cantidad_motores: int
    motores_corriente_superior_nominal: int
    areas_identificadas: int


def _texto(valor: object, campo: str) -> str:
    """Valida los textos de identificacion."""
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"{campo} debe ser texto no vacio.")

    texto = valor.strip()

    if len(texto) > 160:
        raise ValueError(f"{campo} supera 160 caracteres.")

    return texto


def _numero(
    valor: object,
    campo: str,
    *,
    positivo: bool = False,
) -> float:
    """Exige numeros finitos y restringe positivos cuando procede."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"{campo} debe ser numerico.")

    numero = float(valor)

    if not isfinite(numero) or numero < 0 or (positivo and numero == 0):
        raise ValueError(f"{campo} fuera del rango permitido.")

    return numero


def _fases(valor: object) -> int:
    """Admite motores monofasicos o trifasicos declarados."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError("numero_fases debe ser 1 o 3.")

    if valor not in (1, 3):
        raise ValueError("numero_fases debe ser 1 o 3.")

    return int(valor)


def validar_motor(fila: dict[str, object]) -> Motor:
    """Valida un motor sin completar parametros desconocidos."""
    horas = _numero(
        fila.get("horas_operacion_mes"),
        "horas_operacion_mes",
    )

    if horas > 744:
        raise ValueError("horas_operacion_mes no puede superar 744.")

    return Motor(
        area=_texto(fila.get("area"), "area"),
        equipo=_texto(fila.get("equipo"), "equipo"),
        potencia_nominal_hp=_numero(
            fila.get("potencia_nominal_hp"),
            "potencia_nominal_hp",
            positivo=True,
        ),
        numero_fases=_fases(fila.get("numero_fases")),
        corriente_nominal_a=_numero(
            fila.get("corriente_nominal_a"),
            "corriente_nominal_a",
            positivo=True,
        ),
        corriente_medida_a=_numero(
            fila.get("corriente_medida_a"),
            "corriente_medida_a",
        ),
        horas_operacion_mes=horas,
    )


def analizar_motores(
    filas: list[dict[str, object]],
) -> ResumenMotores:
    """Calcula indicadores de placa y compara corrientes declaradas."""
    if not filas or len(filas) > MAXIMO_MOTORES:
        raise ValueError("Se requieren entre 1 y 10000 motores.")

    registros: list[Motor] = []

    for numero, fila in enumerate(filas, start=2):
        try:
            registros.append(validar_motor(fila))
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError(f"Fila Excel {numero}: {error}") from error

    potencia = sum(m.potencia_salida_nominal_kw for m in registros)

    if not isfinite(potencia):
        raise ValueError("La suma de potencias excede el rango numerico.")

    return ResumenMotores(
        registros=tuple(registros),
        potencia_salida_nominal_total_kw=potencia,
        cantidad_motores=len(registros),
        motores_corriente_superior_nominal=sum(
            m.corriente_medida_a > m.corriente_nominal_a for m in registros
        ),
        areas_identificadas=len({m.area for m in registros}),
    )
