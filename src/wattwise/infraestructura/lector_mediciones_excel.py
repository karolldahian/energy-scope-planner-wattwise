"""Importa mediciones XLSX sin evaluar formulas ni modificar datos fuente."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook

COLUMNAS = (
    "fecha_hora",
    "tension_v",
    "corriente_a",
    "factor_potencia",
    "potencia_activa_kw",
)
MAXIMO_BYTES = 25 * 1024 * 1024
MAXIMO_DESCOMPRIMIDO = 150 * 1024 * 1024
MAXIMO_ENTRADAS_ZIP = 1_000
MAXIMO_FILAS = 10_000


def _validar_contenedor(contenido: bytes, nombre: str) -> None:
    """Rechaza archivos con formato o tamano externo no permitido."""
    if not isinstance(nombre, str) or not nombre.lower().endswith(".xlsx"):
        raise ValueError("Solo se admiten archivos .xlsx.")
    if not isinstance(contenido, bytes) or not contenido or len(contenido) > MAXIMO_BYTES:
        raise ValueError("Archivo XLSX vacio o superior al limite de 25 MB.")
    try:
        with ZipFile(BytesIO(contenido)) as archivo:
            entradas = archivo.infolist()
            if len(entradas) > MAXIMO_ENTRADAS_ZIP:
                raise ValueError("Demasiadas entradas dentro del XLSX.")
            if sum(entrada.file_size for entrada in entradas) > MAXIMO_DESCOMPRIMIDO:
                raise ValueError("XLSX supera el limite descomprimido.")
            if archivo.testzip() is not None:
                raise ValueError("XLSX contiene entradas ZIP corruptas.")
    except BadZipFile as error:
        raise ValueError("El archivo no es un XLSX valido.") from error


def _validar_encabezados(celdas: tuple[object, ...] | None) -> None:
    """Comprueba nombres, orden y ausencia de formulas en cabecera."""
    if celdas is None or len(celdas) != len(COLUMNAS):
        raise ValueError("Las columnas no coinciden con la plantilla de mediciones.")
    if any(celda.data_type in ("f", "e") for celda in celdas):
        raise ValueError("No se admiten formulas ni errores en encabezados.")
    nombres = tuple(
        celda.value.strip().lower() if isinstance(celda.value, str) else celda.value
        for celda in celdas
    )
    if nombres != COLUMNAS:
        raise ValueError("Las columnas no coinciden con la plantilla de mediciones.")


def _convertir_fecha(valor: object, numero: int) -> str:
    """Conserva fechas textuales y convierte fechas nativas de Excel."""
    if isinstance(valor, datetime):
        if valor.tzinfo is not None:
            raise ValueError(f"Fila Excel {numero}: fecha con zona horaria no permitida.")
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(valor, str):
        return valor
    raise ValueError(f"Fila Excel {numero}: fecha_hora debe ser fecha o texto.")


def _leer_fila(celdas: tuple[object, ...], numero: int) -> dict[str, object] | None:
    """Devuelve campos crudos; el dominio valida sus rangos."""
    if len(celdas) != len(COLUMNAS):
        raise ValueError(f"Fila Excel {numero}: numero de columnas incorrecto.")
    if any(celda.data_type in ("f", "e") for celda in celdas):
        raise ValueError(f"Fila Excel {numero}: formula o error no admitido.")
    valores = [celda.value for celda in celdas]
    if all(valor is None for valor in valores):
        return None
    valores[0] = _convertir_fecha(valores[0], numero)
    return dict(zip(COLUMNAS, valores, strict=True))


def leer_mediciones_excel(contenido: bytes, nombre: str) -> list[dict[str, object]]:
    """Lee la primera hoja XLSX de mediciones bajo limites estrictos."""
    _validar_contenedor(contenido, nombre)
    try:
        libro = load_workbook(
            BytesIO(contenido),
            read_only=True,
            data_only=False,
            keep_links=False,
        )
    except Exception as error:
        raise ValueError("No se pudo abrir el XLSX de mediciones.") from error

    try:
        if not libro.worksheets:
            raise ValueError("XLSX sin hojas.")
        filas = libro.worksheets[0].iter_rows(values_only=False)
        _validar_encabezados(next(filas, None))
        resultado: list[dict[str, object]] = []
        for numero, celdas in enumerate(filas, start=2):
            if numero > MAXIMO_FILAS + 1:
                raise ValueError("Se superan las 10000 filas permitidas.")
            registro = _leer_fila(tuple(celdas), numero)
            if registro is not None:
                resultado.append(registro)
        if not resultado:
            raise ValueError("El XLSX no contiene mediciones.")
        return resultado
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("No se pudo leer la hoja de mediciones.") from error
    finally:
        libro.close()
