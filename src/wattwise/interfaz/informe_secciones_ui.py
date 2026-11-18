"""Constructor sencillo de informes con imágenes y notas elegidas por casillas."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from wattwise.infraestructura.capturas_sqlite import (
    guardar_captura,
    recuperar_captura,
    validar_png,
)
from wattwise.infraestructura.informe_libre import (
    MAXIMO_ANALISIS,
    MAXIMO_BLOQUES,
    AnalisisLibre,
    BloqueLibre,
    InformeLibre,
    generar_pdf_libre,
    guardar_informe_libre,
    recuperar_informe_libre,
)
from wattwise.infraestructura.informe_por_secciones import recuperar_borrador_informe
from wattwise.infraestructura.notas_calidad_sqlite import listar_notas_calidad
from wattwise.infraestructura.observaciones_sqlite import inicializar_observaciones
from wattwise.infraestructura.proyectos_sqlite import Proyecto, listar_proyectos

_CATEGORIAS = (
    "Inventarios",
    "Mediciones",
    "Motores",
    "Calidad de datos",
)
_ORIGEN_NOTA = "wwnota:"
_ORIGEN_COMPARTIDA = "wwcompartida:"


@dataclass(frozen=True, slots=True)
class NotaDisponible:
    """Observación de un proyecto, con identidad estable para las casillas."""

    clave: str
    categoria: str
    grafica: str
    texto: str


def _nueva_clave() -> str:
    return uuid4().hex


def _bloque(tipo: str, texto: str = "", **cambios: object) -> dict[str, object]:
    """Crea un bloque compatible con el almacenamiento existente."""
    datos = asdict(BloqueLibre(clave=_nueva_clave(), tipo=tipo, texto=texto))
    datos.update(cambios)
    return datos


def _analisis_nuevo() -> dict[str, object]:
    return {"clave": _nueva_clave(), "titulo": "", "bloques": []}


def _desde_heredado(ruta: Path, proyecto: Proyecto) -> dict[str, object]:
    """Importa el texto anterior sin modificar su tabla de origen."""
    anterior = recuperar_borrador_informe(ruta, proyecto.id)
    if anterior is None:
        return {
            "proyecto_id": proyecto.id,
            "proyecto": proyecto.nombre,
            "responsable": "",
            "fecha": date.today().isoformat(),
            "introduccion": [],
            "analisis": [_analisis_nuevo()],
        }

    analisis = []
    for item in anterior.analisis:
        bloques = []
        if item.incluir_grafica and item.captura_id is not None:
            bloques.append(_bloque("imagen", captura_id=item.captura_id))
        if item.incluir_observacion and item.observacion.strip():
            bloques.append(_bloque("observacion", item.observacion))
        analisis.append({"clave": item.clave, "titulo": item.titulo, "bloques": bloques})

    return {
        "proyecto_id": proyecto.id,
        "proyecto": anterior.nombre,
        "responsable": anterior.responsable,
        "fecha": anterior.fecha,
        "introduccion": (
            [_bloque("texto", anterior.descripcion)] if anterior.descripcion.strip() else []
        ),
        "analisis": analisis or [_analisis_nuevo()],
    }


def _estado(ruta: Path, proyecto: Proyecto) -> tuple[str, dict[str, object]]:
    import streamlit as st

    clave = f"ww_informes_libres_{proyecto.id}"
    if clave not in st.session_state:
        guardado = recuperar_informe_libre(ruta, proyecto.id)
        st.session_state[clave] = (
            json.loads(json.dumps(asdict(guardado), ensure_ascii=False))
            if guardado is not None
            else _desde_heredado(ruta, proyecto)
        )
    return clave, st.session_state[clave]


def _generales(estado: dict[str, object], clave: str) -> None:
    """Muestra únicamente los tres datos generales acordados."""
    import streamlit as st

    st.subheader("Datos generales")
    st.session_state.setdefault(f"{clave}_proyecto", estado["proyecto"])
    estado["proyecto"] = st.text_input("Proyecto", max_chars=120, key=f"{clave}_proyecto")

    a, b = st.columns(2)
    with a:
        st.session_state.setdefault(f"{clave}_responsable", estado["responsable"])
        estado["responsable"] = st.text_input(
            "Responsable", max_chars=120, key=f"{clave}_responsable"
        )
    with b:
        st.session_state.setdefault(f"{clave}_fecha", date.fromisoformat(str(estado["fecha"])))
        estado["fecha"] = st.date_input("Fecha", key=f"{clave}_fecha").isoformat()


def _textos_existentes(bloques: list[dict[str, object]]) -> tuple[str, str]:
    """Conserva el texto heredado al simplificar el editor en dos campos."""
    titulos = []
    parrafos = []
    for bloque in bloques:
        if bloque["tipo"] not in ("texto", "observacion") or not bloque["texto"].strip():
            continue
        destino = titulos if bloque["estilo"] in ("Título", "Subtítulo") else parrafos
        destino.append(bloque["texto"].strip())
    return "\n".join(titulos), "\n\n".join(parrafos)


def _bloque_texto(clave: str, contexto: str, texto: str, *, titulo: bool) -> dict[str, object]:
    """Mantiene identificadores estables aunque Streamlit vuelva a ejecutarse."""
    identificador = uuid5(NAMESPACE_URL, f"{clave}:{contexto}:{titulo}").hex
    return asdict(
        BloqueLibre(
            clave=identificador,
            tipo="texto",
            texto=texto,
            estilo="Título" if titulo else "Párrafo",
            tamano=18 if titulo else 11,
            negrilla=titulo,
        )
    )


def _introduccion(estado: dict[str, object], clave: str) -> None:
    """Un único panel con título opcional y texto libre."""
    import streamlit as st

    titulo, cuerpo = _textos_existentes(estado["introduccion"])
    st.subheader("Introducción libre")
    st.caption("Sin título obligatorio; el título aparecerá en negrilla en el PDF.")

    with st.container(border=True):
        st.session_state.setdefault(f"{clave}_intro_titulo", titulo)
        st.session_state.setdefault(f"{clave}_intro_texto", cuerpo)
        titulo = st.text_input("Título (opcional)", max_chars=200, key=f"{clave}_intro_titulo")
        cuerpo = st.text_area("Texto", max_chars=5000, key=f"{clave}_intro_texto", height=170)

    estado["introduccion"] = [
        bloque
        for bloque in (
            _bloque_texto(clave, "intro-titulo", titulo, titulo=True),
            _bloque_texto(clave, "intro-texto", cuerpo, titulo=False),
        )
        if str(bloque["texto"]).strip()
    ]


def _catalogo_notas(ruta: Path, proyecto_id: int) -> dict[str, NotaDisponible]:
    """Recupera todas las observaciones por categoría del proyecto activo."""
    inicializar_observaciones(ruta)
    with sqlite3.connect(ruta, timeout=5) as conexion:
        filas = conexion.execute(
            "SELECT id, tipo, grafica, texto FROM observaciones "
            "WHERE proyecto_id = ? AND tipo IN ('inventario', 'mediciones', 'motores') "
            "ORDER BY id DESC",
            (proyecto_id,),
        ).fetchall()

    categorias = {
        "inventario": "Inventarios",
        "mediciones": "Mediciones",
        "motores": "Motores",
    }
    notas = {
        f"{tipo}:{identificador}": NotaDisponible(
            clave=f"{tipo}:{identificador}",
            categoria=categorias[tipo],
            grafica=grafica,
            texto=texto,
        )
        for identificador, tipo, grafica, texto in filas
    }
    for nota in listar_notas_calidad(ruta, proyecto_id):
        clave = f"calidad:{nota.id}"
        notas[clave] = NotaDisponible(
            clave=clave,
            categoria="Calidad de datos",
            grafica=f"Archivo #{nota.archivo_id}",
            texto=nota.contenido,
        )
    return notas


def _notas_del_proyecto(ruta: Path, proyecto_id: int) -> dict[str, str]:
    """Mantiene la consulta existente para integraciones y pruebas anteriores."""
    return {
        f"{nota.categoria} · {nota.grafica} · {nota.clave}": nota.texto
        for nota in _catalogo_notas(ruta, proyecto_id).values()
    }


def _enriquecer_notas(
    analisis: dict[str, object], catalogo: dict[str, NotaDisponible]
) -> dict[str, NotaDisponible]:
    """Ofrece únicamente notas existentes en las pestañas del proyecto.

    No convierte textos heredados del borrador en una categoría inventada.
    Las notas creadas desde Vistas se registran en su módulo eléctrico original.
    """
    _ = analisis
    return dict(catalogo)


def _notas_previas(analisis: dict[str, object]) -> dict[str, set[str]]:
    """Recupera la selección de notas por imagen, incluidos borradores antiguos.

    Las notas compartidas antiguas quedan asociadas a la última imagen en que
    aparecían para poder desmarcarlas sin mostrar otro panel de observaciones.
    """
    por_imagen: dict[str, set[str]] = {}
    imagen_actual: str | None = None
    previas_sin_imagen: set[str] = set()

    for bloque in analisis["bloques"]:
        if bloque["tipo"] == "imagen":
            imagen_actual = str(bloque["clave"])
            por_imagen.setdefault(imagen_actual, set())
        elif bloque["tipo"] == "observacion":
            nombre = str(bloque.get("nombre") or "")
            if nombre.startswith(_ORIGEN_NOTA):
                token = nombre[len(_ORIGEN_NOTA) :]
            elif nombre.startswith(_ORIGEN_COMPARTIDA):
                token = nombre[len(_ORIGEN_COMPARTIDA) :]
            else:
                token = f"borrador:{bloque['clave']}"

            if imagen_actual is None:
                previas_sin_imagen.add(token)
            else:
                por_imagen[imagen_actual].add(token)

    if previas_sin_imagen and por_imagen:
        primera_imagen = next(iter(por_imagen))
        por_imagen[primera_imagen].update(previas_sin_imagen)

    return por_imagen


def _selector_notas(
    catalogo: dict[str, NotaDisponible],
    previas: set[str],
    clave: str,
) -> list[str]:
    """Ofrece casillas por módulo, más la opción explícita Ninguna."""
    import streamlit as st

    sin_notas = st.checkbox(
        "Ninguna (no incluir observaciones)",
        value=not bool(previas),
        key=f"{clave}_ninguna",
    )
    elegidas = []

    for categoria in _CATEGORIAS:
        notas = [n for n in catalogo.values() if n.categoria == categoria]
        if not notas:
            continue
        with st.expander(f"{categoria} ({len(notas)})"):
            for nota in notas:
                campo = f"{clave}_nota_{hashlib.sha256(nota.clave.encode()).hexdigest()[:16]}"
                if sin_notas:
                    # Se restablece antes de construir la casilla, no después.
                    st.session_state[campo] = False
                elegida = st.checkbox(
                    f"{nota.grafica} · {nota.texto[:100]}",
                    value=nota.clave in previas,
                    disabled=sin_notas,
                    key=campo,
                )
                if elegida and not sin_notas:
                    elegidas.append(nota.clave)
                st.caption(nota.texto)

    return elegidas


def _bloque_nota(
    analisis_id: str,
    destino: str,
    token: str,
    nota: NotaDisponible,
) -> dict[str, object]:
    """Copia cada observación solo en la ubicación elegida del informe."""
    identificador = uuid5(NAMESPACE_URL, f"{analisis_id}:{destino}:{token}").hex
    nombre = f"{_ORIGEN_COMPARTIDA}{token}" if destino == "general" else f"{_ORIGEN_NOTA}{token}"
    return asdict(
        BloqueLibre(
            clave=identificador,
            tipo="observacion",
            texto=nota.texto,
            nombre=nombre,
        )
    )


def _anexar_png(
    ruta: Path, proyecto_id: int, analisis: dict[str, object], archivos: list[object]
) -> None:
    """Agrega PNG automáticamente al seleccionarlos, sin botón adicional."""
    imagenes = [b for b in analisis["bloques"] if b["tipo"] == "imagen"]
    huellas = set()
    for imagen in imagenes:
        meta, _contenido = recuperar_captura(ruta, proyecto_id, imagen["captura_id"])
        huellas.add(meta.sha256)

    nuevos = []
    for archivo in archivos:
        contenido = archivo.getvalue()
        validar_png(contenido)
        huella = hashlib.sha256(contenido).hexdigest()
        if huella not in huellas:
            nuevos.append((archivo.name, contenido))
            huellas.add(huella)

    if len(analisis["bloques"]) + len(nuevos) > MAXIMO_BLOQUES:
        raise ValueError("Se alcanzó el máximo de elementos del análisis.")

    for nombre, contenido in nuevos:
        captura_id = guardar_captura(ruta, proyecto_id, None, nombre, "", contenido)
        analisis["bloques"].append(_bloque("imagen", captura_id=captura_id, nombre=nombre))


def _texto_analisis(analisis: dict[str, object], clave: str) -> dict[str, object]:
    """Condensa textos anteriores en un único campo sin perder su contenido."""
    import streamlit as st

    textos = [
        str(item["texto"])
        for item in analisis["bloques"]
        if item["tipo"] == "texto" and str(item["texto"]).strip()
    ]
    st.session_state.setdefault(f"{clave}_texto", "\n\n".join(textos))
    cuerpo = st.text_area(
        "Texto del análisis (opcional)",
        max_chars=5000,
        height=115,
        key=f"{clave}_texto",
    )
    return _bloque_texto(clave, "texto-analisis", cuerpo, titulo=False)


def _imagen_y_notas(
    ruta: Path,
    proyecto_id: int,
    imagen: dict[str, object],
    catalogo: dict[str, NotaDisponible],
    anteriores: set[str],
    clave: str,
) -> tuple[dict[str, object], list[str], bool]:
    """Muestra una imagen y, al lado, las notas que pueden acompañarla."""
    import streamlit as st

    imagen_id = str(imagen["clave"])
    prefijo = f"{clave}_{imagen_id}"
    a, b = st.columns([3, 2], gap="large")

    with a:
        _metadatos, contenido = recuperar_captura(ruta, proyecto_id, imagen["captura_id"])
        st.image(contenido, caption=imagen["nombre"], use_container_width=True)
        st.session_state.setdefault(f"{prefijo}_nombre", imagen["nombre"])
        imagen["nombre"] = st.text_input(
            "Pie de imagen (opcional)", max_chars=160, key=f"{prefijo}_nombre"
        )
        quitar = st.checkbox("Quitar esta imagen", key=f"{prefijo}_quitar", value=False)

    with b:
        st.markdown("**Observaciones para esta imagen**")
        seleccion = _selector_notas(catalogo, anteriores, prefijo)

    return imagen, seleccion, quitar


def _quitar_imagen(analisis: dict[str, object], imagen_id: str) -> None:
    """Retira solo la imagen y las notas asignadas a ella, no las compartidas."""
    restante = []
    omitir_notas = False
    for bloque in analisis["bloques"]:
        if bloque["tipo"] == "imagen":
            omitir_notas = str(bloque["clave"]) == imagen_id
            if omitir_notas:
                continue
        if (
            omitir_notas
            and bloque["tipo"] == "observacion"
            and str(bloque.get("nombre") or "").startswith(_ORIGEN_NOTA)
        ):
            continue
        restante.append(bloque)
    analisis["bloques"] = restante


def _analisis_visual(
    ruta: Path,
    proyecto_id: int,
    analisis: dict[str, object],
    clave: str,
    catalogo: dict[str, NotaDisponible],
) -> None:
    """Un panel por análisis; las casillas forman automáticamente el PDF."""
    import streamlit as st

    st.session_state.setdefault(f"{clave}_titulo", analisis["titulo"])
    analisis["titulo"] = st.text_input("Título del análisis", max_chars=120, key=f"{clave}_titulo")
    texto = _texto_analisis(analisis, clave)
    st.markdown("**Gráficas del análisis**")
    revision = int(analisis.get("revision_uploader", 0))
    archivos = st.file_uploader(
        "Selecciona una o varias imágenes PNG",
        type=["png"],
        accept_multiple_files=True,
        key=f"{clave}_png_{revision}",
    )
    _anexar_png(ruta, proyecto_id, analisis, archivos or [])

    disponibles = _enriquecer_notas(analisis, catalogo)
    por_imagen = _notas_previas(analisis)
    imagenes = [b for b in analisis["bloques"] if b["tipo"] == "imagen"]
    nuevos_bloques = [texto] if str(texto["texto"]).strip() else []

    for indice, imagen in enumerate(imagenes, start=1):
        st.markdown(f"**Imagen {indice}**")
        with st.container(border=True):
            actualizado, elegidas, quitar = _imagen_y_notas(
                ruta,
                proyecto_id,
                imagen,
                disponibles,
                por_imagen.get(str(imagen["clave"]), set()),
                clave,
            )
        if quitar:
            _quitar_imagen(analisis, str(imagen["clave"]))
            analisis["revision_uploader"] = revision + 1
            st.rerun()

        nuevos_bloques.append(actualizado)
        for token in elegidas:
            nuevos_bloques.append(
                _bloque_nota(
                    str(analisis["clave"]),
                    str(imagen["clave"]),
                    token,
                    disponibles[token],
                )
            )

    if len(nuevos_bloques) > MAXIMO_BLOQUES:
        raise ValueError("Demasiadas observaciones o imágenes en un análisis.")
    analisis["bloques"] = nuevos_bloques


def _mostrar_analisis(
    ruta: Path,
    proyecto_id: int,
    estado: dict[str, object],
    clave: str,
    catalogo: dict[str, NotaDisponible],
) -> None:
    """Reduce controles a título, texto, imágenes y selección por casillas."""
    import streamlit as st

    for indice, analisis in enumerate(estado["analisis"], start=1):
        prefijo = f"{clave}_{analisis['clave']}"
        with st.container(border=True):
            st.subheader(f"Análisis {indice}")
            _analisis_visual(ruta, proyecto_id, analisis, prefijo, catalogo)
            if st.checkbox("Quitar este análisis del borrador", key=f"{prefijo}_eliminar"):
                estado["analisis"].pop(indice - 1)
                st.rerun()

    cantidad = len(estado["analisis"])
    if st.checkbox(
        f"Agregar análisis {cantidad + 1}",
        disabled=cantidad >= MAXIMO_ANALISIS,
        key=f"{clave}_agregar_analisis_{cantidad}",
    ):
        estado["analisis"].append(_analisis_nuevo())
        st.rerun()


def _modelo(estado: dict[str, object]) -> InformeLibre:
    return InformeLibre(
        proyecto_id=int(estado["proyecto_id"]),
        proyecto=str(estado["proyecto"]),
        responsable=str(estado["responsable"]),
        fecha=str(estado["fecha"]),
        introduccion=tuple(BloqueLibre(**item) for item in estado["introduccion"]),
        analisis=tuple(
            AnalisisLibre(
                clave=item["clave"],
                titulo=item["titulo"],
                bloques=tuple(BloqueLibre(**bloque) for bloque in item["bloques"]),
            )
            for item in estado["analisis"]
        ),
    )


def _firma(estado: dict[str, object]) -> str:
    """Ignora datos de widgets para invalidar el PDF solo ante cambios efectivos."""
    serializado = json.dumps(asdict(_modelo(estado)), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def _acciones(ruta: Path, estado: dict[str, object], clave: str) -> None:
    import streamlit as st

    a, b = st.columns(2)
    guardar = a.button("Guardar borrador", key=f"{clave}_guardar")
    generar = b.button("Generar PDF", key=f"{clave}_generar")

    if guardar or generar:
        try:
            informe = _modelo(estado)
            guardar_informe_libre(ruta, informe)
            if guardar:
                st.success("Borrador guardado.")
            if generar:
                pdf = generar_pdf_libre(ruta, informe)
                st.session_state[f"{clave}_pdf"] = (_firma(estado), pdf)
                st.success("PDF generado correctamente.")
        except (ValueError, TypeError, OSError, sqlite3.Error) as error:
            st.error(f"No fue posible guardar o generar el informe: {error}")

    pdf_guardado = st.session_state.get(f"{clave}_pdf")
    if pdf_guardado is not None and pdf_guardado[0] == _firma(estado):
        st.download_button(
            "Descargar PDF",
            data=pdf_guardado[1],
            file_name=f"wattwise_informe_{estado['proyecto_id']}.pdf",
            mime="application/pdf",
            key=f"{clave}_descargar",
        )


def mostrar_informe_por_secciones(ruta: Path) -> None:
    """Editor de informes simplificado; no modifica otros módulos de WattWise."""
    import streamlit as st

    st.header("Constructor de informes")
    st.caption("WattWise · Informe técnico personalizado")

    proyecto_id = st.session_state.get("wattwise_proyecto_id")
    if type(proyecto_id) is not int or proyecto_id <= 0:
        st.info("Selecciona un proyecto activo.")
        return

    try:
        proyecto = next(
            (item for item in listar_proyectos(ruta) if item.id == proyecto_id),
            None,
        )
        if proyecto is None:
            st.error("El proyecto seleccionado no existe.")
            return

        clave, estado = _estado(ruta, proyecto)
        _generales(estado, clave)
        _introduccion(estado, clave)
        catalogo = _catalogo_notas(ruta, proyecto_id)
        _mostrar_analisis(ruta, proyecto_id, estado, clave, catalogo)
        _acciones(ruta, estado, clave)
    except (ValueError, TypeError, OSError, sqlite3.Error) as error:
        st.error(f"No fue posible preparar el informe: {error}")
