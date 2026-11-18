"""Guarda libros originales de proyectos en SQLite con integridad SHA-256."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from wattwise.infraestructura.proyectos_sqlite import inicializar_proyectos

EXTENSIONES = {
    "inventario": frozenset({".xlsx"}),
    "mediciones": frozenset({".xlsx", ".csv"}),
    "motores": frozenset({".xlsx"}),
}
MAXIMO_ARCHIVO_BYTES = 25 * 1024 * 1024
MAXIMO_PROYECTO_BYTES = 250 * 1024 * 1024
MAXIMO_ARCHIVOS = 40


@dataclass(frozen=True, slots=True)
class ArchivoProyecto:
    """Metadatos de un original almacenado sin cambiar sus bytes."""

    id: int
    proyecto_id: int
    tipo: str
    nombre: str
    tamano_bytes: int
    sha256: str
    creado_utc: str


def _id(valor: int) -> None:
    """Verifica que el identificador no sea booleano ni no positivo."""
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError("El identificador debe ser un entero positivo.")


def _nombre_seguro(tipo: str, nombre: str) -> str:
    """Permite nombres de archivo simples y extensiones por modulo."""
    if tipo not in EXTENSIONES:
        raise ValueError("Tipo de archivo no permitido.")
    if not isinstance(nombre, str) or not 1 <= len(nombre) <= 180:
        raise ValueError("Nombre de archivo invalido.")
    if (
        nombre in {".", ".."}
        or nombre != nombre.strip()
        or any(c in nombre for c in ("/", "\\", ":", "\x00"))
        or any(ord(c) < 32 for c in nombre)
    ):
        raise ValueError("El nombre del archivo contiene caracteres no admitidos.")
    if Path(nombre).suffix.lower() not in EXTENSIONES[tipo]:
        raise ValueError("La extension no corresponde al tipo de analisis.")
    return nombre


def _validar_contenido(contenido: bytes) -> bytes:
    """Aplica un limite estricto y no interpreta el contenido del archivo."""
    if not isinstance(contenido, bytes) or not 0 < len(contenido) <= MAXIMO_ARCHIVO_BYTES:
        raise ValueError("El archivo debe contener entre 1 byte y 25 MiB.")
    return contenido


def _conectar(ruta: Path) -> sqlite3.Connection:
    """Abre la base local con integridad referencial y esperas limitadas."""
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_archivos(ruta: Path) -> None:
    """Crea almacenamiento de originales sin alterar tablas previas."""
    inicializar_proyectos(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS archivos_originales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('inventario', 'mediciones', 'motores')),
                nombre TEXT NOT NULL,
                tamano_bytes INTEGER NOT NULL CHECK(tamano_bytes BETWEEN 1 AND 26214400),
                sha256 TEXT NOT NULL,
                creado_utc TEXT NOT NULL,
                contenido BLOB NOT NULL,
                UNIQUE(proyecto_id, tipo, sha256),
                FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_originales_proyecto "
            "ON archivos_originales(proyecto_id, id DESC)"
        )


def guardar_archivo(
    ruta: Path,
    proyecto_id: int,
    tipo: str,
    nombre: str,
    contenido: bytes,
) -> int:
    """Inserta un original verificado por hash; evita duplicados exactos."""
    _id(proyecto_id)
    nombre = _nombre_seguro(tipo, nombre)
    contenido = _validar_contenido(contenido)
    huella = hashlib.sha256(contenido).hexdigest()
    inicializar_archivos(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        existe = conexion.execute("SELECT 1 FROM proyectos WHERE id = ?", (proyecto_id,)).fetchone()
        if existe is None:
            raise ValueError("El proyecto seleccionado no existe.")
        previo = conexion.execute(
            "SELECT id FROM archivos_originales WHERE proyecto_id = ? AND tipo = ? AND sha256 = ?",
            (proyecto_id, tipo, huella),
        ).fetchone()
        if previo is not None:
            return int(previo[0])
        cantidad, total = conexion.execute(
            "SELECT COUNT(*), COALESCE(SUM(tamano_bytes), 0) "
            "FROM archivos_originales WHERE proyecto_id = ?",
            (proyecto_id,),
        ).fetchone()
        if cantidad >= MAXIMO_ARCHIVOS or total + len(contenido) > MAXIMO_PROYECTO_BYTES:
            raise ValueError("El proyecto superaria sus limites de almacenamiento.")
        cursor = conexion.execute(
            "INSERT INTO archivos_originales "
            "(proyecto_id, tipo, nombre, tamano_bytes, sha256, creado_utc, contenido) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                proyecto_id,
                tipo,
                nombre,
                len(contenido),
                huella,
                datetime.now(UTC).isoformat(timespec="seconds"),
                sqlite3.Binary(contenido),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("No se obtuvo el identificador del original.")
        return cursor.lastrowid


def listar_archivos(ruta: Path, proyecto_id: int, tipo: str | None = None) -> list[ArchivoProyecto]:
    """Lista metadatos sin descargar los datos binarios del proyecto."""
    _id(proyecto_id)
    if tipo is not None and tipo not in EXTENSIONES:
        raise ValueError("Tipo de archivo no permitido.")
    inicializar_archivos(ruta)
    consulta = (
        "SELECT id, proyecto_id, tipo, nombre, tamano_bytes, sha256, creado_utc "
        "FROM archivos_originales WHERE proyecto_id = ?"
    )
    parametros: tuple[object, ...] = (proyecto_id,)
    if tipo is not None:
        consulta += " AND tipo = ?"
        parametros = (proyecto_id, tipo)
    consulta += " ORDER BY id DESC"
    with closing(_conectar(ruta)) as conexion:
        filas = conexion.execute(consulta, parametros).fetchall()
    return [ArchivoProyecto(*fila) for fila in filas]


def recuperar_archivo(
    ruta: Path, proyecto_id: int, archivo_id: int
) -> tuple[ArchivoProyecto, bytes]:
    """Recupera un archivo propio y comprueba tamano y huella antes de usarlo."""
    _id(proyecto_id)
    _id(archivo_id)
    inicializar_archivos(ruta)
    with closing(_conectar(ruta)) as conexion:
        fila = conexion.execute(
            "SELECT id, proyecto_id, tipo, nombre, tamano_bytes, sha256, creado_utc, contenido "
            "FROM archivos_originales WHERE id = ? AND proyecto_id = ?",
            (archivo_id, proyecto_id),
        ).fetchone()
    if fila is None:
        raise ValueError("Archivo no encontrado en el proyecto seleccionado.")
    metadatos = ArchivoProyecto(*fila[:7])
    contenido = bytes(fila[7])
    if (
        len(contenido) != metadatos.tamano_bytes
        or hashlib.sha256(contenido).hexdigest() != metadatos.sha256
    ):
        raise ValueError("El archivo almacenado no supera la verificacion de integridad.")
    return metadatos, contenido
