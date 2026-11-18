"""Informe PDF descriptivo de analisis guardados; sin recrear graficas ECharts."""

from __future__ import annotations

from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from wattwise.infraestructura.analisis_sqlite import AnalisisGuardado

MAXIMO_FILAS_PDF = 50
COLUMNAS_PREFERIDAS = {
    "inventario": (
        "area",
        "equipo",
        "tipo_carga",
        "cantidad",
        "potencia_instalada_kw",
    ),
    "motores": (
        "area",
        "equipo",
        "potencia_nominal_hp",
        "corriente_nominal_a",
        "corriente_medida_a",
        "horas_operacion_mes",
    ),
    "mediciones": (
        "fecha_hora",
        "p_total_kw",
        "p_l1_kw",
        "i_total_a",
        "fp_total",
        "potencia_activa_kw",
    ),
}


def _cadena(valor: object, limite: int = 350) -> str:
    """Convierte valores a texto seguro para parrafos ReportLab."""
    if valor is None:
        return "No disponible"
    texto = str(valor)
    if len(texto) > limite:
        texto = texto[:limite] + "..."
    return escape(texto)


def _columnas(analisis: AnalisisGuardado) -> list[str]:
    """Elige hasta seis columnas relevantes sin presentar tablas ilegibles."""
    registros = analisis.datos.get("registros")
    if not isinstance(registros, list):
        return []
    disponibles = {
        clave
        for registro in registros
        if isinstance(registro, dict)
        for clave in registro
        if isinstance(clave, str)
    }
    preferidas = COLUMNAS_PREFERIDAS.get(analisis.tipo, ())
    columnas = [campo for campo in preferidas if campo in disponibles]
    return columnas[:6] if columnas else sorted(disponibles)[:6]


def _indicadores(analisis: AnalisisGuardado) -> list[tuple[str, str]]:
    """Recoge indicadores escalares sin fabricar estadisticas inexistentes."""
    return [
        (clave.replace("_", " ").capitalize(), _cadena(valor))
        for clave, valor in analisis.datos.items()
        if isinstance(valor, (str, int, float, bool))
    ][:24]


def _validar_identidad(
    proyecto: str,
    analisis: AnalisisGuardado,
) -> None:
    """Valida proyecto y tipo de analisis sin confiar en la pantalla."""
    if not isinstance(proyecto, str) or not proyecto.strip():
        raise ValueError("El proyecto no tiene un nombre valido.")
    if analisis.tipo not in COLUMNAS_PREFERIDAS or not isinstance(analisis.datos, dict):
        raise ValueError("El analisis guardado no corresponde a un tipo admitido.")


def _validar_parametros(
    maximo_filas: int,
    origen: str,
    observaciones: str,
) -> None:
    """Impide opciones de exportacion invalidas o excesivas."""
    if isinstance(maximo_filas, bool) or not isinstance(maximo_filas, int):
        raise ValueError("El limite de filas debe ser un entero.")
    if not 1 <= maximo_filas <= MAXIMO_FILAS_PDF:
        raise ValueError("El limite de filas esta fuera del rango permitido.")
    if origen not in {"No verificado", "Datos de ensayo", "Datos declarados"}:
        raise ValueError("Origen de datos no admitido.")
    if not isinstance(observaciones, str) or len(observaciones) > 2000:
        raise ValueError("Las observaciones superan el limite permitido.")


def _estilos() -> dict[str, Any]:
    """Construye estilos locales con fuentes compatibles con PDF."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    normal = ParagraphStyle(
        "NormalWW",
        parent=base["BodyText"],
        leading=14,
        spaceAfter=8,
    )
    celda = ParagraphStyle(
        "CeldaWW",
        parent=normal,
        fontSize=7,
        leading=9,
        spaceAfter=0,
    )
    return {
        "titulo": ParagraphStyle(
            "TituloWW",
            parent=base["Title"],
            alignment=TA_CENTER,
            textColor=colors.HexColor("#123f66"),
            spaceAfter=15,
        ),
        "normal": normal,
        "celda": celda,
        "encabezado": ParagraphStyle(
            "EncabezadoWW",
            parent=celda,
            textColor=colors.HexColor("#123f66"),
        ),
        "seccion": base["Heading2"],
    }


def _cabecera(
    historia: list[Any],
    estilos: dict[str, Any],
    proyecto: str,
    analisis: AnalisisGuardado,
    origen: str,
) -> None:
    """Agrega titulo y datos de procedencia al informe."""
    from reportlab.platypus import Paragraph, Spacer

    historia.extend(
        [
            Paragraph(
                "WattWise | Informe tecnico descriptivo",
                estilos["titulo"],
            ),
            Paragraph(
                f"<b>Proyecto:</b> {_cadena(proyecto)}",
                estilos["normal"],
            ),
            Paragraph(
                f"<b>Analisis:</b> {_cadena(analisis.titulo)}",
                estilos["normal"],
            ),
            Paragraph(
                f"<b>Tipo:</b> {_cadena(analisis.tipo)}",
                estilos["normal"],
            ),
            Paragraph(
                f"<b>Registro UTC:</b> {_cadena(analisis.creado_utc)}",
                estilos["normal"],
            ),
            Paragraph(
                f"<b>Origen:</b> {_cadena(origen)}",
                estilos["normal"],
            ),
            Spacer(1, 12),
            Paragraph(
                "Indicadores disponibles",
                estilos["seccion"],
            ),
        ]
    )


def _agregar_indicadores(
    historia: list[Any],
    estilos: dict[str, Any],
    analisis: AnalisisGuardado,
) -> None:
    """Inserta tabla de indicadores cuando existan valores guardados."""
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle

    indicadores = _indicadores(analisis)
    if not indicadores:
        historia.append(
            Paragraph(
                "No hay indicadores escalares guardados.",
                estilos["normal"],
            )
        )
        return

    filas = [
        [
            Paragraph(_cadena(nombre), estilos["celda"]),
            Paragraph(valor, estilos["celda"]),
        ]
        for nombre, valor in indicadores
    ]
    tabla = Table(
        filas,
        colWidths=[7.3 * cm, 9.7 * cm],
        hAlign="LEFT",
    )
    tabla.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#d9e2ec"),
                ),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor("#f2f6fb"),
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    historia.append(tabla)


def _agregar_registros(
    historia: list[Any],
    estilos: dict[str, Any],
    analisis: AnalisisGuardado,
    maximo_filas: int,
) -> None:
    """Incluye tabla acotada con encabezados repetidos en cada pagina."""
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    registros = analisis.datos.get("registros")
    columnas = _columnas(analisis)
    if not isinstance(registros, list) or not columnas:
        return

    filas = [registro for registro in registros if isinstance(registro, dict)]
    historia.extend(
        [
            Spacer(1, 18),
            Paragraph(
                "Detalle de registros",
                estilos["seccion"],
            ),
            Paragraph(
                f"Se muestran hasta {maximo_filas} de {len(filas)} registros guardados.",
                estilos["normal"],
            ),
        ]
    )
    contenido = [[Paragraph(_cadena(nombre), estilos["encabezado"]) for nombre in columnas]]
    for registro in filas[:maximo_filas]:
        contenido.append(
            [
                Paragraph(
                    _cadena(registro.get(nombre), 80),
                    estilos["celda"],
                )
                for nombre in columnas
            ]
        )

    ancho = 17 * cm / len(columnas)
    tabla = Table(
        contenido,
        colWidths=[ancho] * len(columnas),
        repeatRows=1,
        splitByRow=1,
        hAlign="LEFT",
    )
    tabla.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.3,
                    colors.HexColor("#dae2ec"),
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#eef4fa"),
                ),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    historia.append(tabla)


def _limitaciones(
    historia: list[Any],
    estilos: dict[str, Any],
    observaciones: str,
) -> None:
    """Incluye metodologia, advertencias y comentarios del usuario."""
    from reportlab.platypus import Paragraph, Spacer

    if observaciones.strip():
        historia.extend(
            [
                Spacer(1, 14),
                Paragraph(
                    "Observaciones del informe",
                    estilos["seccion"],
                ),
                Paragraph(
                    _cadena(observaciones, 2000).replace("\n", "<br/>"),
                    estilos["normal"],
                ),
            ]
        )

    historia.extend(
        [
            Spacer(1, 14),
            Paragraph(
                "Metodologia y limitaciones",
                estilos["seccion"],
            ),
            Paragraph(
                "El documento reproduce resultados previamente guardados. "
                "Potencia instalada (kW), demanda (kW) y energia (kWh) "
                "son magnitudes distintas. Los valores no constituyen un "
                "diagnostico de fallas, una certificacion electrica ni una "
                "verificacion normativa.",
                estilos["normal"],
            ),
            Paragraph(
                "El origen, exactitud, alcance electrico y consistencia de "
                "los datos no han sido certificados por esta herramienta. "
                "Los registros de diferentes puntos no se suman "
                "automaticamente.",
                estilos["normal"],
            ),
            Paragraph(
                "Este PDF descriptivo aun no incorpora imagenes exportadas "
                "desde las graficas Apache ECharts. Esa integracion sigue "
                "pendiente.",
                estilos["normal"],
            ),
        ]
    )


def _pie(canvas: Any, documento: Any) -> None:
    """Identifica pagina y aplicacion en cada hoja."""
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#63758a"))
    canvas.drawString(
        1.7 * cm,
        1.15 * cm,
        "WattWise | Resultados sujetos a revision profesional",
    )
    canvas.drawRightString(
        19.3 * cm,
        1.15 * cm,
        f"Pagina {documento.page}",
    )
    canvas.restoreState()


def generar_informe_pdf(
    proyecto: str,
    analisis: AnalisisGuardado,
    *,
    incluir_tabla: bool = True,
    maximo_filas: int = 20,
    origen: str = "No verificado",
    observaciones: str = "",
) -> bytes:
    """Produce PDF real con cifras guardadas y advertencias metodologicas."""
    _validar_identidad(proyecto, analisis)
    _validar_parametros(
        maximo_filas,
        origen,
        observaciones,
    )

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate

    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=A4,
        leftMargin=1.7 * cm,
        rightMargin=1.7 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"WattWise - {analisis.titulo}",
        author="WattWise",
    )
    estilos = _estilos()
    historia: list[Any] = []

    _cabecera(historia, estilos, proyecto, analisis, origen)
    _agregar_indicadores(historia, estilos, analisis)

    if incluir_tabla:
        _agregar_registros(
            historia,
            estilos,
            analisis,
            maximo_filas,
        )

    _limitaciones(historia, estilos, observaciones)
    documento.build(
        historia,
        onFirstPage=_pie,
        onLaterPages=_pie,
    )
    return salida.getvalue()
