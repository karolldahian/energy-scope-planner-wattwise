"""Importacion validada de la hoja XLSX de motores electricos."""

from __future__ import annotations

from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook

COLUMNAS = (
    "area",
    "equipo",
    "potencia_nominal_hp",
    "numero_fases",
    "corriente_nominal_a",
    "corriente_medida_a",
    "horas_operacion_mes",
)

MAXIMO_BYTES = 25 * 1024 * 1024
MAXIMO_DESCOMPRIMIDO = 150 * 1024 * 1024
MAXIMO_FILAS = 10_000


def _validar_archivo(
    contenido: bytes,
    nombre: str,
) -> None:
    """Valida el formato externo y el tamano del archivo."""
    if not isinstance(contenido, bytes) or not contenido or len(contenido) > MAXIMO_BYTES:
        raise ValueError("Archivo vacio, invalido o superior a 25 MB.")

    if not isinstance(nombre, str) or not nombre.lower().endswith(".xlsx"):
        raise ValueError("Solo se admiten archivos .xlsx.")


def _validar_zip(contenido: bytes) -> None:
    """Rechaza contenedores corruptos o desproporcionados."""
    try:
        with ZipFile(BytesIO(contenido)) as archivo:
            entradas = archivo.infolist()

            if len(entradas) > 1_000:
                raise ValueError("Demasiadas entradas en el XLSX.")

            total = sum(entrada.file_size for entrada in entradas)

            if total > MAXIMO_DESCOMPRIMIDO:
                raise ValueError("XLSX excede el limite de descompresion.")

            if archivo.testzip() is not None:
                raise ValueError("XLSX contiene datos ZIP corruptos.")

    except BadZipFile as error:
        raise ValueError("El archivo no es un XLSX valido.") from error


def _encabezados(
    celdas: tuple[object, ...] | None,
) -> None:
    """Exige exactamente el esquema de motores esperado."""
    if celdas is None:
        raise ValueError("Excel sin encabezados.")

    if any(getattr(celda, "data_type", None) in ("f", "e") for celda in celdas):
        raise ValueError("No se admiten formulas en encabezados.")

    nombres = tuple(
        celda.value.strip().lower() if isinstance(celda.value, str) else celda.value
        for celda in celdas
    )

    if nombres != COLUMNAS:
        raise ValueError("Las columnas de motores no coinciden con la plantilla.")


def _fila(
    celdas: tuple[object, ...],
    numero: int,
) -> dict[str, object] | None:
    """Obtiene valores crudos sin evaluar formulas."""
    if len(celdas) != len(COLUMNAS):
        raise ValueError(f"Fila Excel {numero}: numero de columnas incorrecto.")

    if any(celda.data_type in ("f", "e") for celda in celdas):
        raise ValueError(f"Fila Excel {numero}: formula o error Excel.")

    valores = [celda.value for celda in celdas]

    if all(valor is None for valor in valores):
        return None

    return dict(zip(COLUMNAS, valores, strict=True))


def _leer_hoja(
    libro: object,
) -> list[dict[str, object]]:
    """Lee una unica hoja en modo de solo lectura."""
    hoja = libro.worksheets[0]
    filas = hoja.iter_rows(values_only=False)

    _encabezados(next(filas, None))

    resultado: list[dict[str, object]] = []

    for numero, celdas in enumerate(filas, start=2):
        if numero > MAXIMO_FILAS + 1:
            raise ValueError("Se supera el limite de 10000 filas.")

        registro = _fila(tuple(celdas), numero)

        if registro is not None:
            resultado.append(registro)

    if not resultado:
        raise ValueError("El archivo no contiene motores.")

    return resultado


def leer_motores_excel(
    contenido: bytes,
    nombre: str,
) -> list[dict[str, object]]:
    """Lee datos de motores; el dominio valida cada variable."""
    _validar_archivo(contenido, nombre)
    _validar_zip(contenido)

    try:
        libro = load_workbook(
            BytesIO(contenido),
            read_only=True,
            data_only=False,
            keep_links=False,
        )
    except Exception as error:
        raise ValueError("No se pudo abrir el XLSX de motores.") from error

    try:
        if not libro.worksheets:
            raise ValueError("Excel sin hojas.")

        return _leer_hoja(libro)

    finally:
        libro.close()
