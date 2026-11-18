"""Almacena capturas PNG de graficas por proyecto, con integridad y limites."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from wattwise.infraestructura.analisis_sqlite import inicializar_analisis

MAXIMO_PNG_BYTES = 5 * 1024 * 1024
MAXIMO_PIXELES = 12_000_000
MAXIMO_DIMENSION = 7000
MAXIMO_POR_PROYECTO = 50
MAXIMO_TOTAL_PROYECTO = 100 * 1024 * 1024
MAXIMO_DESCRIPCION = 500


@dataclass(frozen=True, slots=True)
class CapturaGrafica:
    """Metadatos verificados de una captura asociada a un proyecto."""

    id: int
    proyecto_id: int
    analisis_id: int | None
    nombre: str
    descripcion: str
    tamano_bytes: int
    sha256: str
    creado_utc: str


def _id(valor: int) -> None:
    """Exige identificadores positivos, sin aceptar booleanos."""
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError("El identificador debe ser entero positivo.")


def _nombre(nombre: str) -> str:
    """Rechaza nombres inseguros y extensiones distintas de PNG."""
    if (
        not isinstance(nombre, str)
        or not 1 <= len(nombre) <= 160
        or nombre != nombre.strip()
        or not nombre.lower().endswith(".png")
        or any(caracter in nombre for caracter in ("/", "\\", ":", "\x00"))
        or any(ord(caracter) < 32 for caracter in nombre)
    ):
        raise ValueError("Nombre PNG no permitido.")
    return nombre


def validar_png(contenido: bytes) -> tuple[int, int]:
    """Comprueba firma, contenido decodificable y dimensiones acotadas."""
    if (
        not isinstance(contenido, bytes)
        or not 0 < len(contenido) <= MAXIMO_PNG_BYTES
        or not contenido.startswith(b"\x89PNG\r\n\x1a\n")
    ):
        raise ValueError("Se requiere PNG valido de hasta 5 MiB.")
    try:
        with Image.open(BytesIO(contenido)) as imagen:
            if imagen.format != "PNG":
                raise ValueError("La imagen debe ser PNG autentico.")
            ancho, alto = imagen.size
            if (
                ancho < 1
                or alto < 1
                or ancho > MAXIMO_DIMENSION
                or alto > MAXIMO_DIMENSION
                or ancho * alto > MAXIMO_PIXELES
            ):
                raise ValueError("Dimensiones de imagen fuera del limite.")
            imagen.verify()
    except (OSError, UnidentifiedImageError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError("PNG corrupto o no decodificable.") from error
    return ancho, alto


def _conectar(ruta: Path) -> sqlite3.Connection:
    """Abre SQLite con integridad referencial activada."""
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_capturas(ruta: Path) -> None:
    """Crea un esquema nuevo sin transformar datos anteriores."""
    inicializar_analisis(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS capturas_graficas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                analisis_id INTEGER,
                nombre TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                tamano_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                creado_utc TEXT NOT NULL,
                contenido BLOB NOT NULL,
                FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE,
                FOREIGN KEY(analisis_id) REFERENCES analisis(id) ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_capturas_unicas "
            "ON capturas_graficas(proyecto_id, COALESCE(analisis_id, -1), sha256)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_capturas_proyecto "
            "ON capturas_graficas(proyecto_id, id DESC)"
        )


def _comprobar_destino(
    conexion: sqlite3.Connection, proyecto_id: int, analisis_id: int | None
) -> None:
    """Valida que el analisis pertenezca al mismo proyecto."""
    existe = conexion.execute("SELECT 1 FROM proyectos WHERE id = ?", (proyecto_id,)).fetchone()
    if existe is None:
        raise ValueError("El proyecto seleccionado no existe.")
    if analisis_id is not None:
        asociado = conexion.execute(
            "SELECT 1 FROM analisis WHERE id = ? AND proyecto_id = ?",
            (analisis_id, proyecto_id),
        ).fetchone()
        if asociado is None:
            raise ValueError("El analisis no pertenece al proyecto seleccionado.")


def guardar_captura(
    ruta: Path,
    proyecto_id: int,
    analisis_id: int | None,
    nombre: str,
    descripcion: str,
    contenido: bytes,
) -> int:
    """Guarda PNG original y deduplica contenido por proyecto y analisis."""
    _id(proyecto_id)
    if analisis_id is not None:
        _id(analisis_id)
    nombre = _nombre(nombre)
    if not isinstance(descripcion, str) or len(descripcion) > MAXIMO_DESCRIPCION:
        raise ValueError("Descripcion PNG no permitida.")
    validar_png(contenido)
    huella = hashlib.sha256(contenido).hexdigest()
    inicializar_capturas(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        _comprobar_destino(conexion, proyecto_id, analisis_id)
        repetido = conexion.execute(
            "SELECT id FROM capturas_graficas WHERE proyecto_id = ? "
            "AND analisis_id IS ? AND sha256 = ?",
            (proyecto_id, analisis_id, huella),
        ).fetchone()
        if repetido is not None:
            return int(repetido[0])
        cantidad, volumen = conexion.execute(
            "SELECT COUNT(*), COALESCE(SUM(tamano_bytes), 0) "
            "FROM capturas_graficas WHERE proyecto_id = ?",
            (proyecto_id,),
        ).fetchone()
        if cantidad >= MAXIMO_POR_PROYECTO or volumen + len(contenido) > MAXIMO_TOTAL_PROYECTO:
            raise ValueError("Limite de capturas del proyecto excedido.")
        cursor = conexion.execute(
            "INSERT INTO capturas_graficas "
            "(proyecto_id, analisis_id, nombre, descripcion, tamano_bytes, "
            "sha256, creado_utc, contenido) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                proyecto_id,
                analisis_id,
                nombre,
                descripcion.strip(),
                len(contenido),
                huella,
                datetime.now(UTC).isoformat(timespec="seconds"),
                sqlite3.Binary(contenido),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("No se pudo obtener el ID de la captura.")
        return cursor.lastrowid


def listar_capturas(ruta: Path, proyecto_id: int) -> list[CapturaGrafica]:
    """Lista metadatos de capturas sin cargar los datos binarios."""
    _id(proyecto_id)
    inicializar_capturas(ruta)
    with closing(_conectar(ruta)) as conexion:
        filas = conexion.execute(
            "SELECT id, proyecto_id, analisis_id, nombre, descripcion, tamano_bytes, "
            "sha256, creado_utc FROM capturas_graficas "
            "WHERE proyecto_id = ? ORDER BY id DESC",
            (proyecto_id,),
        ).fetchall()
    return [CapturaGrafica(*fila) for fila in filas]


def recuperar_captura(
    ruta: Path, proyecto_id: int, captura_id: int
) -> tuple[CapturaGrafica, bytes]:
    """Recupera exclusivamente una captura del proyecto y verifica su hash."""
    _id(proyecto_id)
    _id(captura_id)
    inicializar_capturas(ruta)
    with closing(_conectar(ruta)) as conexion:
        fila = conexion.execute(
            "SELECT id, proyecto_id, analisis_id, nombre, descripcion, tamano_bytes, "
            "sha256, creado_utc, contenido FROM capturas_graficas "
            "WHERE proyecto_id = ? AND id = ?",
            (proyecto_id, captura_id),
        ).fetchone()
    if fila is None:
        raise ValueError("Captura no encontrada en el proyecto seleccionado.")
    metadatos = CapturaGrafica(*fila[:8])
    contenido = bytes(fila[8])
    if (
        len(contenido) != metadatos.tamano_bytes
        or hashlib.sha256(contenido).hexdigest() != metadatos.sha256
    ):
        raise ValueError("Fallo de integridad SHA-256 de la captura.")
    validar_png(contenido)
    return metadatos, contenido


def eliminar_captura(ruta: Path, proyecto_id: int, captura_id: int) -> bool:
    """Borra una captura sin afectar otras notas, originales o analisis."""
    _id(proyecto_id)
    _id(captura_id)
    inicializar_capturas(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        cursor = conexion.execute(
            "DELETE FROM capturas_graficas WHERE proyecto_id = ? AND id = ?",
            (proyecto_id, captura_id),
        )
        return cursor.rowcount == 1
