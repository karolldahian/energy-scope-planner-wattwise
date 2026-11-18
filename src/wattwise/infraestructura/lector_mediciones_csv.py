"""Lee mediciones CSV con validacion estricta de estructura y contenido."""

from __future__ import annotations

import csv
from io import StringIO
from math import isfinite

COLUMNAS = (
    "fecha_hora",
    "tension_v",
    "corriente_a",
    "factor_potencia",
    "potencia_activa_kw",
)
MAXIMO_BYTES = 25 * 1024 * 1024
MAXIMO_FILAS = 100_000


def _validar_entrada(contenido: bytes, nombre_archivo: str) -> None:
    """Comprueba extension, contenido binario y tamano maximo."""
    if not isinstance(nombre_archivo, str) or not nombre_archivo.lower().endswith(".csv"):
        raise ValueError("Solo se admiten archivos .csv.")
    if not isinstance(contenido, bytes) or not contenido:
        raise ValueError("El archivo CSV esta vacio o no es valido.")
    if len(contenido) > MAXIMO_BYTES:
        raise ValueError("El CSV supera el limite de 25 MB.")


def _decodificar(contenido: bytes) -> str:
    """Decodifica UTF-8 con BOM opcional y rechaza bytes invalidos."""
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("El CSV debe estar codificado en UTF-8.") from error
    if "\x00" in texto:
        raise ValueError("El CSV contiene caracteres nulos.")
    return texto


def _validar_cabeceras(cabeceras: list[str] | None) -> None:
    """Exige el contrato exacto de columnas y su orden."""
    if cabeceras is None or tuple(cabeceras) != COLUMNAS:
        raise ValueError("Las columnas del CSV no coinciden con la plantilla.")


def _numero(valor: str, nombre: str, numero: int) -> float:
    """Valida un numero decimal finito sin calcular formulas."""
    texto = valor.strip()
    if not texto or texto.startswith(("=", "+", "@")):
        raise ValueError(f"Fila CSV {numero}: {nombre} vacio o formula no permitida.")
    try:
        resultado = float(texto)
    except ValueError as error:
        raise ValueError(f"Fila CSV {numero}: {nombre} debe ser numerico.") from error
    if not isfinite(resultado):
        raise ValueError(f"Fila CSV {numero}: {nombre} debe ser finito.")
    return resultado


def _convertir_fila(fila: list[str], numero: int) -> dict[str, object]:
    """Convierte numeros y mantiene fecha original para el dominio."""
    if len(fila) != len(COLUMNAS):
        raise ValueError(f"Fila CSV {numero}: numero de columnas incorrecto.")
    fecha_hora = fila[0].strip()
    if not fecha_hora or fecha_hora.startswith(("=", "+", "@")):
        raise ValueError(f"Fila CSV {numero}: fecha_hora vacia o formula no permitida.")
    return {
        "fecha_hora": fecha_hora,
        "tension_v": _numero(fila[1], "tension_v", numero),
        "corriente_a": _numero(fila[2], "corriente_a", numero),
        "factor_potencia": _numero(fila[3], "factor_potencia", numero),
        "potencia_activa_kw": _numero(fila[4], "potencia_activa_kw", numero),
    }


def _leer_filas(texto: str) -> list[dict[str, object]]:
    """Controla encabezados, filas vacias y numero maximo de registros."""
    try:
        lector = csv.reader(StringIO(texto, newline=""), strict=True)
        _validar_cabeceras(next(lector, None))
        registros: list[dict[str, object]] = []
        for numero, fila in enumerate(lector, start=2):
            if numero > MAXIMO_FILAS + 1:
                raise ValueError("El CSV supera las 100000 filas permitidas.")
            if not fila or all(not celda.strip() for celda in fila):
                continue
            registros.append(_convertir_fila(fila, numero))
    except csv.Error as error:
        raise ValueError("El archivo CSV tiene estructura invalida.") from error
    if not registros:
        raise ValueError("El CSV no contiene mediciones.")
    return registros


def leer_mediciones_csv(
    contenido: bytes,
    nombre_archivo: str,
) -> list[dict[str, object]]:
    """Importa mediciones CSV sin estimar parametros electricos."""
    _validar_entrada(contenido, nombre_archivo)
    return _leer_filas(_decodificar(contenido))
