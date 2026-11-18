"""Genera plantillas XLSX de inventarios electricos WattWise."""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ENCABEZADOS = (
    "equipo",
    "tipo_carga",
    "cantidad",
    "potencia_unitaria_kw",
    "area",
    "frontera",
    "ubicacion_detalle",
)


def crear_plantilla_inventario() -> bytes:
    """Genera una plantilla vacia compatible con el lector."""
    libro = Workbook()
    hoja = libro.active

    if hoja is None:
        raise RuntimeError("No se pudo crear la hoja de inventario.")

    hoja.title = "Inventario"
    hoja.append(ENCABEZADOS)
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = "A1:G1"

    anchos = {
        "A": 30,
        "B": 24,
        "C": 14,
        "D": 25,
        "E": 24,
        "F": 24,
        "G": 32,
    }

    for columna, ancho in anchos.items():
        hoja.column_dimensions[columna].width = ancho

    for celda in hoja[1]:
        celda.font = Font(
            name="Aptos",
            size=11,
            bold=True,
            color="FFFFFF",
        )
        celda.fill = PatternFill(
            fill_type="solid",
            fgColor="17324D",
        )
        celda.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    hoja.row_dimensions[1].height = 32

    validacion_cantidad = DataValidation(
        type="whole",
        operator="greaterThan",
        formula1="0",
        allow_blank=False,
    )
    validacion_cantidad.error = "Ingresa una cantidad entera mayor que cero."
    validacion_cantidad.errorTitle = "Cantidad invalida"
    validacion_cantidad.showErrorMessage = True

    validacion_potencia = DataValidation(
        type="decimal",
        operator="greaterThanOrEqual",
        formula1="0",
        allow_blank=False,
    )
    validacion_potencia.error = "Ingresa una potencia numerica no negativa en kW."
    validacion_potencia.errorTitle = "Potencia invalida"
    validacion_potencia.showErrorMessage = True

    hoja.add_data_validation(validacion_cantidad)
    hoja.add_data_validation(validacion_potencia)

    validacion_cantidad.add("C2:C100001")
    validacion_potencia.add("D2:D100001")

    for numero_fila in range(2, 102):
        hoja[f"D{numero_fila}"].number_format = "0.000"

    salida = BytesIO()
    libro.save(salida)
    libro.close()

    return salida.getvalue()
