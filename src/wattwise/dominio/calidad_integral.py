"""Auditoría trazable de Excel originales sin completar ni modificar datos."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from math import isfinite
from statistics import median
from zipfile import BadZipFile

from openpyxl import load_workbook

from wattwise.infraestructura.plantillas_completas import ESQUEMAS, OBLIGATORIAS

MAXIMO_LIBRO_BYTES = 25 * 1024 * 1024
MAXIMO_HOJAS = 30
MAXIMO_FILAS_POR_HOJA = 100_000
MAXIMO_COLUMNAS = 60

FilaFuente = tuple[int, dict[str, object]]
MIN_MUESTRAS_CERO = 3
MIN_MUESTRAS_CONSTANTE = 5
MIN_DURACION_CONSTANTE_MIN = 15.0
MAX_FACTOR_CONTINUIDAD = 1.5
CARACTERES_INVISIBLES = "\u200b\u200c\u200d\ufeff\u2060"
MARCADORES_SIN_DATO = {"-", "--", "N/A", "NA", "ERROR", "#N/A", "NULL"}
PATRON_CERO_TEXTO = re.compile(r"[+-]?0+(?:[.,]0+)?\Z")


@dataclass(frozen=True, slots=True)
class HallazgoCalidad:
    """Ubicación verificable de un hallazgo en la hoja original."""

    hoja: str
    filas: tuple[int, ...] = ()
    columna: str = ""
    punto: str = ""
    variable: str = ""
    valor: str = ""
    motivo: str = ""
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None
    duracion_min: float | None = None
    intervalo_referencia_min: float | None = None
    muestras_estimadas: int | None = None
    cantidad_afectada: int = 1


@dataclass(frozen=True, slots=True)
class CalidadColumna:
    """Cobertura por columna con ubicación de vacíos e inválidos."""

    nombre: str
    obligatoria: bool
    validos: int
    faltantes: int
    invalidos: int
    cobertura_pct: float
    ubicaciones_vacias: tuple[HallazgoCalidad, ...] = ()
    ubicaciones_invalidas: tuple[HallazgoCalidad, ...] = ()
    ceros: int = 0
    ceros_validos: int = 0
    negativos: int = 0
    nulos: int = 0
    blancos: int = 0
    marcadores: int = 0
    rachas_ceros: int = 0
    rachas_constantes: int = 0
    ubicaciones_ceros: tuple[HallazgoCalidad, ...] = ()
    ubicaciones_negativos: tuple[HallazgoCalidad, ...] = ()
    ubicaciones_blancos: tuple[HallazgoCalidad, ...] = ()
    ubicaciones_marcadores: tuple[HallazgoCalidad, ...] = ()
    ubicaciones_rachas_ceros: tuple[HallazgoCalidad, ...] = ()
    ubicaciones_rachas_constantes: tuple[HallazgoCalidad, ...] = ()


@dataclass(frozen=True, slots=True)
class CalidadSerie:
    """Continuidad de una variable de un punto sin mezclar hojas."""

    hoja: str
    punto: str
    variable: str
    muestras: int
    fecha_inicial: datetime | None
    fecha_final: datetime | None
    intervalo_mediano_min: float | None
    huecos_prolongados: int
    fechas_duplicadas: int
    ubicaciones_huecos: tuple[HallazgoCalidad, ...] = ()
    ubicaciones_fechas_duplicadas: tuple[HallazgoCalidad, ...] = ()


@dataclass(frozen=True, slots=True)
class CalidadHoja:
    """Indicadores y localizaciones de todas las filas auditadas."""

    nombre: str
    registros: int
    duplicados_exactos: int
    posibles_repetidos: int
    fechas_invalidas: int
    fechas_duplicadas: int
    columnas_ausentes: tuple[str, ...]
    columnas: tuple[CalidadColumna, ...]
    series: tuple[CalidadSerie, ...]
    ubicaciones_duplicados: tuple[HallazgoCalidad, ...] = ()
    ubicaciones_posibles: tuple[HallazgoCalidad, ...] = ()
    ubicaciones_fechas_invalidas: tuple[HallazgoCalidad, ...] = ()
    ubicaciones_fechas_duplicadas: tuple[HallazgoCalidad, ...] = ()
    filas_completamente_vacias: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class InformeCalidad:
    """Auditoría del libro; hash identifica exactamente el original."""

    tipo: str
    nombre: str
    sha256: str
    hojas: tuple[CalidadHoja, ...]
    hojas_omitidas: tuple[str, ...]


def _limpio(valor: str) -> str:
    """Elimina espacios de Unicode que no siempre reconoce strip()."""
    return valor.translate(str.maketrans("", "", CARACTERES_INVISIBLES)).strip()


def _vacio(valor: object) -> bool:
    """None y texto compuesto solo por espacios son vacíos; cero no lo es."""
    return valor is None or (isinstance(valor, str) and not _limpio(valor))


def _marcador(valor: object) -> bool:
    """Detecta textos que aparentan representar falta de información."""
    return isinstance(valor, str) and _limpio(valor).upper() in MARCADORES_SIN_DATO


def _cero(valor: object) -> bool:
    """Reconoce cero numérico o cero textual, sin equiparar vacío con cero."""
    if isinstance(valor, bool):
        return False
    if isinstance(valor, (int, float)):
        return isfinite(valor) and valor == 0
    return isinstance(valor, str) and bool(PATRON_CERO_TEXTO.fullmatch(valor.strip()))


def _negativo(valor: object) -> bool:
    """Detecta números finitos negativos, sin concluir anomalías eléctricas."""
    return (
        not isinstance(valor, bool)
        and isinstance(valor, (int, float))
        and isfinite(valor)
        and valor < 0
    )


def _campo_numerico(campo: str) -> bool:
    return campo in {
        "cantidad",
        "numero_fases",
        "horas_operacion_mes",
        "fp_total",
    } or campo.endswith(("_kw", "_hp", "_a", "_v"))


def _fecha_formatos(texto: str) -> datetime | None:
    """Acepta tres formatos locales explícitos."""
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def _fecha(valor: object) -> datetime | None:
    """No asume husos horarios ni números de serie Excel."""
    if isinstance(valor, datetime):
        return valor if valor.tzinfo is None else None
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    if not isinstance(valor, str) or not valor.strip():
        return None
    texto = valor.strip()
    try:
        resultado = datetime.fromisoformat(texto)
    except ValueError:
        return _fecha_formatos(texto)
    return resultado if resultado.tzinfo is None else None


def _regla_numerica_especial(valor: float, campo: str) -> bool | None:
    """Reglas estructurales; no emiten juicio normativo eléctrico."""
    if campo == "cantidad":
        return int(valor) == valor and valor >= 1
    if campo == "numero_fases":
        return int(valor) == valor and valor in (1, 3)
    if campo == "fp_total":
        return -1 <= valor <= 1
    if campo == "horas_operacion_mes":
        return 0 <= valor <= 744
    return None


def _numerico(valor: object, campo: str) -> bool:
    """Rechaza tipos incorrectos y no finitos."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return False
    if not isfinite(valor):
        return False
    especial = _regla_numerica_especial(float(valor), campo)
    if especial is not None:
        return especial
    return (campo.startswith("p_") and campo.endswith("_kw")) or valor >= 0


def _estado(valor: object, campo: str) -> str:
    """Distingue ausente, válido e inválido sin confundirlos."""
    if _vacio(valor):
        return "faltante"
    if _marcador(valor):
        return "invalido"
    if campo == "fecha_hora":
        return "valido" if _fecha(valor) is not None else "invalido"
    numerico = _campo_numerico(campo)
    if numerico:
        return "valido" if _numerico(valor, campo) else "invalido"
    return "valido" if isinstance(valor, str) and bool(valor.strip()) else "invalido"


def _clave_valor(valor: object) -> str:
    """Normaliza solo para comparación, sin cambiar el original."""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, str):
        return valor.strip()
    return repr(valor)


def _punto(fila: dict[str, object]) -> str:
    """No mezcla instrumentos de fronteras/áreas/puntos distintos."""
    return " | ".join(
        str(fila.get(campo) if not _vacio(fila.get(campo)) else "Sin especificar")
        for campo in ("frontera", "area", "punto_medicion")
    )


def _hallazgo(
    hoja: str,
    filas: tuple[int, ...],
    *,
    columna: str = "",
    punto: str = "",
    variable: str = "",
    valor: str = "",
    motivo: str = "",
) -> HallazgoCalidad:
    return HallazgoCalidad(
        hoja=hoja,
        filas=filas,
        columna=columna,
        punto=punto,
        variable=variable,
        valor=valor,
        motivo=motivo,
    )


def _repetidas_serie(
    hoja: str,
    punto: str,
    variable: str,
    por_fecha: dict[datetime, list[int]],
) -> tuple[HallazgoCalidad, ...]:
    """Conserva la pareja de filas de cada fecha adicional repetida."""
    hallazgos = []
    for instante, filas in sorted(por_fecha.items()):
        for otra in filas[1:]:
            hallazgos.append(
                _hallazgo(
                    hoja,
                    (filas[0], otra),
                    columna="fecha_hora",
                    punto=punto,
                    variable=variable,
                    valor=instante.isoformat(),
                    motivo="Fecha y hora repetidas en la misma serie",
                )
            )
    return tuple(hallazgos)


def _huecos_serie(
    hoja: str,
    punto: str,
    variable: str,
    por_fecha: dict[datetime, list[int]],
    distintas: list[datetime],
    paso: float | None,
) -> tuple[HallazgoCalidad, ...]:
    """Ubica huecos reales entre muestras, con número ausente aproximado."""
    if paso is None or paso <= 0:
        return ()
    huecos = []
    for inicio, fin in zip(distintas, distintas[1:], strict=False):
        duracion = (fin - inicio).total_seconds() / 60
        if duracion <= 3 * paso:
            continue
        huecos.append(
            HallazgoCalidad(
                hoja=hoja,
                filas=(por_fecha[inicio][-1], por_fecha[fin][0]),
                columna="fecha_hora",
                punto=punto,
                variable=variable,
                motivo="Intervalo mayor que tres veces la mediana",
                fecha_inicio=inicio,
                fecha_fin=fin,
                duracion_min=duracion,
                intervalo_referencia_min=paso,
                muestras_estimadas=max(0, round(duracion / paso) - 1),
            )
        )
    return tuple(huecos)


def _serie(
    hoja: str,
    punto: str,
    variable: str,
    fechas: list[tuple[datetime, int]],
) -> CalidadSerie:
    """Calcula mediana y conserva localizaciones de huecos y repeticiones."""
    por_fecha: dict[datetime, list[int]] = defaultdict(list)
    for instante, fila_excel in fechas:
        por_fecha[instante].append(fila_excel)
    distintas = sorted(por_fecha)
    deltas = [
        (fin - inicio).total_seconds() / 60
        for inicio, fin in zip(distintas, distintas[1:], strict=False)
    ]
    paso = median(deltas) if deltas else None
    huecos = _huecos_serie(hoja, punto, variable, por_fecha, distintas, paso)
    repetidas = _repetidas_serie(hoja, punto, variable, por_fecha)
    return CalidadSerie(
        hoja=hoja,
        punto=punto,
        variable=variable,
        muestras=len(fechas),
        fecha_inicial=distintas[0] if distintas else None,
        fecha_final=distintas[-1] if distintas else None,
        intervalo_mediano_min=paso,
        huecos_prolongados=len(huecos),
        fechas_duplicadas=len(repetidas),
        ubicaciones_huecos=huecos,
        ubicaciones_fechas_duplicadas=repetidas,
    )


def _campos_compatibles(tipo: str, cabecera: tuple[object, ...]) -> bool:
    """Ignora hojas auxiliares sin encabezados reconocibles."""
    encontrados = {str(c).strip() for c in cabecera if c is not None}
    if tipo == "mediciones":
        return "fecha_hora" in encontrados
    return len(encontrados.intersection(ESQUEMAS[tipo])) >= 2


def _serie_numerica(
    campo: str,
    filas: list[FilaFuente],
) -> dict[str, list[tuple[datetime, int, float | None]]]:
    """Preserva filas sin lectura válida para cortar las rachas temporales."""
    puntos: dict[str, list[tuple[datetime, int, float | None]]] = defaultdict(list)
    for numero, fila in filas:
        fecha = _fecha(fila.get("fecha_hora"))
        if fecha is None:
            continue
        original = fila.get(campo)
        valor = (
            float(original)
            if _estado(original, campo) == "valido"
            and isinstance(original, (int, float))
            and not isinstance(original, bool)
            else None
        )
        puntos[_punto(fila)].append((fecha, numero, valor))
    return puntos


def _registrar_racha(
    destino_ceros: list[HallazgoCalidad],
    destino_constantes: list[HallazgoCalidad],
    hoja: str,
    punto: str,
    campo: str,
    muestras: list[tuple[datetime, int, float]],
    paso: float,
) -> None:
    """Registra una racha con sus fechas y filas extremas originales."""
    if not muestras:
        return
    valor = muestras[0][2]
    es_cero = valor == 0
    minimo = MIN_MUESTRAS_CERO if es_cero else MIN_MUESTRAS_CONSTANTE
    if len(muestras) < minimo:
        return
    duracion = (muestras[-1][0] - muestras[0][0]).total_seconds() / 60
    if not es_cero and duracion < MIN_DURACION_CONSTANTE_MIN:
        return
    destino = destino_ceros if es_cero else destino_constantes
    inicio, primera, _ = muestras[0]
    final, ultima, _ = muestras[-1]
    destino.append(
        HallazgoCalidad(
            hoja=hoja,
            filas=(primera, ultima),
            columna=campo,
            punto=punto,
            variable=campo,
            valor=str(valor),
            motivo=("Racha de ceros" if es_cero else "Valor constante no nulo"),
            fecha_inicio=inicio,
            fecha_fin=final,
            duracion_min=(final - inicio).total_seconds() / 60,
            intervalo_referencia_min=paso,
            cantidad_afectada=len(muestras),
        )
    )


def _rachas_columna(
    hoja: str,
    campo: str,
    filas: list[FilaFuente],
) -> tuple[tuple[HallazgoCalidad, ...], tuple[HallazgoCalidad, ...]]:
    """Detecta secuencias continuas separadas por punto y cadencia real."""
    ceros: list[HallazgoCalidad] = []
    constantes: list[HallazgoCalidad] = []
    for punto, registros in sorted(_serie_numerica(campo, filas).items()):
        ordenados = sorted(registros, key=lambda item: (item[0], item[1]))
        instantes = sorted({item[0] for item in ordenados})
        intervalos = [
            (fin - inicio).total_seconds() / 60
            for inicio, fin in zip(instantes, instantes[1:], strict=False)
        ]
        paso = median(intervalos) if intervalos else None
        if paso is None or paso <= 0:
            continue
        racha: list[tuple[datetime, int, float]] = []
        for instante, fila, valor in ordenados:
            anterior = racha[-1] if racha else None
            delta = (instante - anterior[0]).total_seconds() / 60 if anterior else 0
            consecutiva = (
                anterior is not None
                and valor is not None
                and valor == anterior[2]
                and 0 < delta <= MAX_FACTOR_CONTINUIDAD * paso
            )
            if not consecutiva:
                _registrar_racha(ceros, constantes, hoja, punto, campo, racha, paso)
                racha = []
            if valor is not None:
                racha.append((instante, fila, valor))
        _registrar_racha(ceros, constantes, hoja, punto, campo, racha, paso)
    return tuple(ceros), tuple(constantes)


def _guardar_caso(
    hallazgos: dict[str, list[HallazgoCalidad]],
    categoria: str,
    hoja: str,
    fila_excel: int,
    campo: str,
    punto: str,
    valor: object,
    motivo: str,
) -> None:
    """Centraliza la trazabilidad a la celda original."""
    hallazgos[categoria].append(
        _hallazgo(
            hoja,
            (fila_excel,),
            columna=campo,
            punto=punto,
            valor=repr(valor),
            motivo=motivo,
        )
    )


def _revisar_celda(
    hallazgos: dict[str, list[HallazgoCalidad]],
    hoja: str,
    campo: str,
    numero: int,
    valor: object,
    punto: str,
    estado: str,
) -> None:
    """Detecta ceros, negativos y marcas sin interpretar su causa."""
    if estado != "valido":
        categoria = "vacios" if estado == "faltante" else "invalidos"
        _guardar_caso(hallazgos, categoria, hoja, numero, campo, punto, valor, estado)
    if _campo_numerico(campo) and _cero(valor):
        motivo = "Cero válido" if estado == "valido" else "Cero escrito como texto o inválido"
        _guardar_caso(hallazgos, "ceros", hoja, numero, campo, punto, valor, motivo)
    if _campo_numerico(campo) and _negativo(valor):
        _guardar_caso(
            hallazgos,
            "negativos",
            hoja,
            numero,
            campo,
            punto,
            valor,
            "Valor negativo: revisar contexto",
        )
    if isinstance(valor, str) and not _limpio(valor):
        _guardar_caso(
            hallazgos,
            "blancos",
            hoja,
            numero,
            campo,
            punto,
            valor,
            "Espacio o carácter invisible",
        )
    if _marcador(valor):
        _guardar_caso(
            hallazgos,
            "marcadores",
            hoja,
            numero,
            campo,
            punto,
            valor,
            "Marcador textual de dato ausente",
        )


def _resumen_columna(
    hoja: str,
    campo: str,
    obligatoria: bool,
    filas: list[FilaFuente],
    presente: bool,
    tipo: str,
) -> CalidadColumna:
    """Cuenta ceros sin confundirlos con vacíos o duplicar barras visuales."""
    total = len(filas)
    if not presente:
        ausencia = (
            (
                HallazgoCalidad(
                    hoja=hoja,
                    columna=campo,
                    motivo=f"Columna inexistente: afecta {total} filas",
                    cantidad_afectada=total,
                ),
            )
            if total
            else ()
        )
        return CalidadColumna(
            nombre=campo,
            obligatoria=obligatoria,
            validos=0,
            faltantes=total,
            invalidos=0,
            cobertura_pct=0.0,
            ubicaciones_vacias=ausencia,
            nulos=total,
        )

    hallazgos: dict[str, list[HallazgoCalidad]] = defaultdict(list)
    validos = 0
    ceros_validos = 0
    nulos = 0
    for numero, fila in filas:
        valor = fila.get(campo)
        estado = _estado(valor, campo)
        validos += estado == "valido"
        nulos += valor is None
        ceros_validos += estado == "valido" and _campo_numerico(campo) and _cero(valor)
        punto = _punto(fila) if tipo == "mediciones" else ""
        _revisar_celda(hallazgos, hoja, campo, numero, valor, punto, estado)

    rachas_ceros: tuple[HallazgoCalidad, ...] = ()
    rachas_constantes: tuple[HallazgoCalidad, ...] = ()
    if tipo == "mediciones" and _campo_numerico(campo):
        rachas_ceros, rachas_constantes = _rachas_columna(hoja, campo, filas)
    faltantes = tuple(hallazgos["vacios"])
    invalidos = tuple(hallazgos["invalidos"])
    return CalidadColumna(
        nombre=campo,
        obligatoria=obligatoria,
        validos=validos,
        faltantes=len(faltantes),
        invalidos=len(invalidos),
        cobertura_pct=100 * validos / total if total else 0.0,
        ubicaciones_vacias=faltantes,
        ubicaciones_invalidas=invalidos,
        ceros=len(hallazgos["ceros"]),
        ceros_validos=ceros_validos,
        negativos=len(hallazgos["negativos"]),
        nulos=nulos,
        blancos=len(hallazgos["blancos"]),
        marcadores=len(hallazgos["marcadores"]),
        rachas_ceros=len(rachas_ceros),
        rachas_constantes=len(rachas_constantes),
        ubicaciones_ceros=tuple(hallazgos["ceros"]),
        ubicaciones_negativos=tuple(hallazgos["negativos"]),
        ubicaciones_blancos=tuple(hallazgos["blancos"]),
        ubicaciones_marcadores=tuple(hallazgos["marcadores"]),
        ubicaciones_rachas_ceros=rachas_ceros,
        ubicaciones_rachas_constantes=rachas_constantes,
    )


def _resumen_columnas(
    tipo: str,
    hoja: str,
    filas: list[FilaFuente],
    presentes: set[str],
) -> tuple[CalidadColumna, ...]:
    return tuple(
        _resumen_columna(
            hoja,
            campo,
            campo in OBLIGATORIAS[tipo],
            filas,
            campo in presentes,
            tipo,
        )
        for campo in ESQUEMAS[tipo]
    )


def _datos_temporales(
    hoja: str,
    filas: list[FilaFuente],
) -> tuple[tuple[CalidadSerie, ...], tuple[HallazgoCalidad, ...], tuple[HallazgoCalidad, ...]]:
    """Relaciona fechas y filas originales por punto y variable."""
    series: dict[tuple[str, str], list[tuple[datetime, int]]] = defaultdict(list)
    instantes: dict[str, dict[datetime, list[int]]] = defaultdict(lambda: defaultdict(list))
    invalidas: list[HallazgoCalidad] = []

    for numero, fila in filas:
        fecha = _fecha(fila.get("fecha_hora"))
        if fecha is None:
            invalidas.append(
                _hallazgo(
                    hoja,
                    (numero,),
                    columna="fecha_hora",
                    punto=_punto(fila),
                    valor=_clave_valor(fila.get("fecha_hora")),
                    motivo="Fecha ausente o formato no reconocido",
                )
            )
            continue
        punto = _punto(fila)
        instantes[punto][fecha].append(numero)
        for campo in ESQUEMAS["mediciones"][4:]:
            if _estado(fila.get(campo), campo) == "valido":
                series[(punto, campo)].append((fecha, numero))

    duplicadas: list[HallazgoCalidad] = []
    for punto, por_fecha in sorted(instantes.items()):
        for fecha, numeros in sorted(por_fecha.items()):
            for numero in numeros[1:]:
                duplicadas.append(
                    _hallazgo(
                        hoja,
                        (numeros[0], numero),
                        columna="fecha_hora",
                        punto=punto,
                        valor=fecha.isoformat(),
                        motivo="Mismo instante en el mismo punto de medición",
                    )
                )
    resumenes = tuple(
        _serie(hoja, punto, campo, fechas) for (punto, campo), fechas in sorted(series.items())
    )
    return resumenes, tuple(invalidas), tuple(duplicadas)


def _repetidos(
    tipo: str,
    hoja: str,
    filas: list[FilaFuente],
) -> tuple[tuple[HallazgoCalidad, ...], tuple[HallazgoCalidad, ...]]:
    """Localiza cada fila adicional repetida y su primera coincidencia."""
    campos = ESQUEMAS[tipo]
    primeros: dict[tuple[str, ...], int] = {}
    exactos: list[HallazgoCalidad] = []
    for numero, fila in filas:
        clave = tuple(_clave_valor(fila.get(campo)) for campo in campos)
        if clave not in primeros:
            primeros[clave] = numero
            continue
        exactos.append(
            _hallazgo(
                hoja,
                (primeros[clave], numero),
                punto=_punto(fila) if tipo == "mediciones" else "",
                motivo="Coincidencia de todos los campos oficiales",
            )
        )

    if tipo == "mediciones":
        return tuple(exactos), ()

    claves = ("area", "equipo") if tipo == "motores" else ("area", "equipo", "ubicacion_detalle")
    primeras_posibles: dict[tuple[str, ...], int] = {}
    posibles: list[HallazgoCalidad] = []
    for numero, fila in filas:
        clave = tuple(_clave_valor(fila.get(campo)) for campo in claves)
        if clave not in primeras_posibles:
            primeras_posibles[clave] = numero
            continue
        posibles.append(
            _hallazgo(
                hoja,
                (primeras_posibles[clave], numero),
                columna=", ".join(claves),
                valor=" | ".join(clave),
                motivo="Coincidencia de campos de identificación; revisar, no eliminar",
            )
        )
    return tuple(exactos), tuple(posibles)


def _validar_cabecera(cabecera: tuple[object, ...] | None) -> list[str]:
    """Rechaza hojas anchas y encabezados de columna duplicados."""
    if cabecera is None:
        raise ValueError("La hoja de datos no tiene encabezados.")
    if len(cabecera) > MAXIMO_COLUMNAS:
        raise ValueError("La hoja excede el límite de 60 columnas.")
    nombres = [str(valor).strip() if valor is not None else "" for valor in cabecera]
    reconocibles = [nombre for nombre in nombres if nombre]
    if len(reconocibles) != len(set(reconocibles)):
        raise ValueError("La hoja contiene nombres de columna duplicados.")
    return nombres


def _leer_filas_hoja(
    hoja: object,
) -> tuple[list[str], list[FilaFuente], tuple[int, ...]]:
    """Conserva la fila Excel real incluso tras filas vacías intermedias."""
    iterador = hoja.iter_rows(values_only=True)
    nombres = _validar_cabecera(next(iterador, None))
    filas: list[FilaFuente] = []
    vacias_internas: list[int] = []
    pendientes: list[int] = []
    for fila_excel, valores in enumerate(iterador, start=2):
        if fila_excel - 1 > MAXIMO_FILAS_POR_HOJA:
            raise ValueError("La hoja supera el límite de 100.000 registros.")
        if all(_vacio(valor) for valor in valores):
            pendientes.append(fila_excel)
            continue
        if filas:
            vacias_internas.extend(pendientes)
        pendientes.clear()
        filas.append((fila_excel, dict(zip(nombres, valores, strict=False))))
    return nombres, filas, tuple(vacias_internas)


def _analizar_hoja(tipo: str, hoja: object) -> CalidadHoja:
    """Audita hoja, cantidades y ubicación de los hallazgos."""
    nombres, filas, vacias = _leer_filas_hoja(hoja)
    exactos, posibles = _repetidos(tipo, hoja.title, filas)
    series, invalidas, duplicadas = (
        _datos_temporales(hoja.title, filas) if tipo == "mediciones" else ((), (), ())
    )
    return CalidadHoja(
        nombre=hoja.title,
        registros=len(filas),
        duplicados_exactos=len(exactos),
        posibles_repetidos=len(posibles),
        fechas_invalidas=len(invalidas),
        fechas_duplicadas=len(duplicadas),
        columnas_ausentes=tuple(c for c in ESQUEMAS[tipo] if c not in nombres),
        columnas=_resumen_columnas(tipo, hoja.title, filas, set(nombres)),
        series=series,
        ubicaciones_duplicados=exactos,
        ubicaciones_posibles=posibles,
        ubicaciones_fechas_invalidas=invalidas,
        ubicaciones_fechas_duplicadas=duplicadas,
        filas_completamente_vacias=vacias,
    )


def _procesar_hojas(
    libro: object,
    tipo: str,
) -> tuple[tuple[CalidadHoja, ...], tuple[str, ...]]:
    """Omite hojas auxiliares indicando exactamente cuáles fueron."""
    if len(libro.worksheets) > MAXIMO_HOJAS:
        raise ValueError("El Excel supera el límite de 30 hojas.")
    hojas = []
    omitidas = []
    for hoja in libro.worksheets:
        primera = next(
            hoja.iter_rows(min_row=1, max_row=1, values_only=True),
            (),
        )
        if _campos_compatibles(tipo, primera):
            hojas.append(_analizar_hoja(tipo, hoja))
        else:
            omitidas.append(hoja.title)
    if not hojas:
        raise ValueError("Ninguna hoja contiene encabezados compatibles.")
    return tuple(hojas), tuple(omitidas)


def auditar_excel(tipo: str, nombre: str, contenido: bytes) -> InformeCalidad:
    """Valida tamaño y tipo, audita originales sin escritura."""
    if tipo not in ESQUEMAS:
        raise ValueError("Tipo de archivo no permitido para la auditoría.")
    if not isinstance(nombre, str) or not nombre.lower().endswith(".xlsx"):
        raise ValueError("La auditoría integral requiere un archivo XLSX.")
    if not isinstance(contenido, bytes) or not 0 < len(contenido) <= MAXIMO_LIBRO_BYTES:
        raise ValueError("El XLSX debe contener entre 1 byte y 25 MiB.")
    try:
        libro = load_workbook(BytesIO(contenido), read_only=True, data_only=True)
    except (BadZipFile, OSError, ValueError, KeyError, EOFError) as error:
        raise ValueError("El XLSX no pudo abrirse de forma segura.") from error
    try:
        hojas, omitidas = _procesar_hojas(libro, tipo)
        return InformeCalidad(
            tipo=tipo,
            nombre=nombre,
            sha256=hashlib.sha256(contenido).hexdigest(),
            hojas=hojas,
            hojas_omitidas=omitidas,
        )
    finally:
        libro.close()
