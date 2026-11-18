"""Produce un informe PDF con capturas PNG seleccionadas y origen documentado."""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from wattwise.infraestructura.analisis_sqlite import AnalisisGuardado
from wattwise.infraestructura.capturas_sqlite import CapturaGrafica, validar_png

MAXIMO_GRAFICAS_PDF = 12
MAXIMO_NOTAS = 2000


def _texto(valor: object, maximo: int = 500) -> str:
    """Escapa texto libre sin interpretar HTML proporcionado por el usuario."""
    texto = "No disponible" if valor is None else str(valor)
    if len(texto) > maximo:
        texto = texto[:maximo] + "..."
    return escape(texto)


def _validar_imagen(
    captura: CapturaGrafica,
    contenido: bytes,
    analisis: AnalisisGuardado | None,
) -> None:
    """Comprueba asociacion, tamano, SHA-256 y formato de cada PNG."""
    if analisis is None and captura.analisis_id is not None:
        raise ValueError("Una captura vinculada requiere su analisis.")
    if analisis is not None and captura.analisis_id not in (None, analisis.id):
        raise ValueError("La captura corresponde a otro analisis.")
    if len(contenido) != captura.tamano_bytes:
        raise ValueError("El tamano de la captura no coincide.")
    if hashlib.sha256(contenido).hexdigest() != captura.sha256:
        raise ValueError("La captura no supera su verificacion SHA-256.")
    validar_png(contenido)


def _validar_asociaciones(
    analisis: AnalisisGuardado | None,
    imagenes: list[tuple[CapturaGrafica, bytes]],
) -> None:
    """Garantiza que las capturas pertenecen al proyecto y analisis esperados."""
    proyectos = {captura.proyecto_id for captura, _ in imagenes}
    if len(proyectos) != 1 or (analisis is not None and analisis.proyecto_id not in proyectos):
        raise ValueError("Las capturas no corresponden al mismo proyecto.")
    for captura, contenido in imagenes:
        _validar_imagen(captura, contenido, analisis)


def _validar_solicitud(
    proyecto: str,
    analisis: AnalisisGuardado | None,
    imagenes: list[tuple[CapturaGrafica, bytes]],
    observaciones: str,
) -> None:
    """Valida solicitud y delega comprobaciones por archivo."""
    if not isinstance(proyecto, str) or not proyecto.strip():
        raise ValueError("El proyecto debe tener un nombre valido.")
    if not isinstance(observaciones, str) or len(observaciones) > MAXIMO_NOTAS:
        raise ValueError("Las observaciones superan el limite permitido.")
    if not 1 <= len(imagenes) <= MAXIMO_GRAFICAS_PDF:
        raise ValueError("Selecciona entre 1 y 12 graficas para el PDF.")
    if analisis is not None and not isinstance(analisis.datos, dict):
        raise ValueError("El analisis no contiene resultados validos.")
    _validar_asociaciones(analisis, imagenes)


def _indicadores(analisis: AnalisisGuardado | None) -> list[tuple[str, str]]:
    """Recoge escalares originales sin recomputar ni inventar indicadores."""
    if analisis is None:
        return []
    return [
        (clave.replace("_", " ").capitalize(), _texto(valor))
        for clave, valor in analisis.datos.items()
        if isinstance(valor, (str, int, float, bool))
    ][:20]


def _crear_portada(
    historia: list[Any],
    estilos: dict[str, Any],
    proyecto: str,
    analisis: AnalisisGuardado | None,
    observaciones: str,
) -> None:
    """Documenta procedencia, indicadores y límites de las capturas aportadas."""
    from reportlab.platypus import Paragraph, Spacer

    historia.append(Paragraph("WattWise | Informe con graficas", estilos["titulo"]))
    historia.append(Paragraph(f"<b>Proyecto:</b> {_texto(proyecto)}", estilos["normal"]))
    if analisis is None:
        historia.append(
            Paragraph(
                "No se ha asociado un analisis estructurado a las capturas. "
                "Este informe contiene imagenes suministradas por el usuario.",
                estilos["normal"],
            )
        )
    else:
        historia.extend(
            [
                Paragraph(
                    f"<b>Analisis:</b> #{analisis.id} · {_texto(analisis.titulo)}",
                    estilos["normal"],
                ),
                Paragraph(
                    f"<b>Tipo:</b> {_texto(analisis.tipo)} · "
                    f"<b>Registro UTC:</b> {_texto(analisis.creado_utc)}",
                    estilos["normal"],
                ),
            ]
        )
    historia.extend(
        [
            Spacer(1, 12),
            Paragraph("Alcance del documento", estilos["seccion"]),
            Paragraph(
                "Las capturas PNG fueron exportadas e incorporadas manualmente. "
                "WattWise comprueba integridad de los archivos, pero no certifica "
                "que su contenido visual corresponda al conjunto de datos o "
                "a una configuracion especifica de filtros.",
                estilos["normal"],
            ),
        ]
    )
    indicadores = _indicadores(analisis)
    if indicadores:
        historia.append(Paragraph("Indicadores guardados", estilos["seccion"]))
        for nombre, valor in indicadores:
            historia.append(Paragraph(f"<b>{_texto(nombre)}:</b> {valor}", estilos["normal"]))
    if observaciones.strip():
        historia.append(Paragraph("Observaciones del informe", estilos["seccion"]))
        historia.append(
            Paragraph(_texto(observaciones, MAXIMO_NOTAS).replace("\n", "<br/>"), estilos["normal"])
        )
    historia.append(
        Paragraph(
            "Este documento no constituye una certificacion, una verificacion "
            "normativa ni un diagnostico automatico de fallas electricas.",
            estilos["normal"],
        )
    )


def _agregar_imagenes(
    historia: list[Any],
    estilos: dict[str, Any],
    imagenes: list[tuple[CapturaGrafica, bytes]],
) -> None:
    """Incluye una grafica por pagina conservando su relacion de aspecto."""
    from reportlab.lib.units import cm
    from reportlab.platypus import Image as ImagenPDF, PageBreak, Paragraph, Spacer

    for indice, (captura, contenido) in enumerate(imagenes, start=1):
        ancho, alto = validar_png(contenido)
        escala = min(16.5 * cm / ancho, 15 * cm / alto)
        historia.extend(
            [
                PageBreak(),
                Paragraph(f"Grafica {indice}: {_texto(captura.nombre)}", estilos["seccion"]),
                Spacer(1, 12),
                ImagenPDF(BytesIO(contenido), width=ancho * escala, height=alto * escala),
                Spacer(1, 12),
                Paragraph(
                    f"<b>Descripcion:</b> {_texto(captura.descripcion or 'Sin descripcion')}",
                    estilos["normal"],
                ),
                Paragraph(
                    f"<b>Captura:</b> #{captura.id} · <b>SHA-256:</b> {_texto(captura.sha256)}",
                    estilos["pequeno"],
                ),
            ]
        )


def _pie_pagina(canvas: Any, documento: Any) -> None:
    """Añade identidad y número de página a cada hoja."""
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#52677b"))
    canvas.drawString(1.8 * cm, 1.1 * cm, "WattWise · Informe sujeto a revision profesional")
    canvas.drawRightString(19.2 * cm, 1.1 * cm, f"Pagina {documento.page}")
    canvas.restoreState()


def generar_informe_graficas_pdf(
    proyecto: str,
    analisis: AnalisisGuardado | None,
    imagenes: list[tuple[CapturaGrafica, bytes]],
    *,
    observaciones: str = "",
) -> bytes:
    """Genera PDF multipagina solo con imagenes verificadas del mismo proyecto."""
    _validar_solicitud(proyecto, analisis, imagenes, observaciones)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate

    base = getSampleStyleSheet()
    estilos = {
        "titulo": ParagraphStyle(
            "ww_titulo_graficas",
            parent=base["Title"],
            textColor=colors.HexColor("#174a73"),
            spaceAfter=16,
        ),
        "seccion": base["Heading2"],
        "normal": ParagraphStyle(
            "ww_normal_graficas",
            parent=base["BodyText"],
            leading=14,
            spaceAfter=9,
        ),
        "pequeno": ParagraphStyle(
            "ww_pequeno_graficas",
            parent=base["BodyText"],
            fontSize=7,
            leading=10,
            wordWrap="CJK",
        ),
    }
    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="WattWise - Informe con graficas seleccionadas",
        author="WattWise",
    )
    historia: list[Any] = []
    _crear_portada(historia, estilos, proyecto, analisis, observaciones)
    _agregar_imagenes(historia, estilos, imagenes)
    documento.build(historia, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    return salida.getvalue()
