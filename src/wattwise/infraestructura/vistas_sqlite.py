"""Persistencia de vistas reproducibles y eliminación múltiple segura."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from wattwise.dominio.vistas import GRAFICAS, validar_vista
from wattwise.infraestructura.archivos_proyecto import inicializar_archivos

MAXIMO_VISTAS_POR_PROYECTO = 100


@dataclass(frozen=True, slots=True)
class VistaGuardada:
    """Configuración de una vista asociada a un original inmutable."""

    id: int
    proyecto_id: int
    archivo_id: int
    tipo: str
    titulo: str
    configuracion: dict[str, object]
    sha256_archivo: str
    creado_utc: str


def _id(valor: int) -> None:
    """Acepta solo enteros positivos; bool no es un identificador."""
    if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
        raise ValueError("El identificador debe ser un entero positivo.")


def _conectar(ruta: Path) -> sqlite3.Connection:
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_vistas(ruta: Path) -> None:
    """Conserva la estructura existente y crea su índice si falta."""
    inicializar_archivos(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS vistas_guardadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                archivo_id INTEGER NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('inventario', 'motores', 'mediciones')),
                titulo TEXT NOT NULL CHECK(length(titulo) BETWEEN 1 AND 120),
                configuracion_json TEXT NOT NULL,
                sha256_archivo TEXT NOT NULL,
                creado_utc TEXT NOT NULL,
                FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE,
                FOREIGN KEY(archivo_id) REFERENCES archivos_originales(id) ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_vistas_proyecto "
            "ON vistas_guardadas(proyecto_id, id DESC)"
        )


def _huella_original(
    conexion: sqlite3.Connection,
    proyecto_id: int,
    archivo_id: int,
    tipo: str,
) -> str:
    fila = conexion.execute(
        "SELECT sha256 FROM archivos_originales WHERE id = ? AND proyecto_id = ? AND tipo = ?",
        (archivo_id, proyecto_id, tipo),
    ).fetchone()
    if fila is None:
        raise ValueError("El archivo no pertenece al proyecto y tipo seleccionados.")
    return str(fila[0])


def guardar_vista(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int,
    tipo: str,
    titulo: str,
    configuracion: dict[str, object],
) -> int:
    """Inserta una vista solo con fuente y contrato válidos."""
    _id(proyecto_id)
    _id(archivo_id)

    if not isinstance(tipo, str) or tipo not in GRAFICAS:
        raise ValueError("Tipo de vista no permitido.")

    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 120:
        raise ValueError("El titulo de la vista debe tener entre 1 y 120 caracteres.")

    normalizada = validar_vista(tipo, configuracion)
    datos = json.dumps(normalizada, ensure_ascii=False, sort_keys=True)
    inicializar_vistas(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        sha256 = _huella_original(conexion, proyecto_id, archivo_id, tipo)
        cantidad = conexion.execute(
            "SELECT COUNT(*) FROM vistas_guardadas WHERE proyecto_id = ?",
            (proyecto_id,),
        ).fetchone()[0]

        if cantidad >= MAXIMO_VISTAS_POR_PROYECTO:
            raise ValueError(
                f"Se alcanzo el limite de {MAXIMO_VISTAS_POR_PROYECTO} vistas del proyecto."
            )

        cursor = conexion.execute(
            "INSERT INTO vistas_guardadas "
            "(proyecto_id, archivo_id, tipo, titulo, configuracion_json, "
            "sha256_archivo, creado_utc) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                proyecto_id,
                archivo_id,
                tipo,
                titulo.strip(),
                datos,
                sha256,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )

        if cursor.lastrowid is None:
            raise RuntimeError("No fue posible identificar la vista guardada.")

        return int(cursor.lastrowid)


def _vista(fila: tuple[object, ...]) -> VistaGuardada:
    """Vuelve a validar configuraciones cargadas desde SQLite."""
    tipo = str(fila[3])
    configuracion = validar_vista(tipo, json.loads(str(fila[5])))

    return VistaGuardada(
        id=int(fila[0]),
        proyecto_id=int(fila[1]),
        archivo_id=int(fila[2]),
        tipo=tipo,
        titulo=str(fila[4]),
        configuracion=configuracion,
        sha256_archivo=str(fila[6]),
        creado_utc=str(fila[7]),
    )


def listar_vistas(ruta: Path, proyecto_id: int) -> list[VistaGuardada]:
    """Lista las vistas del proyecto sin mezclar registros ajenos."""
    _id(proyecto_id)
    inicializar_vistas(ruta)

    with closing(_conectar(ruta)) as conexion:
        filas = conexion.execute(
            "SELECT id, proyecto_id, archivo_id, tipo, titulo, "
            "configuracion_json, sha256_archivo, creado_utc "
            "FROM vistas_guardadas WHERE proyecto_id = ? ORDER BY id DESC",
            (proyecto_id,),
        ).fetchall()

    return [_vista(fila) for fila in filas]


def _identificador_sql(nombre: str) -> str:
    """Entrecomilla nombres de tablas y columnas leídos del esquema SQLite."""
    return '"' + nombre.replace('"', '""') + '"'


def _comprobar_dependencias(
    conexion: sqlite3.Connection,
    vista_ids: list[int],
) -> None:
    """Impide eliminar vistas que otras tablas realmente referencian."""
    marcas = ", ".join("?" for _ in vista_ids)
    tablas = conexion.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()

    for (nombre,) in tablas:
        if nombre == "vistas_guardadas":
            continue

        tabla = _identificador_sql(str(nombre))
        relaciones = conexion.execute(f"PRAGMA foreign_key_list({tabla})").fetchall()

        referidas = [relacion for relacion in relaciones if relacion[2] == "vistas_guardadas"]

        for relacion in referidas:
            if relacion[4] not in (None, "", "id"):
                raise ValueError("Existe una dependencia no compatible con el borrado.")

            columna = _identificador_sql(str(relacion[3]))

            existe = conexion.execute(
                f"SELECT 1 FROM {tabla} WHERE {columna} IN ({marcas}) LIMIT 1",
                vista_ids,
            ).fetchone()

            if existe is not None:
                raise ValueError(
                    "Alguna vista seleccionada está vinculada a otros registros. "
                    "Revisa esa relación antes de eliminarla."
                )


def eliminar_vistas(
    ruta: Path,
    proyecto_id: int,
    vista_ids: list[int],
) -> int:
    """Valida propiedad y dependencias, y elimina todo o nada."""
    _id(proyecto_id)

    if not isinstance(vista_ids, list) or not vista_ids:
        raise ValueError("Selecciona al menos una vista para eliminar.")

    if len(vista_ids) > MAXIMO_VISTAS_POR_PROYECTO:
        raise ValueError(
            f"La seleccion supera el limite de {MAXIMO_VISTAS_POR_PROYECTO} vistas del proyecto."
        )

    for vista_id in vista_ids:
        _id(vista_id)

    if len(set(vista_ids)) != len(vista_ids):
        raise ValueError("No repitas vistas en la selección.")

    inicializar_vistas(ruta)

    marcas = ", ".join("?" for _ in vista_ids)
    parametros = (proyecto_id, *vista_ids)

    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute("BEGIN IMMEDIATE")

        existentes = conexion.execute(
            f"SELECT id FROM vistas_guardadas WHERE proyecto_id = ? AND id IN ({marcas})",
            parametros,
        ).fetchall()

        if len(existentes) != len(vista_ids):
            raise ValueError("Alguna vista no existe o pertenece a otro proyecto.")

        _comprobar_dependencias(conexion, vista_ids)

        cursor = conexion.execute(
            f"DELETE FROM vistas_guardadas WHERE proyecto_id = ? AND id IN ({marcas})",
            parametros,
        )

        if cursor.rowcount != len(vista_ids):
            raise sqlite3.IntegrityError("No se pudo completar el borrado de todas las vistas.")

        return int(cursor.rowcount)


def eliminar_vista(
    ruta: Path,
    proyecto_id: int,
    vista_id: int,
) -> bool:
    """Compatibilidad con llamadas que eliminan una sola vista."""
    _id(proyecto_id)
    _id(vista_id)
    inicializar_vistas(ruta)

    with closing(_conectar(ruta)) as conexion:
        existe = conexion.execute(
            "SELECT 1 FROM vistas_guardadas WHERE proyecto_id = ? AND id = ?",
            (proyecto_id, vista_id),
        ).fetchone()

    if existe is None:
        return False

    return eliminar_vistas(ruta, proyecto_id, [vista_id]) == 1
