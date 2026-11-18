"""Lee mediciones XLSX parciales sin inventar valores ausentes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from math import isfinite
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

CAMPOS = (
    "fecha_hora",
    "frontera",
    "area",
    "punto_medicion",
    "p_total_kw",
    "p_l1_kw",
    "p_l2_kw",
    "p_l3_kw",
    "i_total_a",
    "i_l1_a",
    "i_l2_a",
    "i_l3_a",
    "v_total_v",
    "v_l1_v",
    "v_l2_v",
    "v_l3_v",
    "fp_total",
)
VARIABLES = CAMPOS[4:]
ETIQUETAS = CAMPOS[1:4]
MAXIMO_BYTES = 25 * 1024 * 1024
MAXIMO_DESCOMPRIMIDO = 150 * 1024 * 1024
MAXIMO_ENTRADAS = 1_000
MAXIMO_FILAS = 10_000
MAXIMO_ADVERTENCIAS = 20


@dataclass(frozen=True, slots=True)
class MedicionesImportadas:
    """Datos útiles, cobertura por variable y problemas de importación."""

    registros: list[dict[str, object]]
    columnas: tuple[str, ...]
    cobertura: dict[str, int]
    advertencias: tuple[str, ...]
    problemas: int
    filas_omitidas: int


@dataclass(slots=True)
class _Acumulador:
    """Agrupa resultados y advertencias durante la lectura."""

    nombres: tuple[str, ...]
    registros: list[dict[str, object]] = field(default_factory=list)
    cobertura: dict[str, int] = field(init=False)
    advertencias: list[str] = field(default_factory=list)
    problemas: int = 0
    filas_omitidas: int = 0

    def __post_init__(self) -> None:
        self.cobertura = {campo: 0 for campo in self.nombres if campo in VARIABLES}

    def advertir(self, mensaje: str) -> None:
        """Cuenta todos los problemas y limita los mensajes visibles."""
        self.problemas += 1
        if len(self.advertencias) < MAXIMO_ADVERTENCIAS:
            self.advertencias.append(mensaje)

    def resultado(self) -> MedicionesImportadas:
        """Construye el resultado final si existen mediciones válidas."""
        if not self.registros:
            raise ValueError("No hay registros con fechas utilizables.")
        if not any(self.cobertura.values()):
            raise ValueError("No hay variables electricas con datos numericos validos.")
        return MedicionesImportadas(
            self.registros,
            self.nombres,
            self.cobertura,
            tuple(self.advertencias),
            self.problemas,
            self.filas_omitidas,
        )


def _validar_archivo(contenido: bytes, nombre: str) -> None:
    if not isinstance(nombre, str) or Path(nombre).suffix.lower() != ".xlsx":
        raise ValueError("Se requiere un archivo XLSX.")
    if not isinstance(contenido, bytes) or not contenido or len(contenido) > MAXIMO_BYTES:
        raise ValueError("Archivo XLSX vacio o superior a 25 MB.")
    try:
        with ZipFile(BytesIO(contenido)) as comprimido:
            entradas = comprimido.infolist()
            if len(entradas) > MAXIMO_ENTRADAS:
                raise ValueError("Demasiados archivos internos en el XLSX.")
            if sum(entrada.file_size for entrada in entradas) > MAXIMO_DESCOMPRIMIDO:
                raise ValueError("XLSX excesivo al descomprimir.")
            if comprimido.testzip() is not None:
                raise ValueError("XLSX corrupto.")
    except BadZipFile as error:
        raise ValueError("El archivo no es un XLSX valido.") from error


def _fecha(valor: object, epoca: datetime) -> datetime:
    if isinstance(valor, datetime):
        resultado = valor
    elif isinstance(valor, date):
        resultado = datetime.combine(valor, datetime.min.time())
    elif isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if not isfinite(valor):
            raise ValueError("Fecha numerica no finita.")
        try:
            resultado = from_excel(valor, epoch=epoca)
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError("Fecha numerica de Excel invalida.") from error
    elif isinstance(valor, str):
        try:
            resultado = datetime.fromisoformat(valor.strip())
        except ValueError as error:
            raise ValueError("Fecha de texto invalida; usa AAAA-MM-DD HH:MM:SS.") from error
    else:
        raise ValueError("Fecha vacia o no reconocida.")
    if not isinstance(resultado, datetime) or resultado.tzinfo is not None:
        raise ValueError("La fecha debe contener hora local sin zona horaria.")
    return resultado


def _numero(valor: object, campo: str) -> float | None:
    if valor is None or isinstance(valor, str) and not valor.strip():
        return None
    if isinstance(valor, bool):
        raise ValueError("Valor booleano no admitido.")
    if isinstance(valor, str):
        texto = valor.strip()
        if texto.startswith(("=", "@")):
            raise ValueError("Formula o expresion no permitida.")
        if texto.count(",") == 1 and "." not in texto:
            texto = texto.replace(",", ".")
        valor = texto
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Valor no numerico.") from error
    if not isfinite(numero):
        raise ValueError("Valor no finito.")
    if campo == "fp_total" and not -1 <= numero <= 1:
        raise ValueError("Factor de potencia fuera de [-1, 1].")
    if campo.startswith(("i_", "v_")) and numero < 0:
        raise ValueError("Corriente o tension negativa; revisar convencion.")
    return numero


def _encabezados(fila: tuple[object, ...] | None) -> tuple[str, ...]:
    if fila is None:
        raise ValueError("El XLSX no contiene encabezados.")
    if any(celda.data_type in ("f", "e") for celda in fila):
        raise ValueError("La cabecera contiene formulas o errores.")
    nombres = tuple(
        celda.value.strip().lower() if isinstance(celda.value, str) else "" for celda in fila
    )
    if len(set(nombres)) != len(nombres):
        raise ValueError("Hay columnas duplicadas o encabezados vacios.")
    desconocidos = set(nombres) - set(CAMPOS)
    if desconocidos:
        raise ValueError(f"Columnas desconocidas: {', '.join(sorted(desconocidos))}.")
    if "fecha_hora" not in nombres:
        raise ValueError("Falta la columna obligatoria fecha_hora.")
    if not set(nombres).intersection(VARIABLES):
        raise ValueError("Se requiere al menos una columna de variable electrica.")
    return nombres


def _leer_etiquetas(
    registro: dict[str, object],
    mapa: dict[str, object],
    numero: int,
    advertir: Callable[[str], None],
) -> None:
    """Recupera los identificadores sin inventar ubicaciones."""
    for campo in ETIQUETAS:
        celda = mapa.get(campo)
        valor = None if celda is None else celda.value
        if celda is not None and celda.data_type in ("f", "e"):
            advertir(f"Fila {numero}: {campo} contiene formula o error.")
            registro[campo] = "Sin especificar"
        else:
            registro[campo] = (
                valor.strip() if isinstance(valor, str) and valor.strip() else "Sin especificar"
            )


def _leer_variables(
    registro: dict[str, object],
    mapa: dict[str, object],
    numero: int,
    acumulador: _Acumulador,
) -> None:
    """Valida cada variable de forma independiente y conserva sus ceros."""
    for campo in VARIABLES:
        celda = mapa.get(campo)
        valor = None if celda is None else celda.value
        if celda is not None and celda.data_type in ("f", "e"):
            acumulador.advertir(f"Fila {numero}: {campo} contiene formula o error.")
            registro[campo] = None
            continue
        try:
            registro[campo] = _numero(valor, campo)
        except ValueError as error:
            acumulador.advertir(f"Fila {numero}: {campo}: {error}")
            registro[campo] = None
        if registro[campo] is not None and campo in acumulador.cobertura:
            acumulador.cobertura[campo] += 1


def _procesar_fila(
    celdas: tuple[object, ...],
    numero: int,
    epoca: datetime,
    acumulador: _Acumulador,
) -> None:
    """Procesa una fila y registra sus incidencias sin detener otras filas."""
    if len(celdas) > len(acumulador.nombres):
        raise ValueError(f"Fila {numero}: aparecen columnas adicionales.")
    if all(celda.value is None for celda in celdas):
        return
    mapa = dict(zip(acumulador.nombres, celdas, strict=False))
    celda_fecha = mapa["fecha_hora"]
    if celda_fecha.data_type in ("f", "e"):
        acumulador.advertir(f"Fila {numero}: fecha con formula o error; fila omitida.")
        acumulador.filas_omitidas += 1
        return
    try:
        fecha = _fecha(celda_fecha.value, epoca)
    except ValueError as error:
        acumulador.advertir(f"Fila {numero}: {error} Fila omitida.")
        acumulador.filas_omitidas += 1
        return
    registro: dict[str, object] = {"fecha_hora": fecha}
    _leer_etiquetas(registro, mapa, numero, acumulador.advertir)
    _leer_variables(registro, mapa, numero, acumulador)
    acumulador.registros.append(registro)


def leer_mediciones_detalladas(contenido: bytes, nombre: str) -> MedicionesImportadas:
    """Admite subconjuntos del contrato de 17 columnas y registra problemas."""
    _validar_archivo(contenido, nombre)
    try:
        libro = load_workbook(BytesIO(contenido), read_only=True, data_only=False, keep_links=False)
    except Exception as error:
        raise ValueError("No se pudo abrir el archivo de mediciones.") from error
    try:
        if not libro.worksheets:
            raise ValueError("El archivo XLSX no tiene hojas.")
        filas = libro.worksheets[0].iter_rows(values_only=False)
        acumulador = _Acumulador(_encabezados(next(filas, None)))
        for numero, celdas in enumerate(filas, start=2):
            if numero > MAXIMO_FILAS + 1:
                raise ValueError("El XLSX supera las 10000 filas permitidas.")
            _procesar_fila(tuple(celdas), numero, libro.epoch, acumulador)
        return acumulador.resultado()
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("Error al leer los registros de mediciones.") from error
    finally:
        libro.close()
