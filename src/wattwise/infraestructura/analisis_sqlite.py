"""Guarda instantaneas de analisis electricos asociadas a proyectos."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path

from wattwise.infraestructura.proyectos_sqlite import inicializar_proyectos

TIPOS = frozenset({"inventario", "mediciones", "motores"})
MAXIMO_JSON_BYTES = 512 * 1024
MAXIMO_TITULO = 120


@dataclass(frozen=True, slots=True)
class AnalisisGuardado:
    """Instantanea de resultados sin archivo binario original."""

    id: int
    proyecto_id: int
    tipo: str
    titulo: str
    creado_utc: str
    datos: dict[str, object]


def _validar_id(valor: int) -> None:
    """Evita identificadores booleanos, nulos y negativos."""
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError("El identificador debe ser entero positivo.")


def _normalizar(valor: object, profundidad: int = 0) -> object:
    """Acepta estructuras JSON finitas y limita su profundidad."""
    if profundidad > 12:
        raise ValueError("Estructura de analisis demasiado profunda.")
    if valor is None or isinstance(valor, (str, bool, int)):
        return valor
    if isinstance(valor, float):
        if not isfinite(valor):
            raise ValueError("No se admiten numeros no finitos.")
        return valor
    if isinstance(valor, (list, tuple)):
        return [_normalizar(item, profundidad + 1) for item in valor]
    if isinstance(valor, dict):
        if not all(isinstance(clave, str) for clave in valor):
            raise ValueError("Las claves deben ser texto.")
        return {clave: _normalizar(item, profundidad + 1) for clave, item in valor.items()}
    raise ValueError("Los resultados deben contener solo datos JSON.")


def _serializar(datos: dict[str, object]) -> str:
    """Valida el contenido y evita valores JSON no estandar."""
    if not isinstance(datos, dict) or not datos:
        raise ValueError("Los resultados deben ser un diccionario no vacio.")
    contenido = json.dumps(
        _normalizar(datos),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    if len(contenido.encode("utf-8")) > MAXIMO_JSON_BYTES:
        raise ValueError("El analisis supera el limite de 512 KiB.")
    return contenido


def _conectar(ruta: Path) -> sqlite3.Connection:
    """Abre conexiones con integridad referencial habilitada."""
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_analisis(ruta: Path) -> None:
    """Prepara el esquema sin modificar proyectos existentes."""
    inicializar_proyectos(ruta)
    with _conectar(ruta) as conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS analisis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('inventario', 'mediciones', 'motores')),
                titulo TEXT NOT NULL CHECK(length(titulo) BETWEEN 1 AND 120),
                creado_utc TEXT NOT NULL,
                datos_json TEXT NOT NULL,
                FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_analisis_proyecto ON analisis(proyecto_id, id DESC)"
        )


def guardar_analisis(
    ruta: Path,
    proyecto_id: int,
    tipo: str,
    titulo: str,
    datos: dict[str, object],
) -> int:
    """Guarda una instantanea solo para un proyecto existente."""
    _validar_id(proyecto_id)
    if tipo not in TIPOS:
        raise ValueError("Tipo de analisis no permitido.")
    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= MAXIMO_TITULO:
        raise ValueError("Titulo no valido.")
    contenido = _serializar(datos)
    inicializar_analisis(ruta)
    fecha = datetime.now(UTC).isoformat(timespec="seconds")
    with _conectar(ruta) as conexion:
        existe = conexion.execute("SELECT 1 FROM proyectos WHERE id = ?", (proyecto_id,)).fetchone()
        if existe is None:
            raise ValueError("El proyecto seleccionado no existe.")
        cursor = conexion.execute(
            "INSERT INTO analisis "
            "(proyecto_id, tipo, titulo, creado_utc, datos_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (proyecto_id, tipo, titulo.strip(), fecha, contenido),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("No se obtuvo el ID del analisis.")
        return cursor.lastrowid


def listar_analisis(ruta: Path, proyecto_id: int) -> list[AnalisisGuardado]:
    """Lista las instantaneas de un solo proyecto."""
    _validar_id(proyecto_id)
    inicializar_analisis(ruta)
    with _conectar(ruta) as conexion:
        filas = conexion.execute(
            "SELECT id, proyecto_id, tipo, titulo, creado_utc, datos_json "
            "FROM analisis WHERE proyecto_id = ? ORDER BY id DESC",
            (proyecto_id,),
        ).fetchall()
    return [AnalisisGuardado(*fila[:5], json.loads(fila[5])) for fila in filas]
