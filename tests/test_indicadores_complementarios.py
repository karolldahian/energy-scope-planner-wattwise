"""Pruebas de indicadores de revisión energética con datos parciales."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from wattwise.dominio.energia_temporal import analizar_energia_temporal
from wattwise.dominio.indicadores_complementarios import (
    calcular_desbalance_tension,
    calcular_factor_carga,
)


def _fila(minuto: int, potencia: object = 10.0, **extras: object) -> dict[str, object]:
    fila: dict[str, object] = {
        "fecha_hora": datetime(2026, 1, 1, 8) + timedelta(minutes=minuto),
        "frontera": "Frontera 1",
        "area": "Bombas",
        "punto_medicion": "M1",
        "p_total_kw": potencia,
    }
    fila.update(extras)
    return fila


def _energia(filas: list[dict[str, object]], maximo: int = 60):
    return analizar_energia_temporal(filas, hueco_maximo_minutos=maximo)


def test_factor_carga_constante_es_cien() -> None:
    filas = [_fila(0), _fila(60), _fila(120)]
    assert calcular_factor_carga(filas, _energia(filas)) == pytest.approx(100)


def test_factor_carga_variable_se_pondera_por_tiempo() -> None:
    filas = [_fila(0, 10), _fila(60, 20), _fila(120, 10)]
    assert calcular_factor_carga(filas, _energia(filas)) == pytest.approx(75)


def test_factor_carga_muestras_irregulares_sin_hueco() -> None:
    filas = [_fila(0, 10), _fila(20, 20), _fila(60, 10)]
    assert calcular_factor_carga(filas, _energia(filas)) == pytest.approx(75)


def test_factor_carga_con_ceros_reales_es_calculable() -> None:
    filas = [_fila(0, 0), _fila(60, 20)]
    assert calcular_factor_carga(filas, _energia(filas)) == pytest.approx(50)


def test_factor_carga_todas_cero_no_inventa_valor() -> None:
    filas = [_fila(0, 0), _fila(60, 0)]
    assert calcular_factor_carga(filas, _energia(filas)) is None


@pytest.mark.parametrize("valor", [-10, None, True, float("nan"), float("inf"), "8"])
def test_factor_carga_rechaza_potencia_no_valida(valor: object) -> None:
    filas = [_fila(0, 10), _fila(60, valor)]
    assert calcular_factor_carga(filas, _energia(filas)) is None


def test_factor_carga_rechaza_exportacion_incluso_con_energia_valida() -> None:
    filas = [_fila(0, 10), _fila(60, -10)]
    assert calcular_factor_carga(filas, _energia(filas)) is None


def test_factor_carga_no_oculta_huecos_temporales() -> None:
    filas = [_fila(0, 10), _fila(60, 10), _fila(360, 10)]
    assert calcular_factor_carga(filas, _energia(filas)) is None


def test_factor_carga_no_oculta_fechas_duplicadas() -> None:
    filas = [_fila(0, 10), _fila(60, 10), _fila(60, 10)]
    assert calcular_factor_carga(filas, _energia(filas)) is None


def test_factor_carga_un_registro_no_calculable() -> None:
    filas = [_fila(0, 10)]
    assert calcular_factor_carga(filas, _energia(filas)) is None


def test_factor_carga_cruce_medianoche() -> None:
    filas = [_fila(15 * 60, 10), _fila(16 * 60, 10)]
    assert calcular_factor_carga(filas, _energia(filas)) == pytest.approx(100)


def test_tension_balanceada_es_cero() -> None:
    filas = [_fila(0, v_l1_v=120, v_l2_v=120, v_l3_v=120)]
    resumen = calcular_desbalance_tension(filas)
    assert resumen is not None
    assert resumen.maximo_pct == pytest.approx(0)
    assert resumen.muestras_validas == 1


def test_tension_desbalanceada_calculo_correcto() -> None:
    filas = [_fila(0, v_l1_v=110, v_l2_v=120, v_l3_v=130)]
    resumen = calcular_desbalance_tension(filas)
    assert resumen is not None
    assert resumen.promedio_pct == pytest.approx(100 * 10 / 120)
    assert resumen.p95_pct == pytest.approx(100 * 10 / 120)


def test_tension_descarta_filas_parciales_y_mantiene_cobertura() -> None:
    filas = [
        _fila(0, v_l1_v=110, v_l2_v=120, v_l3_v=130),
        _fila(60, v_l1_v=110, v_l2_v=None, v_l3_v=130),
        _fila(120, v_l1_v=120, v_l2_v=120, v_l3_v=120),
    ]
    resumen = calcular_desbalance_tension(filas)
    assert resumen is not None
    assert resumen.muestras_validas == 2
    assert resumen.muestras_totales == 3
    assert resumen.maximo_pct == pytest.approx(100 * 10 / 120)


@pytest.mark.parametrize("valor", [0, -120, True, float("inf"), float("nan"), "120"])
def test_tension_rechaza_valores_no_validos(valor: object) -> None:
    filas = [_fila(0, v_l1_v=120, v_l2_v=valor, v_l3_v=120)]
    assert calcular_desbalance_tension(filas) is None


def test_tension_sin_registros_no_calculable() -> None:
    assert calcular_desbalance_tension([]) is None


def test_percentil_tension_interpolado() -> None:
    filas = [
        _fila(0, v_l1_v=120, v_l2_v=120, v_l3_v=120),
        _fila(60, v_l1_v=110, v_l2_v=120, v_l3_v=130),
    ]
    resumen = calcular_desbalance_tension(filas)
    assert resumen is not None
    assert resumen.p95_pct == pytest.approx(0.95 * 100 * 10 / 120)


def test_capa_de_interfaz_conectada_a_mediciones() -> None:
    from wattwise.interfaz import mediciones_botones_vistas

    assert (
        mediciones_botones_vistas.mostrar_indicadores_complementarios.__module__
        == "wattwise.interfaz.panel_energia"
    )


def test_factor_carga_no_acepta_puntos_diferentes() -> None:
    filas = [_fila(0, 10), _fila(60, 20)]
    energia = _energia(filas)
    filas[1]["punto_medicion"] = "M2"
    assert calcular_factor_carga(filas, energia) is None


def test_confirmacion_energia_bloquea_calculo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin confirmación no se ejecuta integración ni aparecen kWh."""
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace

    from wattwise.interfaz import panel_energia

    alertas: list[str] = []
    falso_st = SimpleNamespace(
        session_state={"wattwise_proyecto_id": 1},
        subheader=lambda *_: None,
        caption=lambda *_: None,
        info=lambda texto: alertas.append(texto),
        expander=lambda *_: nullcontext(),
        checkbox=lambda *_, **__: False,
        markdown=lambda *_: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", falso_st)
    monkeypatch.setattr(
        panel_energia,
        "analizar_energia_temporal",
        lambda *_, **__: pytest.fail("No integrar antes de confirmar"),
    )
    filas = [_fila(0, 10), _fila(60, 20)]
    panel_energia.mostrar_panel_energia(filas)
    assert any("Confirma" in mensaje for mensaje in alertas)


def test_desbalance_interfaz_sin_fases_no_inventa_cifras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace

    from wattwise.interfaz import panel_energia

    avisos: list[str] = []
    falso_st = SimpleNamespace(
        session_state={"wattwise_proyecto_id": 1},
        subheader=lambda *_: None,
        caption=lambda *_: None,
        info=lambda texto: avisos.append(texto),
        expander=lambda *_: nullcontext(),
        checkbox=lambda *_, **__: False,
        markdown=lambda *_: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", falso_st)
    panel_energia.mostrar_indicadores_complementarios([_fila(0, 10), _fila(60, 10)])
    assert any("no calculable" in aviso for aviso in avisos)


def test_desbalance_interfaz_muestra_metricas_reales(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace

    from wattwise.interfaz import panel_energia

    metricas: list[tuple[str, str]] = []
    columna = SimpleNamespace(metric=lambda label, valor: metricas.append((label, valor)))
    falso_st = SimpleNamespace(
        session_state={"wattwise_proyecto_id": 1},
        subheader=lambda *_: None,
        caption=lambda *_: None,
        info=lambda *_: None,
        expander=lambda *_: nullcontext(),
        checkbox=lambda *_, **__: False,
        markdown=lambda *_: None,
        columns=lambda cantidad: [columna] * cantidad,
    )
    monkeypatch.setitem(sys.modules, "streamlit", falso_st)
    filas = [
        _fila(0, 10, v_l1_v=110, v_l2_v=120, v_l3_v=130),
        _fila(60, 10, v_l1_v=120, v_l2_v=120, v_l3_v=120),
    ]
    panel_energia.mostrar_indicadores_complementarios(filas)
    assert len(metricas) == 3
    assert metricas[2][1] == "8.33 %"
