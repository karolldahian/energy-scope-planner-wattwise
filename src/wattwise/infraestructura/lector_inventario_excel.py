"""Lee inventarios XLSX con limites y validacion estructural."""

from io import BytesIO
from math import isfinite
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook

COLUMNAS_OBLIGATORIAS = frozenset(
    {
        "equipo",
        "tipo_carga",
        "cantidad",
        "potencia_unitaria_kw",
    }
)

COLUMNAS_PERMITIDAS = COLUMNAS_OBLIGATORIAS | frozenset(
    {
        "frontera",
        "area",
        "ubicacion_detalle",
    }
)

MAXIMO_BYTES = 25 * 1024 * 1024
MAXIMO_DESCOMPRIMIDO = 250 * 1024 * 1024
MAXIMO_ENTRADAS_ZIP = 1_000
MAXIMO_FILAS = 100_000
MAXIMO_COLUMNAS = 150


def _validar_archivo(
    contenido: bytes,
    nombre_archivo: str,
) -> None:
    """Comprueba formato, tipo de entrada y tamano."""
    if not isinstance(contenido, bytes):
        raise ValueError("El contenido debe proporcionarse en bytes.")

    if not isinstance(nombre_archivo, str):
        raise ValueError("El nombre del archivo debe ser texto.")

    if not nombre_archivo.lower().endswith(".xlsx"):
        raise ValueError("Solo se admiten archivos .xlsx.")

    if not contenido or len(contenido) > MAXIMO_BYTES:
        raise ValueError("Archivo vacio o superior a 25 MB.")


def _validar_contenedor_zip(contenido: bytes) -> None:
    """Inspecciona el contenedor antes de abrir Excel."""
    try:
        with ZipFile(BytesIO(contenido)) as archivo:
            entradas = archivo.infolist()

            if len(entradas) > MAXIMO_ENTRADAS_ZIP:
                raise ValueError("Demasiadas entradas internas en XLSX.")

            total = 0

            for entrada in entradas:
                total += entrada.file_size

                if total > MAXIMO_DESCOMPRIMIDO:
                    raise ValueError("XLSX supera el limite descomprimido.")

            if archivo.testzip() is not None:
                raise ValueError("XLSX contiene datos ZIP corruptos.")

    except BadZipFile as error:
        raise ValueError("El archivo no es un XLSX valido.") from error


def _validar_encabezados(
    celdas: tuple[object, ...],
) -> list[str]:
    """Normaliza encabezados y comprueba las columnas."""
    if not celdas:
        raise ValueError("La hoja no contiene encabezados.")

    if len(celdas) > MAXIMO_COLUMNAS:
        raise ValueError("Demasiadas columnas.")

    encabezados: list[str] = []

    for celda in celdas:
        if getattr(celda, "data_type", None) == "f":
            raise ValueError("No se admiten formulas en encabezados.")

        valor = getattr(celda, "value", None)

        if valor is None:
            encabezados.append("")
        elif isinstance(valor, str):
            encabezados.append(valor.strip().lower())
        else:
            raise ValueError("Los encabezados deben ser texto.")

    presentes = [nombre for nombre in encabezados if nombre]

    if len(presentes) != len(set(presentes)):
        raise ValueError("Existen encabezados duplicados.")

    faltantes = COLUMNAS_OBLIGATORIAS - set(presentes)

    if faltantes:
        raise ValueError("Faltan columnas: " + ", ".join(sorted(faltantes)))

    desconocidas = set(presentes) - COLUMNAS_PERMITIDAS

    if desconocidas:
        raise ValueError("Columnas no admitidas: " + ", ".join(sorted(desconocidas)))

    return encabezados


def _extraer_valores(
    celdas: tuple[object, ...],
    numero_fila: int,
) -> list[object]:
    """Rechaza formulas, errores Excel y numeros no finitos."""
    if len(celdas) > MAXIMO_COLUMNAS:
        raise ValueError("Se supera el limite de columnas.")

    valores: list[object] = []

    for celda in celdas:
        if getattr(celda, "data_type", None) in ("f", "e"):
            raise ValueError(f"Formula o error Excel en fila {numero_fila}.")

        valor = getattr(celda, "value", None)

        if isinstance(valor, float) and not isfinite(valor):
            raise ValueError(f"Numero no finito en fila {numero_fila}.")

        valores.append(valor)

    return valores


def _leer_registros(
    filas: object,
    encabezados: list[str],
) -> list[dict[str, object]]:
    """Construye registros preservando los datos originales."""
    resultado: list[dict[str, object]] = []

    for numero_fila, celdas in enumerate(filas, start=2):
        if numero_fila > MAXIMO_FILAS + 1:
            raise ValueError("Se supera el limite de filas.")

        valores = _extraer_valores(
            tuple(celdas),
            numero_fila,
        )

        if not any(valor is not None for valor in valores):
            continue

        fila = {
            nombre: valores[indice] if indice < len(valores) else None
            for indice, nombre in enumerate(encabezados)
            if nombre
        }

        resultado.append(fila)

    if not resultado:
        raise ValueError("El inventario no contiene datos.")

    return resultado


def leer_inventario_excel(
    contenido: bytes,
    nombre_archivo: str,
) -> list[dict[str, object]]:
    """Lee la primera hoja de un inventario Excel validado.

    No ejecuta formulas ni interpreta resultados cacheados.

    Rechaza archivos con columnas incompatibles y datos
    que no pueden utilizarse de forma segura.

    La validacion electrica se realiza posteriormente
    mediante el dominio de inventarios.
    """
    _validar_archivo(contenido, nombre_archivo)
    _validar_contenedor_zip(contenido)

    try:
        libro = load_workbook(
            BytesIO(contenido),
            read_only=True,
            data_only=False,
            keep_links=False,
        )
    except Exception as error:
        raise ValueError("No se pudo abrir el archivo Excel.") from error

    try:
        if not libro.worksheets:
            raise ValueError("El libro no contiene hojas.")

        hoja = libro.worksheets[0]
        filas = hoja.iter_rows(values_only=False)

        encabezados_originales = next(filas, None)

        if encabezados_originales is None:
            raise ValueError("La hoja no contiene encabezados.")

        encabezados = _validar_encabezados(tuple(encabezados_originales))

        return _leer_registros(
            filas,
            encabezados,
        )

    finally:
        libro.close()
