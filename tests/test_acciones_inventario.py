"""Valida los botones externos sin reemplazar los gráficos originales."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openpyxl import Workbook

from wattwise.dominio.inventario import analizar_inventario
from wattwise.infraestructura.archivos_proyecto import guardar_archivo
from wattwise.infraestructura.lector_inventario_excel import leer_inventario_excel
from wattwise.infraestructura.proyectos_sqlite import crear_proyecto
from wattwise.infraestructura.vistas_sqlite import listar_vistas
from wattwise.interfaz import acciones_inventario as modulo
from wattwise.interfaz.paneles_completos import registros_inventario
from wattwise.interfaz.reproduccion_vistas import reconstruir_vista


@pytest.fixture
def contexto() -> dict[str, Any]:
    """Prepara campos válidos para una vista de inventario."""
    return {
        "ruta": Path("prueba.sqlite3"),
        "proyecto_id": 3,
        "archivo_id": 8,
        "resultado": object(),
        "vista": "Pareto por tipo de carga",
        "filtros": {
            "frontera": "Todos",
            "area": "Todos",
            "tipo_carga": "Todos",
            "equipo": "Todos",
        },
        "opciones": {"linea_barras": True, "acumulado": True, "umbral_80": True},
        "titulo": "Mi vista",
    }


def test_html_exportado_conserva_grafica_y_biblioteca() -> None:
    """Las opciones se exportan completas, sin modificar el dict recibido."""
    grafico = {"series": [{"type": "bar", "data": [1, 2]}], "dataZoom": [{"start": 40}]}
    copia = repr(grafico)
    html = modulo.html_grafica(grafico, "Vista prueba").decode("utf-8")
    assert "echarts.min.js" in html
    assert '"dataZoom": [{"start": 40}]' in html
    assert "min-height: 570px" in html
    assert repr(grafico) == copia


def test_html_no_admite_inyeccion_script() -> None:
    """La información del Excel nunca cierra el script exportado."""
    ataque = '</script><script>alert("x")</script>'
    html = modulo.html_grafica(
        {"series": [{"type": "bar", "data": [1], "name": ataque}]}, ataque
    ).decode("utf-8")
    assert "&lt;/script&gt;" in html
    assert "\\u003c/script\\u003e" in html
    assert ataque not in html


@pytest.mark.parametrize("datos", [{}, {"series": None}, {"series": [float("nan")]}])
def test_html_rechaza_datos_invalidos(datos: dict[str, object]) -> None:
    """No exporta configuraciones sin serialización JSON segura."""
    with pytest.raises(ValueError):
        modulo.html_grafica(datos, "Gráfica")


@pytest.mark.parametrize("nombre", ["..\\mala/../../ruta", "   ", "pareto?.html"])
def test_nombre_exportacion_seguro(nombre: str) -> None:
    """Los nombres nunca contienen separadores de ruta ni extensiones inyectadas."""
    seguro = modulo.nombre_exportacion(nombre)
    assert seguro and "/" not in seguro and "\\" not in seguro and "." not in seguro


def test_guardar_rechaza_excel_ajeno(
    contexto: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rechaza un archivo de proyecto distinto antes de insertar en SQLite."""
    monkeypatch.setattr(modulo, "originales_coincidentes", lambda *_: [SimpleNamespace(id=7)])
    monkeypatch.setattr(modulo, "guardar_vista", lambda *_: pytest.fail("No debía guardar"))
    with pytest.raises(ValueError, match="no coincide"):
        modulo.guardar_configuracion_inventario(**contexto)


@pytest.mark.parametrize("id_invalido", [0, -1, True, "3"])
def test_guardar_rechaza_proyectos_invalidos(id_invalido: object, contexto: dict[str, Any]) -> None:
    """No acepta identificadores ausentes, falsos o texto."""
    contexto["proyecto_id"] = id_invalido
    with pytest.raises(ValueError, match="proyecto"):
        modulo.guardar_configuracion_inventario(**contexto)


def test_guardar_valida_opciones(contexto: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """No acepta campos ajenos o booleanos implícitos."""
    contexto["opciones"]["umbral_80"] = 1
    monkeypatch.setattr(
        modulo, "originales_coincidentes", lambda *_: pytest.fail("Validación tardía")
    )
    with pytest.raises(ValueError, match="Pareto"):
        modulo.guardar_configuracion_inventario(**contexto)


def test_sqlite_guarda_y_reproduce_vista_original(tmp_path: Path) -> None:
    """Integra un Excel real con las mismas funciones y KPI de WattWise."""
    libro = Workbook()
    hoja = libro.active
    hoja.append(["equipo", "tipo_carga", "cantidad", "potencia_unitaria_kw", "area"])
    hoja.append(["Motor A", "Motores", 2, 3.5, "Planta A"])
    memoria = io.BytesIO()
    libro.save(memoria)
    contenido = memoria.getvalue()

    ruta = tmp_path / "proyecto.sqlite3"
    proyecto_id = crear_proyecto(ruta, "Proyecto original")
    archivo_id = guardar_archivo(ruta, proyecto_id, "inventario", "inventario.xlsx", contenido)
    resultado = analizar_inventario(leer_inventario_excel(contenido, "inventario.xlsx"))
    filtros = {campo: "Todos" for campo in ("frontera", "area", "tipo_carga", "equipo")}
    opciones = {campo: True for campo in ("linea_barras", "acumulado", "umbral_80")}
    vista_id = modulo.guardar_configuracion_inventario(
        ruta,
        proyecto_id,
        archivo_id,
        resultado,
        "Pareto por equipo",
        filtros,
        opciones,
        "Mi gráfico bonito",
    )

    guardada = listar_vistas(ruta, proyecto_id)[0]
    reconstruida = reconstruir_vista(
        "inventario", registros_inventario(resultado), guardada.configuracion
    )
    assert guardada.id == vista_id
    assert guardada.archivo_id == archivo_id
    assert guardada.titulo == "Mi gráfico bonito"
    assert reconstruida.grafico["series"][0]["type"] == "bar"
    assert reconstruida.grafico["title"]["text"].startswith("Pareto")


def test_panel_no_cambia_renderizador_nativo() -> None:
    """La integración no reemplaza el ECharts nativo que evita aplastamientos."""
    from inspect import getsource

    from wattwise.interfaz.paneles_completos import mostrar_inventario_completo

    codigo = getsource(mostrar_inventario_completo)
    assert "st.echarts_chart(" in codigo
    assert "height=570" in codigo
    assert "mostrar_echarts_capturable" not in codigo
    assert "mostrar_exportacion_inventario" in codigo
    assert "mostrar_guardado_inventario" in codigo
