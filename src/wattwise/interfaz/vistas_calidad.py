"""Vistas de calidad aisladas del contrato de gráficas eléctricas de WattWise."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from wattwise.dominio.calidad_integral import InformeCalidad, auditar_excel
from wattwise.infraestructura.archivos_proyecto import (
    inicializar_archivos,
    recuperar_archivo,
)
from wattwise.infraestructura.notas_calidad_sqlite import (
    guardar_nota_calidad,
    listar_notas_calidad,
)

MAXIMO_VISTAS_CALIDAD = 100


@dataclass(frozen=True, slots=True)
class VistaCalidad:
    """Referencia verificable a una auditoría del archivo original."""

    id: int
    proyecto_id: int
    archivo_id: int
    titulo: str
    sha256_archivo: str
    creado_utc: str


def _id(valor: int) -> None:
    """Rechaza identificadores que no sean enteros positivos."""
    if type(valor) is not int or valor <= 0:
        raise ValueError("El identificador debe ser un entero positivo.")


def _conectar(ruta: Path) -> sqlite3.Connection:
    """Abre SQLite con integridad referencial habilitada."""
    conexion = sqlite3.connect(str(ruta), timeout=5)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 5000")
    return conexion


def inicializar_vistas_calidad(ruta: Path) -> None:
    """Crea una tabla nueva; no migra las vistas de gráficas existentes."""
    inicializar_archivos(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute(
            "CREATE TABLE IF NOT EXISTS vistas_calidad ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "proyecto_id INTEGER NOT NULL, "
            "archivo_id INTEGER NOT NULL, "
            "titulo TEXT NOT NULL CHECK(length(titulo) BETWEEN 1 AND 120), "
            "sha256_archivo TEXT NOT NULL, creado_utc TEXT NOT NULL, "
            "FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE, "
            "FOREIGN KEY(archivo_id) REFERENCES archivos_originales(id) ON DELETE CASCADE)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_vistas_calidad_proyecto "
            "ON vistas_calidad(proyecto_id, id DESC)"
        )


def guardar_vista_calidad(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int,
    titulo: str,
    informe: InformeCalidad,
) -> int:
    """Guarda la vista solo si la auditoría coincide con su archivo original."""
    _id(proyecto_id)
    _id(archivo_id)

    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 120:
        raise ValueError("El nombre de la vista debe tener entre 1 y 120 caracteres.")

    if not isinstance(informe, InformeCalidad):
        raise ValueError("La auditoría debe proceder del análisis de Calidad.")

    metadatos, _contenido = recuperar_archivo(
        ruta,
        proyecto_id,
        archivo_id,
    )

    if (
        not metadatos.nombre.lower().endswith(".xlsx")
        or informe.sha256 != metadatos.sha256
        or informe.tipo != metadatos.tipo
    ):
        raise ValueError("La auditoría no coincide con el Excel original verificado.")

    inicializar_vistas_calidad(ruta)

    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute("BEGIN IMMEDIATE")

        cantidad = conexion.execute(
            "SELECT COUNT(*) FROM vistas_calidad WHERE proyecto_id = ?",
            (proyecto_id,),
        ).fetchone()[0]

        if cantidad >= MAXIMO_VISTAS_CALIDAD:
            raise ValueError("Se alcanzó el máximo de vistas de calidad del proyecto.")

        cursor = conexion.execute(
            "INSERT INTO vistas_calidad "
            "(proyecto_id, archivo_id, titulo, sha256_archivo, creado_utc) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                proyecto_id,
                archivo_id,
                titulo.strip(),
                metadatos.sha256,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )

        if cursor.lastrowid is None:
            raise RuntimeError("No se obtuvo el identificador de la vista de calidad.")

        return int(cursor.lastrowid)


def listar_vistas_calidad(
    ruta: Path,
    proyecto_id: int,
) -> list[VistaCalidad]:
    """Lista solo las vistas de calidad del proyecto seleccionado."""
    _id(proyecto_id)
    inicializar_vistas_calidad(ruta)

    with closing(_conectar(ruta)) as conexion:
        filas = conexion.execute(
            "SELECT id, proyecto_id, archivo_id, titulo, sha256_archivo, creado_utc "
            "FROM vistas_calidad WHERE proyecto_id = ? ORDER BY id DESC",
            (proyecto_id,),
        ).fetchall()

    return [VistaCalidad(*fila) for fila in filas]


def eliminar_vistas_calidad(
    ruta: Path,
    proyecto_id: int,
    ids: list[int],
) -> int:
    """Elimina varias vistas del mismo proyecto sin borrar originales ni notas."""
    _id(proyecto_id)

    if not isinstance(ids, list) or not 1 <= len(ids) <= MAXIMO_VISTAS_CALIDAD:
        raise ValueError("Selecciona entre 1 y 100 vistas de calidad.")

    for identificador in ids:
        _id(identificador)

    if len(set(ids)) != len(ids):
        raise ValueError("No repitas identificadores de vistas.")

    inicializar_vistas_calidad(ruta)
    marcas = ",".join("?" for _ in ids)

    with closing(_conectar(ruta)) as conexion, conexion:
        conexion.execute("BEGIN IMMEDIATE")

        cantidad = conexion.execute(
            f"SELECT COUNT(*) FROM vistas_calidad WHERE proyecto_id = ? AND id IN ({marcas})",
            (proyecto_id, *ids),
        ).fetchone()[0]

        if cantidad != len(ids):
            raise ValueError("Alguna vista de calidad no pertenece al proyecto.")

        cursor = conexion.execute(
            f"DELETE FROM vistas_calidad WHERE proyecto_id = ? AND id IN ({marcas})",
            (proyecto_id, *ids),
        )

        if cursor.rowcount != len(ids):
            raise sqlite3.IntegrityError("No se completó la eliminación de las vistas.")

        return int(cursor.rowcount)


def mostrar_guardar_calidad_en_vistas(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int,
    informe: InformeCalidad,
    *,
    prefijo: str = "panel",
) -> None:
    """Ofrece nombrar y guardar la auditoría al final del panel Calidad."""
    import streamlit as st

    st.divider()
    st.markdown("#### Guardar análisis de calidad en Vistas")

    nombre = st.text_input(
        "Nombre de la vista",
        value=f"Calidad de datos · {informe.nombre}"[:120],
        max_chars=120,
        key=f"ww_calidad_nombre_vista_{prefijo}_{proyecto_id}_{archivo_id}",
    )

    if st.button(
        "Guardar análisis en Vistas",
        key=f"ww_calidad_guardar_vista_{prefijo}_{proyecto_id}_{archivo_id}",
    ):
        try:
            identificador = guardar_vista_calidad(
                ruta,
                proyecto_id,
                archivo_id,
                nombre,
                informe,
            )
            st.success(f"Análisis de calidad guardado en Vistas (#{identificador}).")
        except (ValueError, OSError, sqlite3.Error) as error:
            st.error(f"No se pudo guardar la vista de calidad: {error}")


def mostrar_notas_vista_calidad(
    ruta: Path,
    proyecto_id: int,
    archivo_id: int,
    clave: str,
) -> None:
    """Reutiliza notas del original con claves UI exclusivas de Vistas."""
    import streamlit as st

    st.markdown("#### Observaciones sobre la calidad de los datos")

    nota = st.text_area(
        "Nueva observación",
        max_chars=2000,
        key=f"ww_vista_calidad_nota_{clave}",
    )

    if st.button(
        "Guardar observación",
        key=f"ww_vista_calidad_nota_guardar_{clave}",
    ):
        try:
            guardar_nota_calidad(
                ruta,
                proyecto_id,
                archivo_id,
                nota,
            )
            st.success("Observación guardada para el Excel original.")
            st.rerun()
        except (ValueError, OSError, sqlite3.Error) as error:
            st.error(f"No se pudo guardar la observación: {error}")

    notas = listar_notas_calidad(
        ruta,
        proyecto_id,
        archivo_id,
    )

    if notas:
        with st.expander(f"Observaciones guardadas ({len(notas)})"):
            for posicion, item in enumerate(reversed(notas), start=1):
                st.markdown(f"**Nota {posicion}**")
                st.write(item.contenido)


def _mostrar_vista_calidad(
    ruta: Path,
    proyecto_id: int,
    vista: VistaCalidad,
) -> None:
    """Reaudita el archivo verificado y muestra resultados y notas actuales."""
    import streamlit as st

    metadatos, contenido = recuperar_archivo(
        ruta,
        proyecto_id,
        vista.archivo_id,
    )

    if metadatos.sha256 != vista.sha256_archivo:
        raise ValueError("El archivo original ya no coincide con la vista guardada.")

    informe = auditar_excel(
        metadatos.tipo,
        metadatos.nombre,
        contenido,
    )

    if informe.sha256 != vista.sha256_archivo:
        raise ValueError("No coincide el origen de la auditoría recuperada.")

    from wattwise.interfaz.panel_calidad_integral import _mostrar_informe

    st.markdown(f"#### {vista.titulo}")

    _mostrar_informe(
        informe,
        vista.archivo_id,
        prefijo=f"ww_vista_calidad_{vista.id}",
    )

    mostrar_notas_vista_calidad(
        ruta,
        proyecto_id,
        vista.archivo_id,
        str(vista.id),
    )


def mostrar_vistas_calidad(
    ruta: Path,
    proyecto_id: int,
) -> None:
    """Recupera y administra vistas de auditoría dentro de Vistas."""
    import streamlit as st

    vistas = listar_vistas_calidad(ruta, proyecto_id)

    if not vistas:
        return

    st.divider()
    st.markdown("### Análisis de calidad guardados")

    opciones = {f"{vista.titulo} · calidad #{vista.id}": vista for vista in vistas}

    seleccionada = st.selectbox(
        "Abrir análisis de calidad",
        list(opciones),
        key=f"ww_calidad_vista_{proyecto_id}",
    )

    with st.expander("Eliminar una o varias vistas de calidad"):
        elegidas = st.multiselect(
            "Vistas de calidad a eliminar",
            list(opciones),
            key=f"ww_calidad_vistas_eliminar_{proyecto_id}",
        )

        confirmar = st.checkbox(
            "Confirmar eliminación de las seleccionadas",
            key=f"ww_calidad_confirmar_{proyecto_id}",
        )

        if st.button(
            "Eliminar vistas seleccionadas",
            disabled=not confirmar or not elegidas,
            key=f"ww_calidad_eliminar_{proyecto_id}",
        ):
            try:
                cantidad = eliminar_vistas_calidad(
                    ruta,
                    proyecto_id,
                    [opciones[nombre].id for nombre in elegidas],
                )
                st.success(f"{cantidad} vistas eliminadas. Los originales y notas se conservan.")
                st.rerun()
            except (ValueError, OSError, sqlite3.Error) as error:
                st.error(f"No se pudieron eliminar las vistas: {error}")

    try:
        _mostrar_vista_calidad(
            ruta,
            proyecto_id,
            opciones[seleccionada],
        )
    except (ValueError, OSError, sqlite3.Error) as error:
        st.warning(f"No se pudo recuperar la auditoría: {error}")
