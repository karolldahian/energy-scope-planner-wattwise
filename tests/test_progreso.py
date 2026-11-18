"""El avance se calcula sobre hitos explícitos y no supera el 100 %."""

from wattwise.interfaz.progreso import HITOS, porcentaje_avance, proximos_hitos


def test_pesos_suman_cien() -> None:
    assert sum(hito.peso for hito in HITOS) == 100


def test_porcentaje_coincide_con_hitos() -> None:
    assert porcentaje_avance() == sum(hito.peso for hito in HITOS if hito.completo)


def test_pendientes_no_estan_completos() -> None:
    assert len(proximos_hitos()) == sum(not hito.completo for hito in HITOS)
