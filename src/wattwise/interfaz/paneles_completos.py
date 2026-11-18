"""Dashboards de inventario y motores con filtros y notas por contexto."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from math import isfinite
from pathlib import Path

from wattwise.infraestructura.observaciones_sqlite import (
    Observacion,
    actualizar_visibilidad_observacion,
    eliminar_observacion,
    guardar_observacion,
    listar_observaciones,
)
from wattwise.interfaz.graficos_completos import (
    barras_areas,
    barras_motores,
    corrientes_motores,
    dona_cargas,
    mapa_revision_motores,
    matriz_inventario,
    pareto_inventario,
    resumen_estrategico_inventario,
)

VISTAS_INVENTARIO = (
    "Pareto por tipo de carga",
    "Pareto por equipo",
    "Potencia por area",
    "Distribucion por tipo de carga",
    "Matriz de potencia instalada",
)

VISTAS_MOTORES = (
    "Corriente nominal vs medida",
    "Mapa de revision",
    "Potencia nominal por motor",
    "Horas de operacion por motor",
)


def registros_inventario(resultado: object) -> list[dict[str, object]]:
    """Adapta registros del dominio sin recalcular su potencia validada."""
    return [
        {
            "id_fila": numero,
            "frontera": getattr(registro, "frontera", None),
            "area": registro.area,
            "equipo": registro.equipo,
            "tipo_carga": registro.tipo_carga,
            "cantidad": registro.cantidad,
            "potencia_unitaria_kw": registro.potencia_unitaria_kw,
            "potencia_instalada_kw": registro.potencia_instalada_kw,
        }
        for numero, registro in enumerate(resultado.registros, start=2)
    ]


def registros_motores(resultado: object) -> list[dict[str, object]]:
    """Distingue motores fisicos incluso si sus nombres son identicos."""
    return [
        {
            "id_fila": numero,
            "area": registro.area,
            "equipo": registro.equipo,
            "numero_fases": registro.numero_fases,
            "potencia_nominal_hp": registro.potencia_nominal_hp,
            "corriente_nominal_a": registro.corriente_nominal_a,
            "corriente_medida_a": registro.corriente_medida_a,
            "horas_operacion_mes": registro.horas_operacion_mes,
        }
        for numero, registro in enumerate(resultado.registros, start=2)
    ]


def _filtro(
    registros: list[dict[str, object]],
    nombre: str,
    campo: str,
    clave: str,
) -> tuple[list[dict[str, object]], str]:
    """Aplica un filtro visible sin alterar las filas originales."""
    import streamlit as st

    valores = sorted({str(fila.get(campo) or "Sin especificar") for fila in registros})
    if not valores or valores == ["Sin especificar"]:
        return registros, "Todos"

    seleccion = st.selectbox(
        nombre,
        ["Todos", *valores],
        key=clave,
    )
    if seleccion == "Todos":
        return registros, seleccion

    filtrados = [
        fila for fila in registros if str(fila.get(campo) or "Sin especificar") == seleccion
    ]
    return filtrados, seleccion


def _controles_nota(
    ruta: Path,
    proyecto_id: int,
    nota: Observacion,
    clave: str,
) -> None:
    """Permite gestionar una nota sin concentrar complejidad en el panel."""
    import streamlit as st

    mostrar = st.checkbox(
        "Mostrar en el informe",
        value=nota.mostrar_en_informe,
        key=f"nv_{clave}_{nota.id}",
    )
    if mostrar != nota.mostrar_en_informe:
        try:
            actualizada = actualizar_visibilidad_observacion(
                ruta,
                proyecto_id,
                nota.id,
                mostrar,
            )
            if actualizada:
                st.toast("Preferencia de informe guardada.")
            else:
                st.error("La nota ya no existe. Actualiza la pestaña.")
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(f"No se pudo cambiar la preferencia: {error}")

    confirmar = st.checkbox(
        "Confirmar eliminación",
        key=f"nd_{clave}_{nota.id}",
    )
    if st.button(
        "Eliminar nota",
        disabled=not confirmar,
        key=f"ne_{clave}_{nota.id}",
    ):
        try:
            eliminar_observacion(ruta, proyecto_id, nota.id)
            st.rerun()
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(f"No se pudo eliminar la nota: {error}")


def _mostrar_notas(
    ruta: Path,
    tipo: str,
    grafica: str,
    contexto: dict[str, str],
) -> None:
    """Usa el proyecto activo y enumera las notas visibles consecutivamente."""
    import streamlit as st

    st.markdown("#### Observaciones")
    proyecto_id = st.session_state.get("wattwise_proyecto_id")
    if not isinstance(proyecto_id, int) or isinstance(proyecto_id, bool):
        st.info("Selecciona un proyecto activo en la barra lateral.")
        return

    identidad = hashlib.sha256(
        json.dumps(
            [tipo, grafica, contexto],
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    clave = f"{identidad}_{proyecto_id}"

    texto = st.text_area(
        "Observación",
        max_chars=2000,
        key=f"nt_{clave}",
    )

    if st.button(
        "Guardar observación",
        key=f"ng_{clave}",
    ):
        if not texto.strip():
            st.warning("Escribe una observación antes de guardarla.")
        else:
            try:
                guardar_observacion(
                    ruta,
                    proyecto_id,
                    tipo,
                    grafica,
                    contexto,
                    texto.strip(),
                )
                st.success("Observación guardada.")
            except (ValueError, sqlite3.Error, OSError) as error:
                st.error(f"No se pudo guardar la observación: {error}")

    try:
        notas = sorted(
            listar_observaciones(
                ruta,
                proyecto_id,
                tipo,
                grafica,
                contexto,
            ),
            key=lambda nota: nota.id,
        )
    except (ValueError, sqlite3.Error, OSError) as error:
        st.error(f"No se pudieron consultar las observaciones: {error}")
        return

    if notas:
        with st.expander(f"Notas guardadas ({len(notas)})"):
            for posicion, nota in enumerate(notas, start=1):
                st.markdown(f"**Nota {posicion}**")
                st.write(nota.texto)
                _controles_nota(ruta, proyecto_id, nota, clave)
                st.divider()


def _tabla(
    registros: list[dict[str, object]],
    tipo: str,
) -> None:
    """Permite inspeccionar y descargar únicamente los registros filtrados."""
    import pandas as pd
    import streamlit as st

    st.markdown("#### Datos del filtro aplicado")
    tabla = pd.DataFrame(registros)
    st.dataframe(tabla, hide_index=True, width="stretch")
    exportable = tabla.copy()

    for columna in exportable.select_dtypes(include=["object"]).columns:
        exportable[columna] = exportable[columna].map(
            lambda valor: (
                "'" + valor
                if isinstance(valor, str) and valor.startswith(("=", "+", "-", "@"))
                else valor
            )
        )

    st.download_button(
        "Descargar tabla CSV",
        data=exportable.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"wattwise_{tipo}_filtrado.csv",
        mime="text/csv",
        key=f"csv_{tipo}",
    )


def _agrupaciones_kpi(
    registros: list[dict[str, object]],
    campo: str,
) -> list[tuple[str, float, int]]:
    """Agrupa potencia instalada y unidades por campo."""
    potencias: dict[str, float] = defaultdict(float)
    unidades: dict[str, int] = defaultdict(int)
    nombres: dict[str, str] = {}

    for fila in registros:
        etiqueta = fila.get(campo)
        nombre = (
            " ".join(etiqueta.split())
            if isinstance(etiqueta, str) and etiqueta.strip()
            else "Sin especificar"
        )
        clave = nombre.casefold() if campo == "equipo" else nombre
        nombres.setdefault(clave, nombre)
        potencias[clave] += float(fila["potencia_instalada_kw"])
        unidades[clave] += int(fila["cantidad"])

    return sorted(
        ((nombres[clave], potencia, unidades[clave]) for clave, potencia in potencias.items()),
        key=lambda item: (-item[1], item[0]),
    )


def _porcentaje(parte: float, total: float) -> str:
    """Siempre muestra dos decimales."""
    valor = 100 * parte / total if total > 0 else 0.0
    return f"{valor:.2f} %"


def _desglose_inventario(
    elementos: list[tuple[str, float, int]],
    total_kw: float,
    *,
    mostrar_unidades: bool = False,
) -> None:
    """Muestra todos los elementos de mayor a menor potencia."""
    import streamlit as st

    if not elementos:
        st.caption("No hay elementos para mostrar.")
        return

    for numero, (nombre, potencia, unidades) in enumerate(
        elementos,
        start=1,
    ):
        detalle = f" · {unidades:,} unidades" if mostrar_unidades else ""
        st.write(
            f"{numero}. {nombre} ({potencia:,.2f} kW) ({_porcentaje(potencia, total_kw)}){detalle}"
        )


def _kpi_potencia(
    resumen: dict[str, object],
    registros: list[dict[str, object]],
) -> None:
    """Potencia total y desglose completo por frontera."""
    import streamlit as st

    total = resumen["total_kw"]
    st.metric(
        "Potencia Total Instalada",
        f"{total:,.2f} kW",
    )
    st.caption(
        f"{resumen['unidades']:,} equipos en {resumen['areas_cantidad']} áreas identificadas"
    )

    with st.expander("Ver desglose por frontera"):
        _desglose_inventario(
            _agrupaciones_kpi(registros, "frontera"),
            total,
        )


def _kpi_carga(resumen: dict[str, object]) -> None:
    """Carga dominante con potencia entre paréntesis."""
    import streamlit as st

    total = resumen["total_kw"]
    cargas = resumen["cargas"]

    if cargas and total > 0:
        nombre, potencia, _unidades = cargas[0]
        st.metric(
            "Carga Dominante (Por Potencia)",
            f"{nombre} ({potencia:,.2f} kW)",
        )
        st.caption(f"Participación: {_porcentaje(potencia, total)}")
    else:
        st.metric(
            "Carga Dominante (Por Potencia)",
            "No disponible",
        )

    with st.expander("Ver desglose por tipo de carga"):
        _desglose_inventario(cargas, total)


def _kpi_area(resumen: dict[str, object]) -> None:
    """Área dominante con potencia entre paréntesis."""
    import streamlit as st

    total = resumen["total_kw"]
    areas = resumen["areas"]

    if areas and total > 0:
        nombre, potencia = areas[0]
        st.metric(
            "Área con Mayor Potencia Instalada",
            f"{nombre} ({potencia:,.2f} kW)",
        )
        st.caption(f"Participación: {_porcentaje(potencia, total)}")
    else:
        st.metric(
            "Área con Mayor Potencia Instalada",
            "No disponible",
        )

    with st.expander("Ver desglose por área"):
        elementos = [(nombre, potencia, 0) for nombre, potencia in areas]
        _desglose_inventario(elementos, total)


def _kpi_equipo(
    resumen: dict[str, object],
    registros: list[dict[str, object]],
) -> None:
    """Equipo dominante con potencia entre paréntesis."""
    import streamlit as st

    total = resumen["total_kw"]
    equipos = _agrupaciones_kpi(registros, "equipo")

    if equipos and total > 0:
        nombre, potencia, unidades = equipos[0]
        st.metric(
            "Equipo de Mayor Peso Instalado",
            f"{nombre} ({potencia:,.2f} kW)",
        )
        st.caption(f"Participación: {_porcentaje(potencia, total)} · {unidades:,} unidades")
    else:
        st.metric(
            "Equipo de Mayor Peso Instalado",
            "No disponible",
        )

    with st.expander("Ver desglose por equipo"):
        _desglose_inventario(
            equipos,
            total,
            mostrar_unidades=True,
        )


def _kpis_inventario(
    registros: list[dict[str, object]],
) -> None:
    """Conserva las cuatro tarjetas 2x2 y sus desgloses."""
    import streamlit as st

    resumen = resumen_estrategico_inventario(registros)
    primera = st.columns(2)
    segunda = st.columns(2)

    with primera[0]:
        _kpi_potencia(resumen, registros)
    with primera[1]:
        _kpi_carga(resumen)
    with segunda[0]:
        _kpi_area(resumen)
    with segunda[1]:
        _kpi_equipo(resumen, registros)

    st.caption(
        "Los KPI describen potencia instalada declarada, no consumo (kWh) "
        "ni demanda máxima medida. Se aplican los filtros visibles."
    )


def _numero_motor(valor: object) -> float | None:
    """Rechaza booleanos, valores ausentes y números no finitos."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None

    numero = float(valor)
    return numero if isfinite(numero) else None


def _nombre_motor(valor: object) -> str:
    """Devuelve nombre válido o etiqueta de dato ausente."""
    if isinstance(valor, str) and valor.strip():
        return valor.strip()
    return "Sin especificar"


def _detalle_motor(
    fila: dict[str, object],
) -> dict[str, object]:
    """Calcula I medida/I nominal si ambas magnitudes permiten hacerlo."""
    nominal = _numero_motor(fila.get("corriente_nominal_a"))
    medida = _numero_motor(fila.get("corriente_medida_a"))

    razon = (
        100 * medida / nominal
        if nominal is not None and nominal > 0 and medida is not None and medida >= 0
        else None
    )

    return {
        "equipo": _nombre_motor(fila.get("equipo")),
        "area": _nombre_motor(fila.get("area")),
        "fila": fila.get("id_fila"),
        "hp": _numero_motor(fila.get("potencia_nominal_hp")),
        "fases": fila.get("numero_fases"),
        "nominal_a": nominal,
        "medida_a": medida,
        "relacion_pct": razon,
        "horas_mes": _numero_motor(fila.get("horas_operacion_mes")),
    }


def _areas_motores(
    motores: list[dict[str, object]],
) -> list[tuple[str, float, int]]:
    """Agrupa HP y cantidad de motores por área."""
    areas: dict[str, tuple[float, int]] = defaultdict(lambda: (0.0, 0))

    for motor in motores:
        area = str(motor["area"])
        hp_area, cantidad = areas[area]
        areas[area] = (
            hp_area + float(motor["hp"] or 0),
            cantidad + 1,
        )

    return sorted(
        [(area, potencia, cantidad) for area, (potencia, cantidad) in areas.items()],
        key=lambda item: (-item[1], item[0]),
    )


def _corrientes_motores(
    motores: list[dict[str, object]],
) -> tuple[int, list[dict[str, object]], list[dict[str, object]]]:
    """Devuelve rankings completos de corriente superior y baja."""
    validos = [motor for motor in motores if motor["relacion_pct"] is not None]
    superiores = sorted(
        (motor for motor in validos if motor["relacion_pct"] > 100),
        key=lambda motor: (
            -motor["relacion_pct"],
            str(motor["equipo"]),
        ),
    )
    bajas = sorted(
        (motor for motor in validos if motor["relacion_pct"] < 50),
        key=lambda motor: (
            motor["relacion_pct"],
            str(motor["equipo"]),
        ),
    )
    return len(validos), superiores, bajas


def _uso_motores(
    motores: list[dict[str, object]],
) -> tuple[int, int, list[dict[str, object]]]:
    """Cuenta los que superan 500 h/mes y ordena todos por horas."""
    validos = [motor for motor in motores if motor["horas_mes"] is not None]
    elevados = sum(motor["horas_mes"] > 500 for motor in validos)
    ordenados = sorted(
        validos,
        key=lambda motor: (
            -motor["horas_mes"],
            str(motor["equipo"]),
        ),
    )
    return len(validos), elevados, ordenados


def resumen_integrado_motores(
    registros: list[dict[str, object]],
) -> dict[str, object]:
    """Calcula los cuatro KPI sin inferir energía o eficiencia."""
    motores = [_detalle_motor(fila) for fila in registros]
    hp = sum(float(motor["hp"]) for motor in motores if motor["hp"] is not None)
    con_corriente, superiores, bajas = _corrientes_motores(motores)
    con_horas, elevados, ordenados_uso = _uso_motores(motores)

    return {
        "motores": len(motores),
        "hp": hp,
        "kw_mecanicos": hp * 0.745699872,
        "trifasicos": sum(motor["fases"] == 3 for motor in motores),
        "monofasicos": sum(motor["fases"] == 1 for motor in motores),
        "areas": _areas_motores(motores),
        "con_corriente": con_corriente,
        "corriente_superior": len(superiores),
        "top_superiores": superiores,
        "corriente_baja": len(bajas),
        "top_bajas": bajas,
        "con_horas": con_horas,
        "uso_elevado": elevados,
        "top_uso": ordenados_uso,
    }


def _proporcion(casos: int, evaluables: int) -> str:
    """Porcentaje entre paréntesis, siempre con dos decimales."""
    if not evaluables:
        return "Sin datos"
    return f"{casos} de {evaluables} ({_porcentaje(casos, evaluables)})"


def _texto_horas(horas: object) -> str:
    """Respeta horas no declaradas."""
    if horas is None:
        return "horas no declaradas"
    return f"{horas:,.0f} h/mes"


def _texto_corriente(motor: dict[str, object]) -> str:
    """Ubica el motor, la relación de corriente y sus horas."""
    return (
        f"{motor['equipo']} ({motor['area']}, fila {motor['fila']}): "
        f"{_porcentaje(motor['relacion_pct'], 100)} de I nominal · "
        f"{motor['medida_a']:.2f} A / {motor['nominal_a']:.2f} A · "
        f"{_texto_horas(motor['horas_mes'])}"
    )


def _kpi_motor_capacidad(resumen: dict[str, object]) -> None:
    """HP mecánicos nominales, fases y todas las áreas."""
    import streamlit as st

    st.metric(
        "Capacidad y tecnología",
        f"{resumen['hp']:,.2f} HP",
    )
    st.caption(
        f"Equivalente nominal: {resumen['kw_mecanicos']:,.2f} kW mecánicos · "
        f"{resumen['motores']} motores "
        f"({resumen['trifasicos']} trifásicos · "
        f"{resumen['monofasicos']} monofásicos)"
    )

    with st.expander("Ver desglose por área"):
        for numero, (area, hp_area, cantidad) in enumerate(
            resumen["areas"],
            start=1,
        ):
            st.write(
                f"{numero}. {area} ({hp_area:,.2f} HP) "
                f"({_porcentaje(hp_area, resumen['hp'])}) · "
                f"{cantidad} motores"
            )


def _kpi_motor_corriente(resumen: dict[str, object]) -> None:
    """Corrientes superiores a nominal con todos los casos."""
    import streamlit as st

    st.metric(
        "Corriente superior a nominal",
        _proporcion(
            resumen["corriente_superior"],
            resumen["con_corriente"],
        ),
    )
    st.caption("I medida > I nominal; condición para revisar, no diagnóstico térmico")

    with st.expander("Ver desglose de corrientes superiores a nominal"):
        for numero, motor in enumerate(
            resumen["top_superiores"],
            start=1,
        ):
            st.write(f"{numero}. {_texto_corriente(motor)}")
        if not resumen["top_superiores"]:
            st.caption("No se encontraron casos.")


def _kpi_motor_uso(resumen: dict[str, object]) -> None:
    """Uso mensual alto y todas las horas registradas."""
    import streamlit as st

    st.metric(
        "Uso mensual elevado",
        _proporcion(
            resumen["uso_elevado"],
            resumen["con_horas"],
        ),
    )
    st.caption("Más de 500 h/mes declaradas · kWh no calculables con estos datos")

    with st.expander("Ver desglose por horas de uso"):
        for numero, motor in enumerate(
            resumen["top_uso"],
            start=1,
        ):
            potencia = f"{motor['hp']:,.2f} HP" if motor["hp"] is not None else "HP no declarados"
            st.write(
                f"{numero}. {motor['equipo']} "
                f"({motor['area']}, fila {motor['fila']}): "
                f"{_texto_horas(motor['horas_mes'])} · {potencia}"
            )
        if not resumen["top_uso"]:
            st.caption("No hay horas declaradas.")


def _kpi_motor_corriente_baja(resumen: dict[str, object]) -> None:
    """Muestra las relaciones inferiores al umbral de revisión."""
    import streamlit as st

    st.metric(
        "Baja relación de corriente",
        _proporcion(
            resumen["corriente_baja"],
            resumen["con_corriente"],
        ),
    )
    st.caption("I medida inferior al 50.00 % de I nominal; no demuestra subcarga o ineficiencia")

    with st.expander("Ver desglose de corrientes inferiores al 50 %"):
        for numero, motor in enumerate(
            resumen["top_bajas"],
            start=1,
        ):
            st.write(f"{numero}. {_texto_corriente(motor)}")
        if not resumen["top_bajas"]:
            st.caption("No se encontraron casos.")


def _kpis_motores(
    registros: list[dict[str, object]],
) -> None:
    """Cuatro indicadores de motores en disposición 2x2."""
    import streamlit as st

    resumen = resumen_integrado_motores(registros)
    primera = st.columns(2)
    segunda = st.columns(2)

    with primera[0]:
        _kpi_motor_capacidad(resumen)
    with primera[1]:
        _kpi_motor_corriente(resumen)
    with segunda[0]:
        _kpi_motor_uso(resumen)
    with segunda[1]:
        _kpi_motor_corriente_baja(resumen)

    st.caption(
        "HP y kW equivalentes son potencia mecánica nominal. "
        "I medida/I nominal no indica eficiencia, carga real, kWh ni fallas."
    )


def mostrar_inventario_completo(resultado: object, ruta: Path) -> None:
    """Presenta cinco gráficas, filtros y notas del proyecto activo."""
    import streamlit as st

    from wattwise.interfaz.acciones_inventario import (
        mostrar_exportacion_inventario,
        mostrar_guardado_inventario,
    )

    registros = registros_inventario(resultado)
    if not registros:
        st.info("No hay equipos para analizar.")
        return

    columnas = st.columns(4)
    with columnas[0]:
        registros, frontera = _filtro(
            registros,
            "Frontera",
            "frontera",
            "inv_frontera",
        )
    with columnas[1]:
        registros, area = _filtro(
            registros,
            "Área",
            "area",
            "inv_area",
        )
    with columnas[2]:
        registros, tipo = _filtro(
            registros,
            "Tipo de carga",
            "tipo_carga",
            "inv_tipo",
        )
    with columnas[3]:
        registros, equipo = _filtro(
            registros,
            "Equipo",
            "equipo",
            "inv_equipo",
        )

    if not registros:
        st.info("No hay equipos para la selección actual.")
        return

    izquierda, derecha = st.columns([3, 1], gap="large")

    with derecha:
        st.markdown("#### Controles")
        vista = st.selectbox(
            "Gráfica",
            VISTAS_INVENTARIO,
            key="inv_grafica",
        )

        if vista.startswith("Pareto"):
            linea = st.checkbox(
                "Línea de cumbre",
                value=True,
                key="inv_cumbres",
            )
            acumulado = st.checkbox(
                "Porcentaje acumulado",
                value=True,
                key="inv_acumulado",
            )
            referencia = st.checkbox(
                "Referencia del 80 %",
                value=True,
                key="inv_80",
            )
        else:
            linea, acumulado, referencia = True, True, True

        mostrar_valores = st.checkbox(
            "Visualización de datos numéricos",
            value=True,
            key="inv_mostrar_valores",
        )
        st.caption("Leyenda interactiva, zoom, restauración y descarga PNG.")

    with izquierda:
        if vista == VISTAS_INVENTARIO[0]:
            grafico = pareto_inventario(
                registros,
                "tipo_carga",
                linea_barras=linea,
                acumulado=acumulado,
                umbral_80=referencia,
                mostrar_valores=mostrar_valores,
            )
        elif vista == VISTAS_INVENTARIO[1]:
            grafico = pareto_inventario(
                registros,
                "equipo",
                linea_barras=linea,
                acumulado=acumulado,
                umbral_80=referencia,
                mostrar_valores=mostrar_valores,
            )
        elif vista == VISTAS_INVENTARIO[2]:
            grafico = barras_areas(
                registros,
                mostrar_valores=mostrar_valores,
            )
        elif vista == VISTAS_INVENTARIO[3]:
            grafico = dona_cargas(
                registros,
                mostrar_valores=mostrar_valores,
            )
        else:
            grafico = matriz_inventario(
                registros,
                mostrar_valores=mostrar_valores,
            )

        st.echarts_chart(
            grafico,
            height=570,
            key="inventario_completo",
            alt=vista,
        )
        st.caption("Agrupaciones calculadas únicamente a partir del inventario y los filtros.")

    with derecha:
        mostrar_exportacion_inventario(grafico, vista)
        mostrar_guardado_inventario(
            ruta,
            resultado,
            vista,
            {"frontera": frontera, "area": area, "tipo_carga": tipo, "equipo": equipo},
            {"linea_barras": linea, "acumulado": acumulado, "umbral_80": referencia},
        )

    st.markdown("#### Indicadores del inventario filtrado")
    _kpis_inventario(registros)

    _mostrar_notas(
        ruta,
        "inventario",
        vista,
        {
            "frontera": frontera,
            "area": area,
            "tipo_carga": tipo,
            "equipo": equipo,
        },
    )
    _tabla(registros, "inventario")


def mostrar_motores_completo(resultado: object, ruta: Path) -> None:
    """Presenta cuatro gráficas de motores y notas del proyecto activo."""
    import streamlit as st

    registros = registros_motores(resultado)
    if not registros:
        st.info("No hay motores para analizar.")
        return

    columnas = st.columns(3)
    with columnas[0]:
        registros, area = _filtro(
            registros,
            "Área",
            "area",
            "motor_area",
        )
    with columnas[1]:
        registros, fases = _filtro(
            registros,
            "Número de fases",
            "numero_fases",
            "motor_fases",
        )
    with columnas[2]:
        registros, equipo = _filtro(
            registros,
            "Equipo",
            "equipo",
            "motor_equipo",
        )

    if not registros:
        st.info("No hay motores para la selección actual.")
        return

    vistas = list(VISTAS_MOTORES)
    if not any(registro.get("horas_operacion_mes") is not None for registro in registros):
        vistas.remove(VISTAS_MOTORES[3])

    izquierda, derecha = st.columns([3, 1], gap="large")

    with derecha:
        st.markdown("#### Controles")
        vista = st.selectbox(
            "Gráfica",
            vistas,
            key="motor_grafica",
        )
        mostrar_valores = st.checkbox(
            "Visualización de datos numéricos",
            value=True,
            key="motor_mostrar_valores",
        )
        st.caption("Relación de corrientes: indicador descriptivo, no diagnóstico.")

    with izquierda:
        if vista == VISTAS_MOTORES[0]:
            st.echarts_chart(
                corrientes_motores(
                    registros,
                    mostrar_valores=mostrar_valores,
                ),
                height=540,
                key="motor_corrientes",
                alt=vista,
            )

        elif vista == VISTAS_MOTORES[1]:
            grafico = mapa_revision_motores(
                registros,
                "relacion",
                mostrar_valores=mostrar_valores,
            )
            if grafico is not None:
                st.echarts_chart(
                    grafico,
                    height=520,
                    key="motor_mapa_relacion",
                    alt=vista,
                )

            horas = mapa_revision_motores(
                registros,
                "horas",
                mostrar_valores=mostrar_valores,
            )
            if horas is not None:
                st.caption("Horas: mapa independiente, con escala distinta al porcentaje.")
                st.echarts_chart(
                    horas,
                    height=520,
                    key="motor_mapa_horas",
                    alt="Horas por motor",
                )
        else:
            campo = "potencia_nominal_hp" if vista == VISTAS_MOTORES[2] else "horas_operacion_mes"
            grafico = barras_motores(
                registros,
                campo,
                mostrar_valores=mostrar_valores,
            )
            if grafico is not None:
                st.echarts_chart(
                    grafico,
                    height=530,
                    key="motor_barras",
                    alt=vista,
                )

        st.caption("Revisar placa, instrumento y condiciones antes de concluir una falla.")

    st.markdown("#### Indicadores de motores filtrados")
    _kpis_motores(registros)

    _mostrar_notas(
        ruta,
        "motores",
        vista,
        {
            "area": area,
            "fases": fases,
            "equipo": equipo,
        },
    )
    _tabla(registros, "motores")
