"""Persiste comparaciones confirmadas y huellas de los archivos fuente."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from wattwise.dominio.comparacion import ResultadoComparacion
from wattwise.infraestructura.archivos_proyecto import inicializar_archivos


@dataclass(frozen=True, slots=True)
class ComparacionGuardada:
    """Instantanea verificable con los IDs de sus archivos originales."""

    id: int
    proyecto_id: int
    inventario_id: int
    mediciones_id: int
    creado_utc: str
    areas: tuple[str, ...]
    resultado: dict[str, object]
    sha256_inventario: str
    sha256_mediciones: str


def _id(valor: int) -> None:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError("El ID debe ser entero positivo.")


def _conectar(ruta: Path) -> sqlite3.Connection:
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_comparaciones(ruta: Path) -> None:
    """Crea una tabla nueva sin modificar el esquema existente."""
    inicializar_archivos(ruta)
    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS comparaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                inventario_id INTEGER NOT NULL,
                mediciones_id INTEGER NOT NULL,
                creado_utc TEXT NOT NULL,
                areas_json TEXT NOT NULL,
                resultado_json TEXT NOT NULL,
                sha256_inventario TEXT NOT NULL,
                sha256_mediciones TEXT NOT NULL,
                FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE,
                FOREIGN KEY(inventario_id) REFERENCES archivos_originales(id) ON DELETE CASCADE,
                FOREIGN KEY(mediciones_id) REFERENCES archivos_originales(id) ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_comparaciones_proyecto "
            "ON comparaciones(proyecto_id, id DESC)"
        )


def _hash_fuente(
    conexion: sqlite3.Connection,
    proyecto_id: int,
    archivo_id: int,
    tipo: str,
) -> str:
    """Solo permite originales del proyecto y del tipo esperado."""
    fila = conexion.execute(
        "SELECT sha256 FROM archivos_originales WHERE proyecto_id = ? AND id = ? AND tipo = ?",
        (proyecto_id, archivo_id, tipo),
    ).fetchone()
    if fila is None:
        raise ValueError("El archivo fuente no pertenece al proyecto o tipo indicado.")
    return str(fila[0])


def _serializar_resultado(
    resultado: ResultadoComparacion,
    areas: tuple[str, ...],
) -> tuple[str, str]:
    """Valida alcance y limita el tamaño de la instantánea de resultados."""
    if not isinstance(resultado, ResultadoComparacion):
        raise ValueError("Debe proporcionarse una comparacion validada.")
    if not isinstance(areas, tuple) or not 1 <= len(areas) <= 200:
        raise ValueError("Selecciona areas validas para la comparacion.")
    if any(not isinstance(area, str) or not area.strip() for area in areas):
        raise ValueError("Selecciona areas validas para la comparacion.")

    contenido = asdict(resultado)
    contenido["primera_fecha"] = resultado.primera_fecha.isoformat()
    contenido["ultima_fecha"] = resultado.ultima_fecha.isoformat()

    datos_json = json.dumps(contenido, ensure_ascii=False, allow_nan=False)
    areas_json = json.dumps(list(areas), ensure_ascii=False)

    if len(datos_json.encode("utf-8")) > 16384 or len(areas_json.encode("utf-8")) > 4096:
        raise ValueError("La comparacion excede los limites de almacenamiento.")
    return datos_json, areas_json


def guardar_comparacion(
    ruta: Path,
    proyecto_id: int,
    inventario_id: int,
    mediciones_id: int,
    resultado: ResultadoComparacion,
    areas: tuple[str, ...],
) -> int:
    """Guarda evidencia, filtros y resumen, sin alterar los originales."""
    for identificador in (proyecto_id, inventario_id, mediciones_id):
        _id(identificador)

    datos_json, areas_json = _serializar_resultado(resultado, areas)
    inicializar_comparaciones(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        huella_inventario = _hash_fuente(conexion, proyecto_id, inventario_id, "inventario")
        huella_mediciones = _hash_fuente(conexion, proyecto_id, mediciones_id, "mediciones")
        cursor = conexion.execute(
            "INSERT INTO comparaciones "
            "(proyecto_id, inventario_id, mediciones_id, creado_utc, areas_json, "
            "resultado_json, sha256_inventario, sha256_mediciones) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                proyecto_id,
                inventario_id,
                mediciones_id,
                datetime.now(UTC).isoformat(timespec="seconds"),
                areas_json,
                datos_json,
                huella_inventario,
                huella_mediciones,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("No se obtuvo el identificador de la comparacion.")
        return cursor.lastrowid


def listar_comparaciones(ruta: Path, proyecto_id: int) -> list[ComparacionGuardada]:
    """Consulta historicos separados por proyecto, del mas nuevo al anterior."""
    _id(proyecto_id)
    inicializar_comparaciones(ruta)

    with closing(_conectar(ruta)) as conexion:
        filas = conexion.execute(
            "SELECT id, proyecto_id, inventario_id, mediciones_id, creado_utc, "
            "areas_json, resultado_json, sha256_inventario, sha256_mediciones "
            "FROM comparaciones WHERE proyecto_id = ? ORDER BY id DESC",
            (proyecto_id,),
        ).fetchall()

    return [
        ComparacionGuardada(
            id=fila[0],
            proyecto_id=fila[1],
            inventario_id=fila[2],
            mediciones_id=fila[3],
            creado_utc=fila[4],
            areas=tuple(json.loads(fila[5])),
            resultado=json.loads(fila[6]),
            sha256_inventario=fila[7],
            sha256_mediciones=fila[8],
        )
        for fila in filas
    ]
