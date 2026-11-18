"""Genera una plantilla XLSX compatible con el lector de motores."""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from wattwise.infraestructura.lector_motores_excel import COLUMNAS

ANCHO_COLUMNAS = (22, 30, 22, 16, 23, 22, 23)


def crear_plantilla_motores() -> bytes:
    """Crea una plantilla vacia, sin estimaciones ni datos ficticios."""
    libro = Workbook()
    hoja = libro.active
    if hoja is None:
        raise RuntimeError("No se pudo crear la hoja de motores.")

    hoja.title = "Motores"
    hoja.append(COLUMNAS)
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = "A1:G1001"

    for celda, ancho in zip(hoja[1], ANCHO_COLUMNAS, strict=True):
        celda.font = Font(color="FFFFFF", bold=True)
        celda.fill = PatternFill(fill_type="solid", fgColor="16324F")
        celda.alignment = Alignment(horizontal="center", wrap_text=True)
        hoja.column_dimensions[celda.column_letter].width = ancho

    hoja.row_dimensions[1].height = 34

    fases = DataValidation(type="list", formula1='"1,3"', allow_blank=True)
    fases.error = "Solo se admiten 1 o 3 fases."
    fases.errorTitle = "Numero de fases invalido"
    fases.showErrorMessage = True
    hoja.add_data_validation(fases)
    fases.add("D2:D1001")

    instrucciones = libro.create_sheet("Instrucciones")
    instrucciones.append(("Campo", "Unidad / descripcion"))

    descripciones = (
        "Area o ubicacion del motor",
        "Identificador del equipo",
        "Potencia mecanica nominal de placa en HP",
        "Numero de fases: 1 o 3",
        "Corriente nominal en amperios",
        "Corriente medida en amperios",
        "Horas declaradas de operacion durante un mes (0 a 744)",
    )

    for columna, descripcion in zip(COLUMNAS, descripciones, strict=True):
        instrucciones.append((columna, descripcion))

    instrucciones.column_dimensions["A"].width = 30
    instrucciones.column_dimensions["B"].width = 75
    instrucciones.freeze_panes = "A2"
    instrucciones["A1"].font = Font(bold=True)
    instrucciones["B1"].font = Font(bold=True)

    salida = BytesIO()
    libro.save(salida)
    libro.close()
    return salida.getvalue()
