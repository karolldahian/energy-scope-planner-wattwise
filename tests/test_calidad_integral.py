"""Regresiones de plantillas completas, auditoría por hoja y notas trazables."""

from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from wattwise.dominio.calidad_integral import auditar_excel
from wattwise.infraestructura.archivos_proyecto import guardar_archivo
from wattwise.infraestructura.notas_calidad_sqlite import (
    eliminar_nota_calidad,
    guardar_nota_calidad,
    listar_notas_calidad,
)
from wattwise.infraestructura.plantillas_completas import (
    ESQUEMAS,
    HOJAS,
    OBLIGATORIAS,
    crear_plantilla_completa,
)
from wattwise.infraestructura.proyectos_sqlite import crear_proyecto, eliminar_proyecto


def _libro(
    tipo: str,
    filas: list[dict[str, object]],
    con_copia: bool = False,
) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = HOJAS[tipo]
    hoja.append(list(ESQUEMAS[tipo]))

    for fila in filas:
        hoja.append([fila.get(campo) for campo in ESQUEMAS[tipo]])

    if con_copia:
        copia = libro.create_sheet("Segundo lote")
        copia.append(list(ESQUEMAS[tipo]))
        for fila in filas:
            copia.append([fila.get(campo) for campo in ESQUEMAS[tipo]])
        libro.create_sheet("Guía")

    salida = BytesIO()
    libro.save(salida)
    libro.close()
    return salida.getvalue()


def _inventario() -> list[dict[str, object]]:
    return [
        {
            "frontera": "F",
            "area": "A",
            "equipo": "Bomba",
            "tipo_carga": "Bombeo",
            "cantidad": 2,
            "potencia_unitaria_kw": 0.0,
        },
        {
            "frontera": "F",
            "area": "B",
            "equipo": "Luz",
            "tipo_carga": "Iluminación",
            "cantidad": 1,
            "potencia_unitaria_kw": 5.0,
        },
    ]


def _medicion(
    minutos: int,
    potencia: object,
    punto: str = "PM1",
) -> dict[str, object]:
    return {
        "fecha_hora": datetime(2026, 1, 1) + timedelta(minutes=minutos),
        "frontera": "F",
        "area": "A",
        "punto_medicion": punto,
        "p_total_kw": potencia,
    }


@pytest.mark.parametrize(
    "tipo",
    ["inventario", "mediciones", "motores"],
)
def test_plantilla_todos_los_encabezados_y_sin_formulas(
    tipo: str,
) -> None:
    libro = load_workbook(
        BytesIO(crear_plantilla_completa(tipo)),
        data_only=False,
    )
    hoja = libro.active

    assert hoja.title == HOJAS[tipo]
    assert tuple(c.value for c in hoja[1]) == ESQUEMAS[tipo]
    assert hoja.max_row == 1
    assert all(c.data_type != "f" for fila in hoja for c in fila)

    for columna in OBLIGATORIAS[tipo]:
        assert columna in ESQUEMAS[tipo]

    libro.close()


def test_plantilla_tipo_desconocido() -> None:
    with pytest.raises(ValueError, match="tipo"):
        crear_plantilla_completa("comparacion")


def test_todas_las_hojas_compatibles_y_auxiliares_omitidas() -> None:
    reporte = auditar_excel(
        "inventario",
        "inv.xlsx",
        _libro("inventario", _inventario(), True),
    )
    assert len(reporte.hojas) == 2
    assert sum(hoja.registros for hoja in reporte.hojas) == 4
    assert reporte.hojas_omitidas == ("Guía",)


def test_ceros_validos_no_se_convierten_en_faltantes() -> None:
    reporte = auditar_excel(
        "inventario",
        "inv.xlsx",
        _libro("inventario", _inventario()),
    )
    campo = next(c for c in reporte.hojas[0].columnas if c.nombre == "potencia_unitaria_kw")
    assert campo.validos == 2
    assert campo.faltantes == 0


def test_duplicado_exacto_y_posible_repetido() -> None:
    filas = _inventario()
    filas.append(dict(filas[0]))

    reporte = auditar_excel(
        "inventario",
        "inv.xlsx",
        _libro("inventario", filas),
    )
    assert reporte.hojas[0].duplicados_exactos == 1
    assert reporte.hojas[0].posibles_repetidos == 1


def test_duplicado_nombre_areas_distintas_no_es_repetido() -> None:
    filas = _inventario()
    filas[1].update(
        equipo="Bomba",
        tipo_carga="Bombeo",
    )

    reporte = auditar_excel(
        "inventario",
        "inv.xlsx",
        _libro("inventario", filas),
    )
    assert reporte.hojas[0].posibles_repetidos == 0


def test_motores_valor_no_valido_se_distingue_del_vacio() -> None:
    fila = {
        "area": "A",
        "equipo": "M",
        "potencia_nominal_hp": 5,
        "numero_fases": 4,
        "corriente_nominal_a": 10,
        "corriente_medida_a": None,
        "horas_operacion_mes": 800,
    }

    reporte = auditar_excel(
        "motores",
        "m.xlsx",
        _libro("motores", [fila]),
    )
    datos = {c.nombre: c for c in reporte.hojas[0].columnas}

    assert datos["numero_fases"].invalidos == 1
    assert datos["corriente_medida_a"].faltantes == 1
    assert datos["horas_operacion_mes"].invalidos == 1


def test_huecos_por_serie_y_punto_sin_sumar_registros() -> None:
    filas = [
        _medicion(0, 0),
        _medicion(15, 2),
        _medicion(30, 2),
        _medicion(120, 2),
        _medicion(15, 4, "PM2"),
        _medicion(30, 4, "PM2"),
    ]

    reporte = auditar_excel(
        "mediciones",
        "med.xlsx",
        _libro("mediciones", filas),
    )
    series = {s.punto.split(" | ")[-1]: s for s in reporte.hojas[0].series}

    assert series["PM1"].huecos_prolongados == 1
    assert series["PM1"].muestras == 4
    assert series["PM2"].huecos_prolongados == 0
    assert series["PM2"].muestras == 2


def test_fechas_duplicadas_por_punto() -> None:
    filas = [
        _medicion(0, 2),
        _medicion(0, 3),
        _medicion(0, 4, "PM2"),
    ]

    reporte = auditar_excel(
        "mediciones",
        "med.xlsx",
        _libro("mediciones", filas),
    )
    assert reporte.hojas[0].fechas_duplicadas == 1


def test_potencia_negativa_valida_en_mediciones() -> None:
    reporte = auditar_excel(
        "mediciones",
        "med.xlsx",
        _libro("mediciones", [_medicion(0, -2)]),
    )
    campo = next(c for c in reporte.hojas[0].columnas if c.nombre == "p_total_kw")
    assert campo.validos == 1


def test_fecha_texto_erroneo_no_se_inventa() -> None:
    fila = _medicion(0, 2)
    fila["fecha_hora"] = "ayer en la noche"

    reporte = auditar_excel(
        "mediciones",
        "med.xlsx",
        _libro("mediciones", [fila]),
    )

    assert reporte.hojas[0].fechas_invalidas == 1
    assert reporte.hojas[0].series == ()


def test_rechaza_otros_formatos_y_contenido_vacio() -> None:
    with pytest.raises(ValueError):
        auditar_excel("inventario", "inventario.csv", b"a,b")
    with pytest.raises(ValueError):
        auditar_excel("inventario", "inventario.xlsx", b"")


def test_omision_de_columnas_opcionales_se_reporta() -> None:
    libro = Workbook()
    hoja = libro.active
    hoja.append(
        [
            "equipo",
            "tipo_carga",
            "cantidad",
            "potencia_unitaria_kw",
        ]
    )
    hoja.append(["M", "B", 1, 2])

    salida = BytesIO()
    libro.save(salida)
    libro.close()

    reporte = auditar_excel(
        "inventario",
        "i.xlsx",
        salida.getvalue(),
    )
    assert "area" in reporte.hojas[0].columnas_ausentes
    assert reporte.hojas[0].registros == 1


def _proyecto(tmp_path: Path) -> tuple[Path, int, int]:
    ruta = tmp_path / "wattwise.sqlite3"
    proyecto = crear_proyecto(ruta, "Calidad")
    archivo = guardar_archivo(
        ruta,
        proyecto,
        "inventario",
        "i.xlsx",
        b"original",
    )
    return ruta, proyecto, archivo


def test_guardar_y_recuperar_nota(tmp_path: Path) -> None:
    ruta, proyecto, archivo = _proyecto(tmp_path)
    identidad = guardar_nota_calidad(
        ruta,
        proyecto,
        archivo,
        "Falta revisar documento.",
    )
    notas = listar_notas_calidad(
        ruta,
        proyecto,
        archivo,
    )
    assert notas[0].id == identidad
    assert notas[0].contenido == "Falta revisar documento."
    assert len(notas[0].sha256_archivo) == 64


def test_rechaza_nota_vacia(tmp_path: Path) -> None:
    ruta, proyecto, archivo = _proyecto(tmp_path)
    with pytest.raises(ValueError, match="nota"):
        guardar_nota_calidad(
            ruta,
            proyecto,
            archivo,
            " ",
        )


def test_nota_no_permite_archivo_de_otro_proyecto(
    tmp_path: Path,
) -> None:
    ruta, _, archivo = _proyecto(tmp_path)
    otro = crear_proyecto(ruta, "Otro")

    with pytest.raises(ValueError, match="no pertenece"):
        guardar_nota_calidad(
            ruta,
            otro,
            archivo,
            "Nota",
        )


def test_eliminar_nota_respeta_proyecto(tmp_path: Path) -> None:
    ruta, proyecto, archivo = _proyecto(tmp_path)
    otro = crear_proyecto(ruta, "Otro")
    identidad = guardar_nota_calidad(
        ruta,
        proyecto,
        archivo,
        "Nota",
    )

    assert not eliminar_nota_calidad(
        ruta,
        otro,
        identidad,
    )
    assert eliminar_nota_calidad(
        ruta,
        proyecto,
        identidad,
    )


def test_eliminar_proyecto_elimina_notas(tmp_path: Path) -> None:
    ruta, proyecto, archivo = _proyecto(tmp_path)
    guardar_nota_calidad(
        ruta,
        proyecto,
        archivo,
        "Nota",
    )
    assert eliminar_proyecto(ruta, proyecto)
    assert listar_notas_calidad(ruta, proyecto) == []
