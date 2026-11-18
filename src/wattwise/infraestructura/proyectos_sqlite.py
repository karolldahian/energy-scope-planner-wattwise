"""Persistencia local SQLite de metadatos de proyectos de WattWise."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Proyecto:
    """Proyecto guardado localmente sin almacenar datos electricos aun."""

    id: int
    nombre: str
    descripcion: str
    creado_utc: str


def _validar_texto(valor: str, campo: str, limite: int, *, requerido: bool) -> str:
    """Valida el texto antes de tocar la base de datos."""
    if not isinstance(valor, str):
        raise ValueError(f"{campo} debe ser texto.")
    limpio = valor.strip()
    if len(limpio) > limite or (requerido and not limpio):
        raise ValueError(f"{campo} tiene longitud no permitida.")
    if any(ord(caracter) < 32 and caracter not in "\n\t" for caracter in limpio):
        raise ValueError(f"{campo} contiene caracteres de control.")
    return limpio


def _conectar(ruta: Path) -> sqlite3.Connection:
    """Abre una base local existente o crea sus carpetas."""
    ruta = Path(ruta)
    if ruta.exists() and not ruta.is_file():
        raise ValueError("La ruta de la base de datos no es un archivo.")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA busy_timeout = 5000")
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def inicializar_proyectos(ruta: Path) -> None:
    """Crea la tabla local de proyectos si no existe."""
    with _conectar(ruta) as conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS proyectos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL CHECK(length(nombre) BETWEEN 1 AND 120),
                descripcion TEXT NOT NULL CHECK(length(descripcion) <= 1000),
                creado_utc TEXT NOT NULL
            )
            """
        )


def crear_proyecto(ruta: Path, nombre: str, descripcion: str = "") -> int:
    """Guarda los metadatos y devuelve el identificador creado."""
    nombre = _validar_texto(nombre, "nombre", 120, requerido=True)
    descripcion = _validar_texto(descripcion, "descripcion", 1000, requerido=False)
    inicializar_proyectos(ruta)
    creado = datetime.now(UTC).isoformat(timespec="seconds")
    with _conectar(ruta) as conexion:
        cursor = conexion.execute(
            "INSERT INTO proyectos (nombre, descripcion, creado_utc) VALUES (?, ?, ?)",
            (nombre, descripcion, creado),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("No se obtuvo el identificador del proyecto.")
        return cursor.lastrowid


def listar_proyectos(ruta: Path) -> list[Proyecto]:
    """Consulta proyectos del mas reciente al mas antiguo."""
    inicializar_proyectos(ruta)
    with _conectar(ruta) as conexion:
        filas = conexion.execute(
            "SELECT id, nombre, descripcion, creado_utc FROM proyectos ORDER BY id DESC"
        ).fetchall()
    return [Proyecto(*fila) for fila in filas]


def eliminar_proyecto(ruta: Path, proyecto_id: int) -> bool:
    """Elimina un proyecto por su identificador, con parametros SQL."""
    if isinstance(proyecto_id, bool) or not isinstance(proyecto_id, int):
        raise ValueError("El identificador debe ser un entero positivo.")
    if proyecto_id <= 0:
        raise ValueError("El identificador debe ser un entero positivo.")
    inicializar_proyectos(ruta)
    with _conectar(ruta) as conexion:
        cursor = conexion.execute("DELETE FROM proyectos WHERE id = ?", (proyecto_id,))
        return cursor.rowcount == 1
