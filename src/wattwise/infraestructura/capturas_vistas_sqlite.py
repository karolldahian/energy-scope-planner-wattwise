"""Almacena capturas ECharts y copias de notas sin alterar las vistas existentes."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from wattwise.infraestructura.observaciones_sqlite import Observacion
from wattwise.infraestructura.vistas_sqlite import inicializar_vistas

MAXIMO_ESTADO_BYTES = 12_000_000
MAXIMO_PNG_BYTES = 20_000_000
MAXIMO_NOTAS = 200
MAXIMO_NOTA = 2000
FIRMA_PNG = b"\x89PNG\r\n\x1a\n"
FINAL_PNG = b"\x00\x00\x00\x00IEND\xaeB`\x82"


@dataclass(frozen=True, slots=True)
class NotaCapturada:
    """Copia independiente de una observacion y su visibilidad."""

    texto: str
    mostrar_en_informe: bool


@dataclass(frozen=True, slots=True)
class CapturaVista:
    """Imagen y estado interactivo capturados para una vista ya guardada."""

    vista_id: int
    proyecto_id: int
    estado_echarts: dict[str, object]
    imagen_png: bytes
    notas: tuple[NotaCapturada, ...]
    incluir_en_informe: bool
    creado_utc: str


def _id(valor: int) -> None:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
        raise ValueError("El identificador debe ser un entero positivo.")


def _conexion(ruta: Path) -> sqlite3.Connection:
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_capturas_vistas(ruta: Path) -> None:
    """Crea almacenamiento complementario sin migrar la tabla de vistas."""
    inicializar_vistas(ruta)

    with closing(_conexion(ruta)) as conexion, conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS capturas_vistas (
                vista_id INTEGER PRIMARY KEY,
                proyecto_id INTEGER NOT NULL,
                estado_echarts_json TEXT NOT NULL,
                imagen_png BLOB NOT NULL,
                notas_json TEXT NOT NULL,
                incluir_en_informe INTEGER NOT NULL DEFAULT 1
                    CHECK(incluir_en_informe IN (0, 1)),
                creado_utc TEXT NOT NULL,
                FOREIGN KEY (proyecto_id)
                    REFERENCES proyectos(id) ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_capturas_vistas_proyecto "
            "ON capturas_vistas(proyecto_id, vista_id)"
        )

        # La eliminacion de una vista elimina su captura asociada.
        # No se usa una FK a vistas_guardadas porque su modulo anterior
        # bloquea el borrado de vistas que tienen tablas dependientes.
        conexion.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_borrar_captura_vista
            AFTER DELETE ON vistas_guardadas
            BEGIN
                DELETE FROM capturas_vistas WHERE vista_id = OLD.id;
            END
            """
        )


def _estado_json(estado: dict[str, object]) -> str:
    """Valida que el estado ECharts se pueda guardar como JSON."""
    if not isinstance(estado, dict) or not isinstance(estado.get("series"), list):
        raise ValueError("La captura requiere un estado ECharts con series.")

    if not estado["series"]:
        raise ValueError("La grafica capturada no contiene series.")

    try:
        contenido = json.dumps(
            estado,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("El estado ECharts no es JSON valido.") from error

    if len(contenido.encode("utf-8")) > MAXIMO_ESTADO_BYTES:
        raise ValueError("El estado ECharts supera el tamaño permitido.")

    return contenido


def _validar_png(imagen_png: bytes) -> bytes:
    """Comprueba firma, dimensiones basicas y terminacion del PNG."""
    if not isinstance(imagen_png, bytes):
        raise ValueError("La captura debe ser una imagen PNG en bytes.")

    if len(imagen_png) < 45 or len(imagen_png) > MAXIMO_PNG_BYTES:
        raise ValueError("El tamaño del PNG no es valido.")

    if not imagen_png.startswith(FIRMA_PNG) or not imagen_png.endswith(FINAL_PNG):
        raise ValueError("La imagen no tiene una estructura PNG reconocible.")

    if imagen_png[12:16] != b"IHDR" or imagen_png[8:12] != b"\x00\x00\x00\r":
        raise ValueError("La cabecera PNG no es valida.")

    ancho = int.from_bytes(imagen_png[16:20], "big")
    alto = int.from_bytes(imagen_png[20:24], "big")

    if not 1 <= ancho <= 10000 or not 1 <= alto <= 10000:
        raise ValueError("Las dimensiones del PNG no son validas.")

    return imagen_png


def _notas_json(notas: list[Observacion], proyecto_id: int) -> str:
    """Copia texto y permiso, sin depender de los IDs originales."""
    if not isinstance(notas, list) or len(notas) > MAXIMO_NOTAS:
        raise ValueError("La cantidad de observaciones no es valida.")

    copia: list[dict[str, object]] = []

    for nota in notas:
        if not isinstance(nota, Observacion) or nota.proyecto_id != proyecto_id:
            raise ValueError("La observacion no pertenece al proyecto de la vista.")

        if not isinstance(nota.texto, str) or not 1 <= len(nota.texto.strip()) <= MAXIMO_NOTA:
            raise ValueError("Una observacion tiene texto invalido.")

        if not isinstance(nota.mostrar_en_informe, bool):
            raise ValueError("Una observacion tiene una preferencia invalida.")

        copia.append(
            {
                "texto": nota.texto,
                "mostrar_en_informe": nota.mostrar_en_informe,
            }
        )

    return json.dumps(
        copia,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def guardar_captura_vista(
    ruta: Path,
    proyecto_id: int,
    vista_id: int,
    estado_echarts: dict[str, object],
    imagen_png: bytes,
    notas: list[Observacion],
) -> None:
    """Adjunta una captura congelada a una vista del mismo proyecto."""
    _id(proyecto_id)
    _id(vista_id)

    estado_json = _estado_json(estado_echarts)
    png = _validar_png(imagen_png)
    notas_json = _notas_json(notas, proyecto_id)

    inicializar_capturas_vistas(ruta)

    with closing(_conexion(ruta)) as conexion, conexion:
        conexion.execute("BEGIN IMMEDIATE")

        pertenece = conexion.execute(
            "SELECT 1 FROM vistas_guardadas WHERE id = ? AND proyecto_id = ?",
            (vista_id, proyecto_id),
        ).fetchone()

        if pertenece is None:
            raise ValueError("La vista no existe o pertenece a otro proyecto.")

        conexion.execute(
            "INSERT INTO capturas_vistas "
            "(vista_id, proyecto_id, estado_echarts_json, imagen_png, "
            "notas_json, incluir_en_informe, creado_utc) "
            "VALUES (?, ?, ?, ?, ?, 1, ?)",
            (
                vista_id,
                proyecto_id,
                estado_json,
                png,
                notas_json,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )


def recuperar_captura_vista(
    ruta: Path,
    proyecto_id: int,
    vista_id: int,
) -> CapturaVista | None:
    """Recupera la imagen y las notas tal como estaban al capturar."""
    _id(proyecto_id)
    _id(vista_id)

    inicializar_capturas_vistas(ruta)

    with closing(_conexion(ruta)) as conexion:
        fila = conexion.execute(
            "SELECT c.vista_id, c.proyecto_id, c.estado_echarts_json, "
            "c.imagen_png, c.notas_json, c.incluir_en_informe, c.creado_utc "
            "FROM capturas_vistas AS c "
            "JOIN vistas_guardadas AS v ON v.id = c.vista_id "
            "WHERE c.vista_id = ? AND c.proyecto_id = ? "
            "AND v.proyecto_id = ?",
            (vista_id, proyecto_id, proyecto_id),
        ).fetchone()

    if fila is None:
        return None

    notas = tuple(NotaCapturada(**nota) for nota in json.loads(fila[4]))

    return CapturaVista(
        vista_id=int(fila[0]),
        proyecto_id=int(fila[1]),
        estado_echarts=json.loads(fila[2]),
        imagen_png=bytes(fila[3]),
        notas=notas,
        incluir_en_informe=bool(fila[5]),
        creado_utc=str(fila[6]),
    )


def actualizar_inclusion_vista(
    ruta: Path,
    proyecto_id: int,
    vista_id: int,
    incluir_en_informe: bool,
) -> bool:
    """Activa o desactiva una captura para el futuro informe PDF."""
    _id(proyecto_id)
    _id(vista_id)

    if not isinstance(incluir_en_informe, bool):
        raise ValueError("Incluir en el informe debe ser verdadero o falso.")

    inicializar_capturas_vistas(ruta)

    with closing(_conexion(ruta)) as conexion, conexion:
        cursor = conexion.execute(
            "UPDATE capturas_vistas "
            "SET incluir_en_informe = ? "
            "WHERE proyecto_id = ? AND vista_id = ?",
            (
                int(incluir_en_informe),
                proyecto_id,
                vista_id,
            ),
        )
        return cursor.rowcount == 1
