"""Plantillas Excel oficiales con columnas obligatorias y opcionales visibles."""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ESQUEMAS = {
    "inventario": (
        "frontera",
        "area",
        "ubicacion_detalle",
        "equipo",
        "tipo_carga",
        "cantidad",
        "potencia_unitaria_kw",
    ),
    "mediciones": (
        "fecha_hora",
        "frontera",
        "area",
        "punto_medicion",
        "p_total_kw",
        "p_l1_kw",
        "p_l2_kw",
        "p_l3_kw",
        "i_total_a",
        "i_l1_a",
        "i_l2_a",
        "i_l3_a",
        "v_total_v",
        "v_l1_v",
        "v_l2_v",
        "v_l3_v",
        "fp_total",
    ),
    "motores": (
        "area",
        "equipo",
        "potencia_nominal_hp",
        "numero_fases",
        "corriente_nominal_a",
        "corriente_medida_a",
        "horas_operacion_mes",
    ),
}

OBLIGATORIAS = {
    "inventario": frozenset({"equipo", "tipo_carga", "cantidad", "potencia_unitaria_kw"}),
    "mediciones": frozenset({"fecha_hora"}),
    "motores": frozenset(ESQUEMAS["motores"]),
}

HOJAS = {
    "inventario": "Inventario",
    "mediciones": "Mediciones",
    "motores": "Motores",
}


def crear_plantilla_completa(tipo: str) -> bytes:
    """Entrega XLSX vacío con encabezados exactos, sin fórmulas ni datos ficticios."""
    if tipo not in ESQUEMAS:
        raise ValueError("El tipo de plantilla no está permitido.")

    libro = Workbook()
    hoja = libro.active
    hoja.title = HOJAS[tipo]
    hoja.freeze_panes = "A2"
    hoja.sheet_view.showGridLines = False
    campos = ESQUEMAS[tipo]

    for indice, campo in enumerate(campos, start=1):
        celda = hoja.cell(row=1, column=indice, value=campo)
        obligatorio = campo in OBLIGATORIAS[tipo]
        celda.fill = PatternFill(
            "solid",
            fgColor="194D70" if obligatorio else "DDEBF2",
        )
        celda.font = Font(
            bold=True,
            color="FFFFFF" if obligatorio else "194D70",
        )
        celda.alignment = Alignment(
            vertical="center",
            wrap_text=True,
        )
        hoja.column_dimensions[get_column_letter(indice)].width = min(34, max(19, len(campo) + 4))

    hoja.row_dimensions[1].height = 34
    hoja.auto_filter.ref = f"A1:{get_column_letter(len(campos))}1"

    salida = BytesIO()
    libro.save(salida)
    libro.close()
    return salida.getvalue()
