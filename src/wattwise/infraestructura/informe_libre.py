"""Borradores y PDF libres para Informes; preserva los informes heredados."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from wattwise.infraestructura.capturas_sqlite import recuperar_captura, validar_png
from wattwise.infraestructura.proyectos_sqlite import inicializar_proyectos

MAXIMO_ANALISIS = 30
MAXIMO_BLOQUES = 80
ESTILOS = ("Título", "Subtítulo", "Párrafo")
TIPOS = ("imagen", "observacion", "texto")


@dataclass(frozen=True, slots=True)
class BloqueLibre:
    """Pieza ordenada: imagen, observación o texto con formato."""

    clave: str
    tipo: str
    texto: str = ""
    estilo: str = "Párrafo"
    tamano: int = 11
    negrilla: bool = False
    captura_id: int | None = None
    nombre: str = ""


@dataclass(frozen=True, slots=True)
class AnalisisLibre:
    """Sección temática con múltiples imágenes y observaciones."""

    clave: str
    titulo: str
    bloques: tuple[BloqueLibre, ...] = ()


@dataclass(frozen=True, slots=True)
class InformeLibre:
    """Informe completo de un proyecto, con introducción y análisis."""

    proyecto_id: int
    proyecto: str
    responsable: str
    fecha: str
    introduccion: tuple[BloqueLibre, ...]
    analisis: tuple[AnalisisLibre, ...]


def _id(valor: int) -> None:
    if type(valor) is not int or valor <= 0:
        raise ValueError("El identificador debe ser un entero positivo.")


def _texto(valor: str, nombre: str, maximo: int) -> str:
    if not isinstance(valor, str) or len(valor) > maximo:
        raise ValueError(f"{nombre} supera el límite permitido.")
    if any(ord(caracter) < 32 and caracter not in "\t\n" for caracter in valor):
        raise ValueError(f"{nombre} contiene caracteres de control.")
    return valor


def _clave(valor: str) -> None:
    if not isinstance(valor, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", valor):
        raise ValueError("La clave del bloque no es válida.")


def _validar_formato(bloque: BloqueLibre) -> None:
    if bloque.tipo not in TIPOS or bloque.estilo not in ESTILOS:
        raise ValueError("Tipo o formato de bloque desconocido.")
    if type(bloque.tamano) is not int or not 8 <= bloque.tamano <= 40:
        raise ValueError("El tamaño de fuente debe estar entre 8 y 40.")
    if type(bloque.negrilla) is not bool:
        raise ValueError("La negrilla debe ser verdadera o falsa.")


def _validar_bloque(bloque: BloqueLibre) -> None:
    if not isinstance(bloque, BloqueLibre):
        raise ValueError("El bloque no es válido.")
    _clave(bloque.clave)
    _validar_formato(bloque)
    _texto(bloque.texto, "Texto del bloque", 5000)
    _texto(bloque.nombre, "Nombre de la imagen", 160)
    if bloque.captura_id is not None:
        _id(bloque.captura_id)
    if bloque.tipo == "imagen" and bloque.captura_id is None:
        raise ValueError("La imagen necesita un PNG guardado.")
    if bloque.tipo != "imagen" and bloque.captura_id is not None:
        raise ValueError("Solo una imagen puede incluir captura PNG.")


def _validar_metadatos(informe: InformeLibre) -> None:
    _id(informe.proyecto_id)
    if not _texto(informe.proyecto, "Proyecto", 120).strip():
        raise ValueError("El nombre del proyecto es obligatorio.")
    _texto(informe.responsable, "Responsable", 120)
    if not isinstance(informe.fecha, str):
        raise ValueError("La fecha no es válida.")
    try:
        if date.fromisoformat(informe.fecha).isoformat() != informe.fecha:
            raise ValueError("Fecha no canónica.")
    except ValueError as error:
        raise ValueError("La fecha debe usar AAAA-MM-DD.") from error


def _validar_analisis(analisis: AnalisisLibre, claves: list[str]) -> None:
    if not isinstance(analisis, AnalisisLibre):
        raise ValueError("La sección del análisis es inválida.")
    _clave(analisis.clave)
    _texto(analisis.titulo, "Título del análisis", 120)
    claves.append(analisis.clave)
    if not isinstance(analisis.bloques, tuple) or len(analisis.bloques) > MAXIMO_BLOQUES:
        raise ValueError("El análisis contiene demasiados bloques.")
    for bloque in analisis.bloques:
        _validar_bloque(bloque)
        claves.append(bloque.clave)


def validar_informe(informe: InformeLibre) -> None:
    """Valida contenido, estructura y límites antes de tocar SQLite."""
    if not isinstance(informe, InformeLibre):
        raise ValueError("El informe no es válido.")
    _validar_metadatos(informe)
    if not isinstance(informe.introduccion, tuple) or len(informe.introduccion) > MAXIMO_BLOQUES:
        raise ValueError("La introducción contiene demasiados bloques.")
    if not isinstance(informe.analisis, tuple) or len(informe.analisis) > MAXIMO_ANALISIS:
        raise ValueError("El número de análisis supera el límite.")
    claves: list[str] = []
    for bloque in informe.introduccion:
        _validar_bloque(bloque)
        if bloque.tipo == "imagen":
            raise ValueError("La introducción solo admite texto.")
        claves.append(bloque.clave)
    for analisis in informe.analisis:
        _validar_analisis(analisis, claves)
    if len(claves) != len(set(claves)):
        raise ValueError("Los bloques necesitan claves únicas.")


def _conectar(ruta: Path) -> sqlite3.Connection:
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_informes_libres(ruta: Path) -> None:
    """Tabla nueva; no borra ni migra los borradores anteriores."""
    inicializar_proyectos(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute(
            "CREATE TABLE IF NOT EXISTS borradores_informes_libres ("
            "proyecto_id INTEGER PRIMARY KEY, contenido_json TEXT NOT NULL, "
            "sha256 TEXT NOT NULL, actualizado_utc TEXT NOT NULL, "
            "FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE)"
        )


def _comprobar_png(ruta: Path, informe: InformeLibre) -> None:
    for analisis in informe.analisis:
        for bloque in analisis.bloques:
            if bloque.tipo == "imagen" and bloque.captura_id is not None:
                recuperar_captura(ruta, informe.proyecto_id, bloque.captura_id)


def guardar_informe_libre(ruta: Path, informe: InformeLibre) -> None:
    """Guarda el borrador con SHA-256 y referencias PNG del mismo proyecto."""
    validar_informe(informe)
    _comprobar_png(ruta, informe)
    contenido = json.dumps(asdict(informe), ensure_ascii=False, sort_keys=True)
    huella = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    inicializar_informes_libres(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        if (
            conexion.execute(
                "SELECT 1 FROM proyectos WHERE id = ?", (informe.proyecto_id,)
            ).fetchone()
            is None
        ):
            raise ValueError("El proyecto no existe.")
        conexion.execute(
            "INSERT INTO borradores_informes_libres "
            "(proyecto_id, contenido_json, sha256, actualizado_utc) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(proyecto_id) DO UPDATE SET "
            "contenido_json=excluded.contenido_json, "
            "sha256=excluded.sha256, actualizado_utc=excluded.actualizado_utc",
            (informe.proyecto_id, contenido, huella, datetime.now(UTC).isoformat()),
        )


def recuperar_informe_libre(ruta: Path, proyecto_id: int) -> InformeLibre | None:
    """Recupera únicamente el borrador verificable del proyecto solicitado."""
    _id(proyecto_id)
    inicializar_informes_libres(ruta)
    with closing(_conectar(ruta)) as conexion:
        fila = conexion.execute(
            "SELECT contenido_json, sha256 FROM borradores_informes_libres WHERE proyecto_id = ?",
            (proyecto_id,),
        ).fetchone()
    if fila is None:
        return None
    contenido, huella = fila
    if hashlib.sha256(contenido.encode("utf-8")).hexdigest() != huella:
        raise ValueError("El borrador no supera la comprobación de integridad.")
    try:
        datos = json.loads(contenido)
        intro = tuple(BloqueLibre(**item) for item in datos.pop("introduccion"))
        analisis = tuple(
            AnalisisLibre(
                clave=item["clave"],
                titulo=item["titulo"],
                bloques=tuple(BloqueLibre(**bloque) for bloque in item["bloques"]),
            )
            for item in datos.pop("analisis")
        )
        informe = InformeLibre(introduccion=intro, analisis=analisis, **datos)
        validar_informe(informe)
    except (TypeError, ValueError, KeyError, AttributeError) as error:
        raise ValueError("El borrador guardado tiene una estructura inválida.") from error
    if informe.proyecto_id != proyecto_id:
        raise ValueError("El borrador corresponde a otro proyecto.")
    return informe


def _parrafo(texto: str) -> str:
    """Escapa etiquetas HTML; admite solo negrilla ligera con **palabras**."""
    seguro = escape(texto)
    seguro = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", seguro)
    return seguro.replace("\n", "<br/>")


def _agregar_bloque(historia: list[Any], bloque: BloqueLibre, ruta: Path, proyecto_id: int) -> None:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, KeepTogether, Paragraph, Spacer

    if bloque.tipo == "imagen":
        _meta, png = recuperar_captura(ruta, proyecto_id, bloque.captura_id)
        ancho, alto = validar_png(png)
        escala = min((16.5 * cm) / ancho, (19 * cm) / alto)
        imagen = Image(BytesIO(png), width=ancho * escala, height=alto * escala)
        elementos: list[Any] = [imagen]
        # Los nombres automáticos como wattwise (1).png no se imprimen.
        if bloque.nombre.strip() and not bloque.nombre.strip().casefold().endswith(".png"):
            elementos.append(Spacer(1, 6))
            elementos.append(
                Paragraph(
                    _parrafo(bloque.nombre),
                    ParagraphStyle("pie_imagen", fontName="Helvetica", fontSize=9, leading=12),
                )
            )
        historia.extend([KeepTogether(elementos), Spacer(1, 12)])
        return
    if not bloque.texto.strip():
        return
    fuente = "Helvetica-Bold" if bloque.negrilla or bloque.estilo != "Párrafo" else "Helvetica"
    tamano = bloque.tamano
    estilo = ParagraphStyle(
        "texto_libre",
        fontName=fuente,
        fontSize=tamano,
        leading=tamano * 1.35,
        spaceAfter=10,
        keepWithNext=bloque.estilo != "Párrafo",
    )
    historia.append(Paragraph(_parrafo(bloque.texto), estilo))


def _tiene_contenido(informe: InformeLibre) -> bool:
    bloques = [*informe.introduccion]
    for analisis in informe.analisis:
        bloques.extend(analisis.bloques)
    return any(bloque.tipo == "imagen" or bloque.texto.strip() for bloque in bloques)


def _agregar_observaciones(
    historia: list[Any],
    notas: list[BloqueLibre],
    estilo_titulo: Any,
    estilo_nota: Any,
) -> None:
    """Imprime viñetas solo cuando la imagen tiene observaciones."""
    from reportlab.lib.units import cm
    from reportlab.platypus import CondPageBreak, Paragraph

    textos: set[str] = set()
    unicas = []
    for nota in notas:
        texto = nota.texto.strip()
        if texto and texto not in textos:
            textos.add(texto)
            unicas.append(texto)
    if not unicas:
        return
    historia.append(CondPageBreak(3 * cm))
    historia.append(Paragraph("Observaciones", estilo_titulo))
    for texto in unicas:
        historia.append(Paragraph(_parrafo(texto), estilo_nota, bulletText="•"))


def _cuerpo_pdf(historia: list[Any], ruta: Path, informe: InformeLibre) -> None:
    """Respeta la secuencia imagen, sus notas, siguiente imagen y sus notas."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import CondPageBreak, Paragraph

    estilo_seccion = ParagraphStyle(
        "titulo_analisis",
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=21,
        spaceAfter=13,
    )
    estilo_observaciones = ParagraphStyle(
        "titulo_observaciones",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        spaceBefore=8,
        spaceAfter=8,
        keepWithNext=True,
    )
    estilo_nota = ParagraphStyle(
        "nota_vineta",
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        leftIndent=18,
        bulletIndent=5,
        bulletFontName="Helvetica",
        bulletFontSize=11,
        spaceAfter=6,
    )
    for bloque in informe.introduccion:
        _agregar_bloque(historia, bloque, ruta, informe.proyecto_id)
    for indice, analisis in enumerate(informe.analisis, start=1):
        if not analisis.titulo.strip() and not analisis.bloques:
            continue
        historia.append(CondPageBreak(7 * cm))
        rotulo = f"Análisis {indice}"
        if analisis.titulo.strip():
            rotulo += f" — {analisis.titulo.strip()}"
        historia.append(Paragraph(_parrafo(rotulo), estilo_seccion))

        notas_pendientes: list[BloqueLibre] = []
        for bloque in analisis.bloques:
            if bloque.tipo == "observacion":
                notas_pendientes.append(bloque)
                continue
            _agregar_observaciones(historia, notas_pendientes, estilo_observaciones, estilo_nota)
            notas_pendientes = []
            _agregar_bloque(historia, bloque, ruta, informe.proyecto_id)
        _agregar_observaciones(historia, notas_pendientes, estilo_observaciones, estilo_nota)


def generar_pdf_libre(ruta: Path, informe: InformeLibre) -> bytes:
    """PDF sin módulo ni gráfica predeterminados ni párrafos de advertencia."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    validar_informe(informe)
    _comprobar_png(ruta, informe)
    if not _tiene_contenido(informe):
        raise ValueError("Agrega texto, observaciones o imágenes antes de generar el PDF.")
    memoria = BytesIO()
    documento = SimpleDocTemplate(
        memoria,
        pagesize=A4,
        leftMargin=1.9 * cm,
        rightMargin=1.9 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=f"Informe técnico - {informe.proyecto}",
        author=informe.responsable or "WattWise",
    )
    estilo_info = ParagraphStyle(
        "datos_generales",
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        spaceAfter=7,
    )
    historia: list[Any] = [
        Paragraph(f"<b>Proyecto:</b> {_parrafo(informe.proyecto)}", estilo_info),
        Paragraph(f"<b>Responsable:</b> {_parrafo(informe.responsable)}", estilo_info),
        Paragraph(f"<b>Fecha:</b> {informe.fecha}", estilo_info),
        Spacer(1, 12),
    ]
    _cuerpo_pdf(historia, ruta, informe)
    documento.build(historia)
    return memoria.getvalue()
