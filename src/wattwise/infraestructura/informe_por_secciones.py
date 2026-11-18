"""Borradores y PDF por análisis sin modificar el generador de informes existente."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from wattwise.dominio.vistas import GRAFICAS
from wattwise.infraestructura.capturas_sqlite import recuperar_captura, validar_png
from wattwise.infraestructura.proyectos_sqlite import inicializar_proyectos

MAXIMO_ANALISIS = 30

# Catálogo del informe separado del contrato reproducible de Vistas.
GRAFICAS_INFORME = {
    **GRAFICAS,
    "mediciones": (
        *GRAFICAS["mediciones"],
        "Comportamiento horario",
        "Diagnóstico de ingeniería",
        "Potencia activa (formato inicial)",
    ),
    "motores": (
        *GRAFICAS["motores"],
        "Mapa de horas por motor",
    ),
}


@dataclass(frozen=True, slots=True)
class AnalisisInforme:
    """Una gráfica y su observación, con inclusión independiente."""

    clave: str
    titulo: str
    modulo: str
    grafica: str
    captura_id: int | None = None
    observacion: str = ""
    incluir_grafica: bool = True
    incluir_observacion: bool = True


@dataclass(frozen=True, slots=True)
class BorradorInforme:
    """Datos generales y análisis ordenados de un proyecto."""

    proyecto_id: int
    nombre: str
    responsable: str
    fecha: str
    descripcion: str
    analisis: tuple[AnalisisInforme, ...]


def _id(valor: int) -> None:
    if type(valor) is not int or valor <= 0:
        raise ValueError("Se requiere un identificador entero positivo.")


def _texto(valor: str, campo: str, limite: int, requerido: bool = False) -> str:
    if not isinstance(valor, str):
        raise ValueError(f"{campo} debe ser texto.")
    limpio = valor.strip()
    if len(limpio) > limite or (requerido and not limpio):
        raise ValueError(f"{campo} tiene una longitud no permitida.")
    if any(ord(caracter) < 32 and caracter not in "\n\t" for caracter in limpio):
        raise ValueError(f"{campo} contiene caracteres de control.")
    return limpio


def _validar_analisis(item: AnalisisInforme) -> None:
    if not isinstance(item, AnalisisInforme):
        raise ValueError("La estructura del análisis es inválida.")
    clave = _texto(item.clave, "Identificador del análisis", 64, True)
    if not clave.isascii() or not all(c.isalnum() or c in "_-" for c in clave):
        raise ValueError("Identificador del análisis no permitido.")
    _texto(item.titulo, "Título del análisis", 120, True)
    if item.modulo not in GRAFICAS_INFORME or item.grafica not in GRAFICAS_INFORME[item.modulo]:
        raise ValueError("Selecciona una gráfica que exista en el módulo indicado.")
    if item.captura_id is not None:
        _id(item.captura_id)
    _texto(item.observacion, "Observación", 2000)
    if type(item.incluir_grafica) is not bool or type(item.incluir_observacion) is not bool:
        raise ValueError("Las opciones de inclusión deben ser verdaderas o falsas.")


def validar_borrador(borrador: BorradorInforme) -> None:
    """Valida el esquema antes de almacenar o generar documentos."""
    if not isinstance(borrador, BorradorInforme):
        raise ValueError("Se requiere un borrador de informe válido.")
    _id(borrador.proyecto_id)
    _texto(borrador.nombre, "Nombre del proyecto", 120, True)
    _texto(borrador.responsable, "Responsable", 120)
    _texto(borrador.descripcion, "Descripción", 2000)
    try:
        fecha = date.fromisoformat(borrador.fecha)
    except (TypeError, ValueError) as error:
        raise ValueError("La fecha debe usar AAAA-MM-DD.") from error
    if fecha.isoformat() != borrador.fecha:
        raise ValueError("La fecha debe usar AAAA-MM-DD.")
    if not isinstance(borrador.analisis, tuple) or len(borrador.analisis) > MAXIMO_ANALISIS:
        raise ValueError("Se permiten como máximo 30 análisis en el informe.")
    for item in borrador.analisis:
        _validar_analisis(item)
    claves = [item.clave for item in borrador.analisis]
    if len(set(claves)) != len(claves):
        raise ValueError("Los análisis deben tener identificadores distintos.")


def _conectar(ruta: Path) -> sqlite3.Connection:
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_borradores(ruta: Path) -> None:
    """Crea una tabla adicional sin migrar ni alterar las tablas anteriores."""
    inicializar_proyectos(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute(
            "CREATE TABLE IF NOT EXISTS borradores_informe_secciones ("
            "proyecto_id INTEGER PRIMARY KEY, contenido_json TEXT NOT NULL, "
            "sha256 TEXT NOT NULL, actualizado_utc TEXT NOT NULL, "
            "FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE)"
        )


def guardar_borrador_informe(ruta: Path, borrador: BorradorInforme) -> None:
    """Guarda un borrador completo por proyecto en una transacción."""
    validar_borrador(borrador)
    contenido = json.dumps(asdict(borrador), ensure_ascii=False, sort_keys=True)
    huella = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    inicializar_borradores(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        if (
            conexion.execute(
                "SELECT 1 FROM proyectos WHERE id = ?", (borrador.proyecto_id,)
            ).fetchone()
            is None
        ):
            raise ValueError("El proyecto seleccionado no existe.")
        conexion.execute(
            "INSERT INTO borradores_informe_secciones "
            "(proyecto_id, contenido_json, sha256, actualizado_utc) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(proyecto_id) DO UPDATE SET "
            "contenido_json = excluded.contenido_json, sha256 = excluded.sha256, "
            "actualizado_utc = excluded.actualizado_utc",
            (
                borrador.proyecto_id,
                contenido,
                huella,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )


def recuperar_borrador_informe(ruta: Path, proyecto_id: int) -> BorradorInforme | None:
    """Recupera exclusivamente el borrador del proyecto y comprueba su SHA-256."""
    _id(proyecto_id)
    inicializar_borradores(ruta)
    with closing(_conectar(ruta)) as conexion:
        fila = conexion.execute(
            "SELECT contenido_json, sha256 FROM borradores_informe_secciones WHERE proyecto_id = ?",
            (proyecto_id,),
        ).fetchone()
    if fila is None:
        return None
    contenido, huella = fila
    if hashlib.sha256(contenido.encode("utf-8")).hexdigest() != huella:
        raise ValueError("El borrador del informe no supera la verificación de integridad.")
    try:
        datos = json.loads(contenido)
        analisis = tuple(AnalisisInforme(**item) for item in datos.pop("analisis"))
        borrador = BorradorInforme(analisis=analisis, **datos)
        validar_borrador(borrador)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError("El borrador guardado tiene una estructura inválida.") from error
    if borrador.proyecto_id != proyecto_id:
        raise ValueError("El borrador no corresponde al proyecto solicitado.")
    return borrador


def _estilos() -> dict[str, Any]:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "ww_is_titulo", parent=base["Title"], textColor=colors.HexColor("#174a73")
        ),
        "seccion": ParagraphStyle(
            "ww_is_seccion", parent=base["Heading2"], textColor=colors.HexColor("#174a73")
        ),
        "normal": ParagraphStyle("ww_is_normal", parent=base["BodyText"], leading=15, spaceAfter=9),
        "pequeno": ParagraphStyle("ww_is_pequeno", parent=base["BodyText"], fontSize=8, leading=11),
    }


def _escapar(valor: str) -> str:
    return escape(valor).replace("\n", "<br/>")


def _agregar_datos_generales(
    historia: list[Any],
    borrador: BorradorInforme,
    estilos: dict[str, Any],
) -> None:
    from reportlab.platypus import Paragraph, Spacer

    historia.extend(
        [
            Paragraph("WattWise | Informe técnico", estilos["titulo"]),
            Spacer(1, 12),
            Paragraph(f"<b>Proyecto:</b> {_escapar(borrador.nombre)}", estilos["normal"]),
            Paragraph(
                f"<b>Responsable:</b> {_escapar(borrador.responsable or 'No indicado')}",
                estilos["normal"],
            ),
            Paragraph(f"<b>Fecha:</b> {borrador.fecha}", estilos["normal"]),
        ]
    )
    if borrador.descripcion.strip():
        historia.append(Paragraph("Descripción general", estilos["seccion"]))
        historia.append(Paragraph(_escapar(borrador.descripcion), estilos["normal"]))
    historia.append(
        Paragraph(
            "Las capturas PNG fueron aportadas por el usuario. WattWise verifica su "
            "integridad, pero no certifica su correspondencia con las mediciones "
            "ni reemplaza una revisión profesional.",
            estilos["pequeno"],
        )
    )


def _agregar_analisis(
    historia: list[Any],
    indice: int,
    item: AnalisisInforme,
    png: bytes | None,
    estilos: dict[str, Any],
) -> None:
    from reportlab.lib.units import cm
    from reportlab.platypus import CondPageBreak, Image as ImagenPDF, Paragraph, Spacer

    historia.extend(
        [
            CondPageBreak(14 * cm if png is not None else 6 * cm),
            Spacer(1, 17),
            Paragraph(f"Análisis {indice}: {_escapar(item.titulo)}", estilos["seccion"]),
            Paragraph(f"<b>Módulo:</b> {_escapar(item.modulo.capitalize())}", estilos["normal"]),
            Paragraph(f"<b>Gráfica:</b> {_escapar(item.grafica)}", estilos["normal"]),
        ]
    )
    if png is not None:
        ancho, alto = validar_png(png)
        escala = min(16.5 * cm / ancho, 11 * cm / alto)
        historia.extend(
            [
                Spacer(1, 7),
                ImagenPDF(BytesIO(png), width=ancho * escala, height=alto * escala),
                Spacer(1, 9),
            ]
        )
    if item.incluir_observacion and item.observacion.strip():
        historia.extend(
            [
                Paragraph("Observaciones", estilos["seccion"]),
                Paragraph(_escapar(item.observacion.strip()), estilos["normal"]),
            ]
        )


def _pie_pagina(canvas: Any, documento: Any) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#52677b"))
    canvas.drawString(1.8 * cm, 1 * cm, "WattWise · Documento sujeto a revisión profesional")
    canvas.drawRightString(19.1 * cm, 1 * cm, f"Página {documento.page}")
    canvas.restoreState()


def _imagen_para_pdf(
    ruta: Path, proyecto_id: int, indice: int, item: AnalisisInforme
) -> bytes | None:
    if not item.incluir_grafica:
        return None
    if item.captura_id is None:
        raise ValueError(f"Análisis {indice}: falta subir la imagen PNG marcada para el PDF.")
    try:
        _captura, png = recuperar_captura(ruta, proyecto_id, item.captura_id)
    except ValueError as error:
        raise ValueError(f"Análisis {indice}: el PNG no pertenece a este proyecto.") from error
    return png


def generar_pdf_por_secciones(ruta: Path, borrador: BorradorInforme) -> bytes:
    """Genera PDF con las gráficas y notas elegidas, en el orden de los análisis."""
    validar_borrador(borrador)
    inicializar_borradores(ruta)
    with closing(_conectar(ruta)) as conexion:
        existe = conexion.execute(
            "SELECT 1 FROM proyectos WHERE id = ?", (borrador.proyecto_id,)
        ).fetchone()
    if existe is None:
        raise ValueError("El proyecto seleccionado no existe.")
    incluidos = [
        (indice, item)
        for indice, item in enumerate(borrador.analisis, start=1)
        if item.incluir_grafica or (item.incluir_observacion and item.observacion.strip())
    ]
    if not incluidos:
        raise ValueError("Incluye al menos una gráfica o una observación en el PDF.")
    contenido = [
        (indice, item, _imagen_para_pdf(ruta, borrador.proyecto_id, indice, item))
        for indice, item in incluidos
    ]

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate

    memoria = BytesIO()
    documento = SimpleDocTemplate(
        memoria,
        pagesize=A4,
        leftMargin=1.9 * cm,
        rightMargin=1.9 * cm,
        topMargin=1.7 * cm,
        bottomMargin=1.8 * cm,
        title=f"WattWise - {borrador.nombre}",
        author=borrador.responsable or "WattWise",
    )
    estilos = _estilos()
    historia: list[Any] = []
    _agregar_datos_generales(historia, borrador, estilos)
    for indice, item, png in contenido:
        _agregar_analisis(historia, indice, item, png, estilos)
    documento.build(historia, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    return memoria.getvalue()
