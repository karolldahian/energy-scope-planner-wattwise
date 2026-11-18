"""Regresiones de dashboards, notas persistentes e informes WattWise."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from wattwise.infraestructura.analisis_sqlite import AnalisisGuardado
from wattwise.infraestructura.informes_pdf import generar_informe_pdf
from wattwise.infraestructura.observaciones_sqlite import (
    eliminar_observacion,
    guardar_observacion,
    listar_observaciones,
)
from wattwise.infraestructura.proyectos_sqlite import crear_proyecto, eliminar_proyecto
from wattwise.interfaz.graficos_completos import (
    barras_areas,
    barras_motores,
    corrientes_motores,
    dona_cargas,
    indicadores_inventario,
    indicadores_motores,
    mapa_revision_motores,
    matriz_inventario,
    pareto_inventario,
)
from wattwise.interfaz.paneles_completos import (
    registros_inventario,
    registros_motores,
)


def _inventario() -> list[dict[str, object]]:
    """Construye equipos con duplicados y potencia cero."""
    return [
        {
            "area": "A",
            "equipo": "Bomba",
            "tipo_carga": "Bombeo",
            "cantidad": 2,
            "potencia_instalada_kw": 12.0,
        },
        {
            "area": "B",
            "equipo": "Luz",
            "tipo_carga": "Iluminacion",
            "cantidad": 4,
            "potencia_instalada_kw": 4.0,
        },
        {
            "area": "",
            "equipo": "Bomba",
            "tipo_carga": "Bombeo",
            "cantidad": 1,
            "potencia_instalada_kw": 0.0,
        },
    ]


def _motores() -> list[dict[str, object]]:
    """Construye motores duplicados con horas nulas y cero real."""
    return [
        {
            "id_fila": 2,
            "equipo": "Motor A",
            "corriente_nominal_a": 10.0,
            "corriente_medida_a": 12.0,
            "potencia_nominal_hp": 3.0,
            "horas_operacion_mes": 0.0,
        },
        {
            "id_fila": 3,
            "equipo": "Motor A",
            "corriente_nominal_a": 20.0,
            "corriente_medida_a": 10.0,
            "potencia_nominal_hp": 5.0,
            "horas_operacion_mes": None,
        },
    ]


def _analisis() -> AnalisisGuardado:
    """Prepara un analisis guardado sin inventar magnitudes adicionales."""
    return AnalisisGuardado(
        1,
        2,
        "inventario",
        "Inventario de cargas",
        "2026-11-14T12:00:00+00:00",
        {
            "potencia_total_kw": 16,
            "cantidad_equipos": 7,
            "registros": [
                {
                    "equipo": "Bomba",
                    "area": "Hacienda",
                    "cantidad": 2,
                    "potencia_instalada_kw": 12.0,
                }
            ],
        },
    )


def test_inventario_kpis_suman_unidades_y_kw() -> None:
    indicadores = indicadores_inventario(_inventario())
    assert indicadores["potencia_kw"] == 16
    assert indicadores["equipos"] == 7
    assert indicadores["areas"] == 2
    assert indicadores["tipo_predominante"] == "Bombeo"


def test_pareto_tres_series_y_acumulado() -> None:
    grafico = pareto_inventario(_inventario(), "tipo_carga")
    assert [serie["data"] for serie in grafico["series"]] == [
        [12.0, 4.0],
        [12.0, 4.0],
        [75.0, 100.0],
    ]
    assert grafico["series"][2]["markLine"]["data"][0]["yAxis"] == 80


def test_pareto_permite_ocultar_series() -> None:
    grafico = pareto_inventario(
        _inventario(),
        "equipo",
        linea_barras=False,
        acumulado=False,
    )
    assert len(grafico["series"]) == 1


def test_pareto_total_cero_no_divide() -> None:
    grafico = pareto_inventario(
        [_inventario()[2]],
        "tipo_carga",
    )
    assert grafico["series"][2]["data"] == [0.0]


def test_matriz_conserva_kw_y_no_inventa_celdas() -> None:
    grafico = matriz_inventario(_inventario())
    assert len(grafico["series"][0]["data"]) == 3
    assert sum(punto[2] for punto in grafico["series"][0]["data"]) == 16


def test_barras_y_dona_conservan_kw() -> None:
    barras = barras_areas(_inventario())
    dona = dona_cargas(_inventario())

    assert barras["series"][0]["data"][0] == 12
    assert dona["series"][0]["data"][0]["value"] == 12


def test_motores_kpis_y_sobrecorriente() -> None:
    indicadores = indicadores_motores(_motores())
    assert indicadores["sobre_nominal"] == 1
    assert indicadores["relacion_media_pct"] == 85
    assert indicadores["potencia_hp"] == 8


def test_motor_duplicado_preserva_identidad() -> None:
    grafico = corrientes_motores(_motores())
    assert grafico["xAxis"]["data"] == [
        "Motor A · fila 2",
        "Motor A · fila 3",
    ]
    assert grafico["series"][2]["data"] == [120, 50]
    assert grafico["series"][2]["yAxisIndex"] == 1


def test_mapas_motor_con_escalas_independientes() -> None:
    relacion = mapa_revision_motores(
        _motores(),
        "relacion",
    )
    horas = mapa_revision_motores(
        _motores(),
        "horas",
    )
    assert relacion is not None
    assert horas is not None
    assert relacion["visualMap"]["max"] == 120
    assert horas["visualMap"]["max"] == 1.0
    assert len(horas["series"][0]["data"]) == 1


def test_oculta_horas_faltantes() -> None:
    registros = [dict(motor, horas_operacion_mes=None) for motor in _motores()]
    assert barras_motores(registros, "horas_operacion_mes") is None
    assert mapa_revision_motores(registros, "horas") is None


def test_barras_hp_ordenadas() -> None:
    grafico = barras_motores(
        _motores(),
        "potencia_nominal_hp",
    )
    assert grafico is not None
    assert grafico["series"][0]["data"] == [5, 3]


def test_rechaza_corriente_nominal_cero() -> None:
    with pytest.raises(ValueError, match="positiva"):
        indicadores_motores([dict(_motores()[0], corriente_nominal_a=0)])


def test_adaptador_inventario_no_altera_resultado() -> None:
    modelo = SimpleNamespace(
        registros=[
            SimpleNamespace(
                area="Hacienda",
                equipo="Bomba",
                tipo_carga="Bombeo",
                cantidad=2,
                potencia_unitaria_kw=3.0,
                potencia_instalada_kw=6.0,
            )
        ]
    )
    registros = registros_inventario(modelo)
    assert registros[0]["potencia_instalada_kw"] == 6
    assert registros[0]["id_fila"] == 2


def test_adaptador_motores_preserva_filas() -> None:
    motor = SimpleNamespace(
        area="Hacienda",
        equipo="Bomba",
        numero_fases=3,
        potencia_nominal_hp=5,
        corriente_nominal_a=10,
        corriente_medida_a=8,
        horas_operacion_mes=None,
    )
    registros = registros_motores(SimpleNamespace(registros=[motor, motor]))
    assert [registro["id_fila"] for registro in registros] == [2, 3]


def test_guardar_nota_por_contexto(tmp_path: Path) -> None:
    ruta = tmp_path / "notas.sqlite3"
    proyecto = crear_proyecto(ruta, "Parque")
    contexto = {"area": "Hacienda"}

    identificador = guardar_observacion(
        ruta,
        proyecto,
        "inventario",
        "Pareto",
        contexto,
        "Revisar equipos",
    )
    notas = listar_observaciones(
        ruta,
        proyecto,
        "inventario",
        "Pareto",
        contexto,
    )

    assert notas[0].id == identificador
    assert notas[0].texto == "Revisar equipos"
    assert (
        listar_observaciones(
            ruta,
            proyecto,
            "inventario",
            "Pareto",
            {"area": "B"},
        )
        == []
    )


def test_eliminar_nota_protege_otro_proyecto(tmp_path: Path) -> None:
    ruta = tmp_path / "notas.sqlite3"
    uno = crear_proyecto(ruta, "Uno")
    dos = crear_proyecto(ruta, "Dos")
    identificador = guardar_observacion(
        ruta,
        uno,
        "motores",
        "Corriente",
        {},
        "Nota",
    )

    assert not eliminar_observacion(ruta, dos, identificador)
    assert eliminar_observacion(ruta, uno, identificador)


def test_nota_cascada_proyecto(tmp_path: Path) -> None:
    ruta = tmp_path / "notas.sqlite3"
    proyecto = crear_proyecto(ruta, "Temporal")

    guardar_observacion(
        ruta,
        proyecto,
        "motores",
        "Corriente",
        {},
        "Nota",
    )
    assert eliminar_proyecto(ruta, proyecto)
    assert (
        listar_observaciones(
            ruta,
            proyecto,
            "motores",
            "Corriente",
            {},
        )
        == []
    )


@pytest.mark.parametrize(
    "nota",
    ["", "  ", "x" * 2001],
)
def test_nota_invalida(
    tmp_path: Path,
    nota: str,
) -> None:
    ruta = tmp_path / "notas.sqlite3"
    proyecto = crear_proyecto(ruta, "Parque")
    with pytest.raises(ValueError):
        guardar_observacion(
            ruta,
            proyecto,
            "inventario",
            "Pareto",
            {},
            nota,
        )


def test_rechaza_id_y_contexto_no_valido(tmp_path: Path) -> None:
    ruta = tmp_path / "notas.sqlite3"
    proyecto = crear_proyecto(ruta, "Parque")

    with pytest.raises(ValueError):
        listar_observaciones(ruta, True, "motores", "Corriente", {})

    with pytest.raises(ValueError):
        guardar_observacion(
            ruta,
            proyecto,
            "inventario",
            "Pareto",
            {"area": 5},
            "Nota",
        )


@pytest.mark.skipif(
    importlib.util.find_spec("reportlab") is None,
    reason="ReportLab opcional",
)
def test_pdf_valido_con_datos() -> None:
    pdf = generar_informe_pdf(
        "Parque",
        _analisis(),
        origen="Datos de ensayo",
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1500


@pytest.mark.skipif(
    importlib.util.find_spec("reportlab") is None,
    reason="ReportLab opcional",
)
def test_pdf_con_observaciones_y_sin_tabla() -> None:
    pdf = generar_informe_pdf(
        "Parque",
        _analisis(),
        incluir_tabla=False,
        observaciones="Revisar placa",
    )
    assert pdf.startswith(b"%PDF-")


@pytest.mark.parametrize(
    "maximo",
    [0, 51, True],
)
def test_pdf_rechaza_limite_invalido(
    maximo: object,
) -> None:
    with pytest.raises(ValueError):
        generar_informe_pdf(
            "Parque",
            _analisis(),
            maximo_filas=maximo,
        )


def test_pdf_rechaza_proyecto_vacio() -> None:
    with pytest.raises(ValueError):
        generar_informe_pdf(" ", _analisis())
