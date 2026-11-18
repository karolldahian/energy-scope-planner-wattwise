"""Pruebas de integracion de energia sin extrapolar huecos ni sumar puntos."""

from datetime import datetime, timedelta

import pytest

from wattwise.dominio.energia_temporal import analizar_energia_temporal
from wattwise.interfaz.panel_energia import (
    grafico_energia_acumulada,
    grafico_energia_diaria,
)


def _fila(minutos: int, potencia: object, punto: str = "A") -> dict[str, object]:
    return {
        "fecha_hora": datetime(2026, 1, 1) + timedelta(minutes=minutos),
        "frontera": "Parque",
        "area": "Acuario",
        "punto_medicion": punto,
        "p_total_kw": potencia,
    }


def test_potencia_constante_dos_horas() -> None:
    resumen = analizar_energia_temporal([_fila(0, 10), _fila(120, 10)], hueco_maximo_minutos=120)
    assert resumen.importada_kwh == 20
    assert resumen.exportada_kwh == 0
    assert resumen.horas_integradas == 2
    assert resumen.tramos_validos == 1


def test_potencia_cero_se_conserva() -> None:
    resumen = analizar_energia_temporal([_fila(0, 0), _fila(60, 0)], hueco_maximo_minutos=60)
    assert resumen.tramos_validos == 1
    assert resumen.importada_kwh == 0


def test_cambio_de_signo_separa_importacion_y_exportacion() -> None:
    resumen = analizar_energia_temporal([_fila(0, 4), _fila(60, -4)], hueco_maximo_minutos=60)
    assert resumen.importada_kwh == 1
    assert resumen.exportada_kwh == 1
    assert resumen.neta_kwh == 0


def test_hueco_grande_no_se_extrapola() -> None:
    resumen = analizar_energia_temporal(
        [_fila(0, 10), _fila(60, 10), _fila(360, 10)],
        hueco_maximo_minutos=60,
    )
    assert resumen.importada_kwh == 10
    assert resumen.tramos_validos == 1
    assert resumen.tramos_descartados == 1


def test_potencia_faltante_no_se_puentea() -> None:
    resumen = analizar_energia_temporal(
        [_fila(0, 10), _fila(30, None), _fila(60, 10)],
        hueco_maximo_minutos=60,
    )
    assert resumen.tramos_validos == 0
    assert resumen.tramos_descartados == 2


def test_duplicados_excluyen_tramos_adyacentes() -> None:
    resumen = analizar_energia_temporal(
        [_fila(0, 10), _fila(60, 10), _fila(60, 20), _fila(120, 20)],
        hueco_maximo_minutos=60,
    )
    assert resumen.fechas_duplicadas == 1
    assert resumen.tramos_validos == 0
    assert resumen.tramos_descartados == 3


def test_rechaza_mezclar_puntos() -> None:
    with pytest.raises(ValueError, match="mezclar"):
        analizar_energia_temporal(
            [_fila(0, 10, "A"), _fila(60, 10, "B")],
            hueco_maximo_minutos=60,
        )


def test_rechaza_limite_invalido() -> None:
    with pytest.raises(ValueError, match="hueco maximo"):
        analizar_energia_temporal([_fila(0, 10), _fila(60, 10)], hueco_maximo_minutos=0)


def test_corta_tramo_en_medianoche() -> None:
    datos = [_fila(23 * 60 + 30, 4), _fila(24 * 60 + 30, 4)]
    resumen = analizar_energia_temporal(datos, hueco_maximo_minutos=60)
    assert len(resumen.por_dia) == 2
    assert [dia.importada_kwh for dia in resumen.por_dia] == [2, 2]


def test_graficos_usando_resultado_validado() -> None:
    resumen = analizar_energia_temporal([_fila(0, 5), _fila(60, 5)], hueco_maximo_minutos=60)
    diario = grafico_energia_diaria(resumen)
    acumulado = grafico_energia_acumulada(resumen)
    assert diario is not None
    assert acumulado is not None
    assert diario["series"][0]["data"] == [5]
    assert acumulado["series"][0]["data"][0][1] == 5


def test_lista_vacia_rechazada() -> None:
    with pytest.raises(ValueError, match="No existen"):
        analizar_energia_temporal([], hueco_maximo_minutos=60)


def test_un_registro_no_inventa_consumo() -> None:
    resumen = analizar_energia_temporal([_fila(0, 20)], hueco_maximo_minutos=60)
    assert resumen.tramos_validos == 0
    assert resumen.importada_kwh == 0
    assert resumen.por_dia == ()
    assert grafico_energia_diaria(resumen) is None
    assert grafico_energia_acumulada(resumen) is None


def test_orden_entrada_no_afecta_resultado() -> None:
    muestras = [_fila(0, 10), _fila(30, 10), _fila(60, 10)]
    ordenado = analizar_energia_temporal(muestras, hueco_maximo_minutos=60)
    invertido = analizar_energia_temporal(muestras[::-1], hueco_maximo_minutos=60)
    assert ordenado == invertido


def test_intervalo_igual_al_limite_se_admite() -> None:
    resumen = analizar_energia_temporal([_fila(0, 10), _fila(60, 10)], hueco_maximo_minutos=60)
    assert resumen.tramos_validos == 1


def test_rechaza_intervalo_booleano() -> None:
    with pytest.raises(ValueError, match="hueco maximo"):
        analizar_energia_temporal([_fila(0, 10), _fila(60, 10)], hueco_maximo_minutos=True)


def test_rechaza_intervalo_no_entero() -> None:
    with pytest.raises(ValueError, match="hueco maximo"):
        analizar_energia_temporal([_fila(0, 10), _fila(60, 10)], hueco_maximo_minutos=60.5)


def test_no_integra_potencias_infinitas() -> None:
    resumen = analizar_energia_temporal(
        [_fila(0, 10), _fila(60, float("inf"))], hueco_maximo_minutos=60
    )
    assert resumen.tramos_validos == 0


def test_no_integra_booleanos() -> None:
    resumen = analizar_energia_temporal([_fila(0, True), _fila(60, 5)], hueco_maximo_minutos=60)
    assert resumen.tramos_validos == 0


def test_exportacion_neta_negativa() -> None:
    resumen = analizar_energia_temporal([_fila(0, -6), _fila(60, -6)], hueco_maximo_minutos=60)
    assert resumen.importada_kwh == 0
    assert resumen.exportada_kwh == 6
    assert resumen.neta_kwh == -6
    grafico = grafico_energia_diaria(resumen)
    assert grafico is not None
    assert grafico["series"][1]["data"] == [-6]


def test_rechaza_zona_horaria_implicita() -> None:
    from datetime import UTC

    primera = _fila(0, 5)
    primera["fecha_hora"] = primera["fecha_hora"].replace(tzinfo=UTC)
    with pytest.raises(ValueError, match="zonas horarias"):
        analizar_energia_temporal([primera, _fila(60, 5)], hueco_maximo_minutos=60)


def test_no_integra_potencia_por_fase_como_total() -> None:
    primero = _fila(0, None)
    segundo = _fila(60, None)
    primero["p_l1_kw"] = 2.0
    segundo["p_l1_kw"] = 2.0
    resumen = analizar_energia_temporal([primero, segundo], hueco_maximo_minutos=60)
    assert resumen.tramos_validos == 0


def test_no_mezcla_areas_con_mismo_punto() -> None:
    primero = _fila(0, 5)
    segundo = _fila(60, 5)
    segundo["area"] = "Otro lugar"
    with pytest.raises(ValueError, match="mezclar"):
        analizar_energia_temporal([primero, segundo], hueco_maximo_minutos=60)


def test_cruce_asimetrico_por_cero() -> None:
    resumen = analizar_energia_temporal([_fila(0, 6), _fila(60, -2)], hueco_maximo_minutos=60)
    assert resumen.importada_kwh == pytest.approx(2.25)
    assert resumen.exportada_kwh == pytest.approx(0.25)
    assert resumen.neta_kwh == pytest.approx(2)
