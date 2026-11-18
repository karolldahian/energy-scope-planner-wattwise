"""Persiste notas técnicas ligadas a proyectos, gráficas y filtros."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from wattwise.infraestructura.proyectos_sqlite import inicializar_proyectos

MAXIMO_NOTA = 2000
MAXIMO_CONTEXTO = 4096
TIPOS = frozenset({"inventario", "mediciones", "motores", "comparacion"})


@dataclass(frozen=True, slots=True)
class Observacion:
    """Nota vinculada a un contexto, con permiso para el informe."""

    id: int
    proyecto_id: int
    tipo: str
    grafica: str
    contexto: dict[str, str]
    texto: str
    creado_utc: str
    mostrar_en_informe: bool = True


def _id(valor: int) -> None:
    """Rechaza identificadores inválidos, incluidos booleanos."""
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError("El ID debe ser un entero positivo.")


def _texto(valor: str, maximo: int) -> str:
    """Requiere texto no vacío y limitado."""
    if not isinstance(valor, str) or not 1 <= len(valor.strip()) <= maximo:
        raise ValueError("Texto vacío o excesivamente largo.")
    return valor.strip()


def _json_contexto(contexto: dict[str, str]) -> str:
    """Serializa un contexto simple y estable."""
    if not isinstance(contexto, dict) or not all(
        isinstance(clave, str) and isinstance(valor, str) for clave, valor in contexto.items()
    ):
        raise ValueError("El contexto debe contener campos y valores de texto.")

    contenido = json.dumps(
        contexto,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(contenido.encode("utf-8")) > MAXIMO_CONTEXTO:
        raise ValueError("El contexto supera el límite permitido.")
    return contenido


def _conectar(ruta: Path) -> sqlite3.Connection:
    """Abre SQLite con claves foráneas activas."""
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_observaciones(ruta: Path) -> None:
    """Crea o migra la tabla sin borrar notas anteriores."""
    inicializar_proyectos(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS observaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                grafica TEXT NOT NULL,
                contexto_json TEXT NOT NULL,
                texto TEXT NOT NULL,
                creado_utc TEXT NOT NULL,
                mostrar_en_informe INTEGER NOT NULL DEFAULT 1
                    CHECK(mostrar_en_informe IN (0, 1)),
                FOREIGN KEY (proyecto_id)
                    REFERENCES proyectos(id) ON DELETE CASCADE
            )
            """
        )

        columnas = {str(fila[1]) for fila in conexion.execute("PRAGMA table_info(observaciones)")}

        if "mostrar_en_informe" not in columnas:
            conexion.execute(
                "ALTER TABLE observaciones ADD COLUMN "
                "mostrar_en_informe INTEGER NOT NULL DEFAULT 1 "
                "CHECK(mostrar_en_informe IN (0, 1))"
            )

        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_notas_contexto "
            "ON observaciones(proyecto_id, tipo, grafica, id DESC)"
        )


def guardar_observacion(
    ruta: Path,
    proyecto_id: int,
    tipo: str,
    grafica: str,
    contexto: dict[str, str],
    texto: str,
    *,
    mostrar_en_informe: bool = True,
) -> int:
    """Guarda una nota manteniendo la firma anterior."""
    _id(proyecto_id)

    if tipo not in TIPOS:
        raise ValueError("Tipo de análisis desconocido.")

    if not isinstance(mostrar_en_informe, bool):
        raise ValueError("Mostrar en el informe debe ser verdadero o falso.")

    titulo = _texto(grafica, 120)
    nota = _texto(texto, MAXIMO_NOTA)
    filtros = _json_contexto(contexto)

    inicializar_observaciones(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        existe = conexion.execute(
            "SELECT 1 FROM proyectos WHERE id = ?",
            (proyecto_id,),
        ).fetchone()

        if existe is None:
            raise ValueError("El proyecto seleccionado no existe.")

        cursor = conexion.execute(
            "INSERT INTO observaciones "
            "(proyecto_id, tipo, grafica, contexto_json, texto, "
            "creado_utc, mostrar_en_informe) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                proyecto_id,
                tipo,
                titulo,
                filtros,
                nota,
                datetime.now(UTC).isoformat(),
                int(mostrar_en_informe),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("No se obtuvo el ID de la observación.")

        return int(cursor.lastrowid)


def listar_observaciones(
    ruta: Path,
    proyecto_id: int,
    tipo: str,
    grafica: str,
    contexto: dict[str, str],
) -> list[Observacion]:
    """Consulta notas del proyecto, gráfica y filtros exactos."""
    _id(proyecto_id)
    filtros = _json_contexto(contexto)
    inicializar_observaciones(ruta)

    with closing(_conectar(ruta)) as conexion:
        filas = conexion.execute(
            "SELECT id, proyecto_id, tipo, grafica, "
            "contexto_json, texto, creado_utc, mostrar_en_informe "
            "FROM observaciones "
            "WHERE proyecto_id = ? AND tipo = ? AND grafica = ? "
            "AND contexto_json = ? ORDER BY id DESC",
            (proyecto_id, tipo, grafica, filtros),
        ).fetchall()

    return [
        Observacion(
            id=fila[0],
            proyecto_id=fila[1],
            tipo=fila[2],
            grafica=fila[3],
            contexto=json.loads(fila[4]),
            texto=fila[5],
            creado_utc=fila[6],
            mostrar_en_informe=bool(fila[7]),
        )
        for fila in filas
    ]


def actualizar_visibilidad_observacion(
    ruta: Path,
    proyecto_id: int,
    observacion_id: int,
    mostrar_en_informe: bool,
) -> bool:
    """Cambia la visibilidad sin alterar el contenido de la nota."""
    _id(proyecto_id)
    _id(observacion_id)

    if not isinstance(mostrar_en_informe, bool):
        raise ValueError("Mostrar en el informe debe ser verdadero o falso.")

    inicializar_observaciones(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        cursor = conexion.execute(
            "UPDATE observaciones SET mostrar_en_informe = ? WHERE id = ? AND proyecto_id = ?",
            (
                int(mostrar_en_informe),
                observacion_id,
                proyecto_id,
            ),
        )
        return cursor.rowcount == 1


def eliminar_observacion(
    ruta: Path,
    proyecto_id: int,
    observacion_id: int,
) -> bool:
    """Elimina únicamente una nota del proyecto indicado."""
    _id(proyecto_id)
    _id(observacion_id)
    inicializar_observaciones(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        cursor = conexion.execute(
            "DELETE FROM observaciones WHERE id = ? AND proyecto_id = ?",
            (observacion_id, proyecto_id),
        )
        return cursor.rowcount == 1


def actualizar_observacion(
    ruta: Path,
    proyecto_id: int,
    observacion_id: int,
    texto: str,
) -> bool:
    """Edita una nota existente sin cambiar su proyecto ni sus filtros."""
    _id(proyecto_id)
    _id(observacion_id)
    nota = _texto(texto, MAXIMO_NOTA)
    inicializar_observaciones(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        cursor = conexion.execute(
            "UPDATE observaciones SET texto = ? WHERE id = ? AND proyecto_id = ?",
            (nota, observacion_id, proyecto_id),
        )
        return cursor.rowcount == 1


def listar_observaciones_modulo(
    ruta: Path,
    proyecto_id: int,
    tipo: str,
) -> list[Observacion]:
    """Lista notas que pueden recuperarse en Informes."""
    _id(proyecto_id)

    if tipo not in TIPOS:
        raise ValueError("El módulo de observaciones no existe.")

    inicializar_observaciones(ruta)

    with closing(_conectar(ruta)) as conexion:
        filas = conexion.execute(
            "SELECT id, proyecto_id, tipo, grafica, "
            "contexto_json, texto, creado_utc, mostrar_en_informe "
            "FROM observaciones WHERE proyecto_id = ? AND tipo = ? "
            "AND mostrar_en_informe = 1 ORDER BY id DESC LIMIT 100",
            (proyecto_id, tipo),
        ).fetchall()

    return [
        Observacion(
            id=fila[0],
            proyecto_id=fila[1],
            tipo=fila[2],
            grafica=fila[3],
            contexto=json.loads(fila[4]),
            texto=fila[5],
            creado_utc=fila[6],
            mostrar_en_informe=bool(fila[7]),
        )
        for fila in filas
    ]
