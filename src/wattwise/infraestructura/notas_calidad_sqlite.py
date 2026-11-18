"""Notas de calidad trazables por proyecto y archivo original verificado."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from wattwise.infraestructura.archivos_proyecto import inicializar_archivos

MAXIMO_NOTA = 2000


@dataclass(frozen=True, slots=True)
class NotaCalidad:
    """Observación humana recuperable sin atribuirle certeza automática."""

    id: int
    proyecto_id: int
    archivo_id: int
    tipo: str
    contenido: str
    sha256_archivo: str
    creado_utc: str


def _id(valor: int) -> None:
    """Rechaza identificadores vacíos y booleanos."""
    if type(valor) is not int or valor <= 0:
        raise ValueError("Se requiere un identificador positivo.")


def _conectar(ruta: Path) -> sqlite3.Connection:
    """Asegura relaciones y una espera máxima acotada en SQLite."""
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_notas_calidad(ruta: Path) -> None:
    """Añade la tabla sin alterar datos anteriores."""
    inicializar_archivos(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS notas_calidad (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                archivo_id INTEGER NOT NULL,
                tipo TEXT NOT NULL
                    CHECK(tipo IN ('inventario', 'mediciones', 'motores')),
                contenido TEXT NOT NULL,
                sha256_archivo TEXT NOT NULL,
                creado_utc TEXT NOT NULL,
                FOREIGN KEY(proyecto_id)
                    REFERENCES proyectos(id) ON DELETE CASCADE,
                FOREIGN KEY(archivo_id)
                    REFERENCES archivos_originales(id) ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_notas_calidad_proyecto "
            "ON notas_calidad(proyecto_id, archivo_id, id DESC)"
        )


def guardar_nota_calidad(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int,
    contenido: str,
) -> int:
    """Guarda texto humano solo si archivo y proyecto coinciden."""
    _id(proyecto_id)
    _id(archivo_id)

    if not isinstance(contenido, str) or not 1 <= len(contenido.strip()) <= MAXIMO_NOTA:
        raise ValueError("La nota debe tener entre 1 y 2000 caracteres.")

    inicializar_notas_calidad(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        fila = conexion.execute(
            "SELECT tipo, sha256 FROM archivos_originales WHERE id = ? AND proyecto_id = ?",
            (archivo_id, proyecto_id),
        ).fetchone()

        if fila is None:
            raise ValueError("El archivo no pertenece al proyecto seleccionado.")

        cursor = conexion.execute(
            "INSERT INTO notas_calidad "
            "(proyecto_id, archivo_id, tipo, contenido, "
            "sha256_archivo, creado_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                proyecto_id,
                archivo_id,
                fila[0],
                contenido.strip(),
                fila[1],
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )

        if cursor.lastrowid is None:
            raise RuntimeError("No se pudo identificar la nota guardada.")

        return int(cursor.lastrowid)


def listar_notas_calidad(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int | None = None,
) -> list[NotaCalidad]:
    """Recupera notas por proyecto con filtro opcional de archivo."""
    _id(proyecto_id)
    if archivo_id is not None:
        _id(archivo_id)

    inicializar_notas_calidad(ruta)
    consulta = (
        "SELECT id, proyecto_id, archivo_id, tipo, contenido, "
        "sha256_archivo, creado_utc "
        "FROM notas_calidad WHERE proyecto_id = ?"
    )
    parametros: tuple[int, ...] = (proyecto_id,)

    if archivo_id is not None:
        consulta += " AND archivo_id = ?"
        parametros = (proyecto_id, archivo_id)

    consulta += " ORDER BY id DESC"

    with closing(_conectar(ruta)) as conexion:
        filas = conexion.execute(consulta, parametros).fetchall()

    return [NotaCalidad(*fila) for fila in filas]


def eliminar_nota_calidad(
    ruta: Path,
    proyecto_id: int,
    nota_id: int,
) -> bool:
    """Elimina una nota únicamente desde su proyecto."""
    _id(proyecto_id)
    _id(nota_id)
    inicializar_notas_calidad(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        cursor = conexion.execute(
            "DELETE FROM notas_calidad WHERE id = ? AND proyecto_id = ?",
            (nota_id, proyecto_id),
        )
        return cursor.rowcount == 1
