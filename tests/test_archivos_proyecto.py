"""Pruebas de guardado seguro y recuperacion de originales por proyecto."""

import sqlite3
from pathlib import Path

import pytest

from wattwise.infraestructura.archivos_proyecto import (
    guardar_archivo,
    listar_archivos,
    recuperar_archivo,
)
from wattwise.infraestructura.proyectos_sqlite import crear_proyecto, eliminar_proyecto
from wattwise.interfaz.panel_archivos import FuenteArchivo


def _crear(tmp_path: Path) -> tuple[Path, int]:
    ruta = tmp_path / "originales.sqlite3"
    return ruta, crear_proyecto(ruta, "Ensayo")


def test_roundtrip_identico_y_hash(tmp_path: Path) -> None:
    ruta, proyecto = _crear(tmp_path)
    original = b"Excel de ensayo con bytes sin cambiar"
    ident = guardar_archivo(ruta, proyecto, "inventario", "01.xlsx", original)
    metadatos, contenido = recuperar_archivo(ruta, proyecto, ident)
    assert contenido == original
    assert metadatos.tamano_bytes == len(original)
    assert len(metadatos.sha256) == 64


def test_reapertura_conserva_nombre_y_tipo(tmp_path: Path) -> None:
    ruta, proyecto = _crear(tmp_path)
    guardar_archivo(ruta, proyecto, "mediciones", "02.xlsx", b"abc")
    archivos = listar_archivos(ruta, proyecto, "mediciones")
    assert len(archivos) == 1
    assert archivos[0].nombre == "02.xlsx"
    assert archivos[0].tipo == "mediciones"


def test_evitar_duplicados_exacto(tmp_path: Path) -> None:
    ruta, proyecto = _crear(tmp_path)
    uno = guardar_archivo(ruta, proyecto, "motores", "M.xlsx", b"a")
    dos = guardar_archivo(ruta, proyecto, "motores", "otro.xlsx", b"a")
    assert uno == dos
    assert len(listar_archivos(ruta, proyecto)) == 1


def test_archivos_diferentes_se_conservan(tmp_path: Path) -> None:
    ruta, proyecto = _crear(tmp_path)
    guardar_archivo(ruta, proyecto, "motores", "M.xlsx", b"a")
    guardar_archivo(ruta, proyecto, "motores", "M.xlsx", b"b")
    assert len(listar_archivos(ruta, proyecto)) == 2


def test_tipo_diferente_no_se_confunde(tmp_path: Path) -> None:
    ruta, proyecto = _crear(tmp_path)
    guardar_archivo(ruta, proyecto, "motores", "M.xlsx", b"a")
    guardar_archivo(ruta, proyecto, "inventario", "I.xlsx", b"a")
    assert len(listar_archivos(ruta, proyecto)) == 2


def test_proyectos_aislados(tmp_path: Path) -> None:
    ruta, uno = _crear(tmp_path)
    dos = crear_proyecto(ruta, "Otro")
    ident = guardar_archivo(ruta, uno, "motores", "motor.xlsx", b"datos")
    assert listar_archivos(ruta, dos) == []
    with pytest.raises(ValueError, match="no encontrado"):
        recuperar_archivo(ruta, dos, ident)


def test_proyecto_inexistente(tmp_path: Path) -> None:
    ruta = tmp_path / "faltante.sqlite3"
    with pytest.raises(ValueError, match="no existe"):
        guardar_archivo(ruta, 500, "motores", "a.xlsx", b"a")


@pytest.mark.parametrize("identificador", [True, 0, -1, "2"])
def test_ids_no_validos(tmp_path: Path, identificador: object) -> None:
    ruta, _ = _crear(tmp_path)
    with pytest.raises(ValueError):
        listar_archivos(ruta, identificador)


@pytest.mark.parametrize("nombre", ["../a.xlsx", "C:\\a.xlsx", "x.csv", "", " archivo.xlsx"])
def test_nombres_inseguros(tmp_path: Path, nombre: str) -> None:
    ruta, proyecto = _crear(tmp_path)
    with pytest.raises(ValueError):
        guardar_archivo(ruta, proyecto, "motores", nombre, b"a")


@pytest.mark.parametrize("tipo", ["", "INVENTARIO", "otro", None])
def test_tipos_invalidos(tmp_path: Path, tipo: object) -> None:
    ruta, proyecto = _crear(tmp_path)
    with pytest.raises(ValueError):
        guardar_archivo(ruta, proyecto, tipo, "a.xlsx", b"a")


def test_csv_solo_mediciones(tmp_path: Path) -> None:
    ruta, proyecto = _crear(tmp_path)
    ident = guardar_archivo(ruta, proyecto, "mediciones", "m.csv", b"fecha_hora\n")
    assert recuperar_archivo(ruta, proyecto, ident)[1] == b"fecha_hora\n"


def test_contenido_vacio_rechazado(tmp_path: Path) -> None:
    ruta, proyecto = _crear(tmp_path)
    with pytest.raises(ValueError, match="25 MiB"):
        guardar_archivo(ruta, proyecto, "motores", "a.xlsx", b"")


def test_contenido_excesivo_rechazado(tmp_path: Path) -> None:
    ruta, proyecto = _crear(tmp_path)
    with pytest.raises(ValueError, match="25 MiB"):
        guardar_archivo(ruta, proyecto, "motores", "a.xlsx", b"a" * (25 * 1024 * 1024 + 1))


def test_fallo_de_integridad_bloquea_reapertura(tmp_path: Path) -> None:
    ruta, proyecto = _crear(tmp_path)
    ident = guardar_archivo(ruta, proyecto, "motores", "a.xlsx", b"correcto")
    with sqlite3.connect(str(ruta)) as conexion:
        conexion.execute(
            "UPDATE archivos_originales SET contenido = ? WHERE id = ?",
            (b"alterado", ident),
        )
    with pytest.raises(ValueError, match="integridad"):
        recuperar_archivo(ruta, proyecto, ident)


def test_eliminacion_proyecto_en_cascada(tmp_path: Path) -> None:
    ruta, proyecto = _crear(tmp_path)
    guardar_archivo(ruta, proyecto, "motores", "a.xlsx", b"datos")
    assert eliminar_proyecto(ruta, proyecto)
    assert listar_archivos(ruta, proyecto) == []


def test_adapter_de_upload() -> None:
    fuente = FuenteArchivo("a.xlsx", b"datos")
    assert fuente.size == 5
    assert fuente.getvalue() == b"datos"
    assert not fuente.guardado


def test_limite_cantidad_archivos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import wattwise.infraestructura.archivos_proyecto as modulo

    ruta, proyecto = _crear(tmp_path)
    monkeypatch.setattr(modulo, "MAXIMO_ARCHIVOS", 1)
    guardar_archivo(ruta, proyecto, "motores", "a.xlsx", b"a")
    with pytest.raises(ValueError, match="limites de almacenamiento"):
        guardar_archivo(ruta, proyecto, "motores", "b.xlsx", b"b")


def test_limite_bytes_por_proyecto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import wattwise.infraestructura.archivos_proyecto as modulo

    ruta, proyecto = _crear(tmp_path)
    monkeypatch.setattr(modulo, "MAXIMO_PROYECTO_BYTES", 3)
    guardar_archivo(ruta, proyecto, "motores", "a.xlsx", b"ab")
    with pytest.raises(ValueError, match="limites de almacenamiento"):
        guardar_archivo(ruta, proyecto, "motores", "b.xlsx", b"cd")


def test_seleccion_archivo_guardado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import SimpleNamespace

    from wattwise.interfaz.panel_archivos import seleccionar_fuente

    ruta, proyecto = _crear(tmp_path)
    guardar_archivo(ruta, proyecto, "motores", "m.xlsx", b"original")
    fake_st = SimpleNamespace(
        session_state={"wattwise_proyecto_id": proyecto},
        radio=lambda *_args, **_kw: "Abrir archivo guardado",
        selectbox=lambda _titulo, opciones, **_kw: list(opciones)[0],
        caption=lambda *_args: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    fuente = seleccionar_fuente(ruta, "motores", ["xlsx"])
    assert fuente is not None
    assert fuente.guardado
    assert fuente.name == "m.xlsx"
    assert fuente.getvalue() == b"original"


def test_seleccion_archivo_nuevo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Subir un archivo lo archiva automáticamente, sin otro botón."""
    import sys
    from types import SimpleNamespace

    from wattwise.interfaz.panel_archivos import seleccionar_fuente

    ruta, proyecto = _crear(tmp_path)
    fake_upload = SimpleNamespace(name="m.xlsx", getvalue=lambda: b"libro")
    fake_st = SimpleNamespace(
        session_state={"wattwise_proyecto_id": proyecto},
        radio=lambda *_args, **_kw: "Subir archivo",
        file_uploader=lambda *_args, **_kw: fake_upload,
        caption=lambda *_args: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    fuente = seleccionar_fuente(ruta, "motores", ["xlsx"])
    assert fuente is not None
    assert fuente.guardado
    assert fuente.getvalue() == b"libro"
    guardados = listar_archivos(ruta, proyecto, "motores")
    assert len(guardados) == 1
    assert recuperar_archivo(ruta, proyecto, guardados[0].id)[1] == b"libro"

    # Las reejecuciones de Streamlit no generan duplicados de originales.
    seleccionar_fuente(ruta, "motores", ["xlsx"])
    assert len(listar_archivos(ruta, proyecto, "motores")) == 1


def test_origenes_restringidos_al_proyecto_activo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ni el listado ni la recuperación muestran archivos de otro proyecto."""
    import sys
    from types import SimpleNamespace

    from wattwise.interfaz.panel_archivos import seleccionar_fuente

    ruta, a = _crear(tmp_path)
    b = crear_proyecto(ruta, "Segundo")
    guardar_archivo(ruta, a, "motores", "privado.xlsx", b"datos A")
    guardar_archivo(ruta, b, "motores", "nuevo.xlsx", b"datos B")
    opciones_observadas: list[list[str]] = []

    def elegir(_titulo: str, opciones: object, **_kwargs: object) -> str:
        opciones_observadas.append(list(opciones))
        return list(opciones)[0]

    estado = {"wattwise_proyecto_id": b}
    fake_st = SimpleNamespace(
        session_state=estado,
        radio=lambda *_args, **_kw: "Abrir archivo guardado",
        selectbox=elegir,
        caption=lambda *_args: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    fuente = seleccionar_fuente(ruta, "motores", ["xlsx"])
    assert fuente is not None
    assert fuente.getvalue() == b"datos B"
    assert "privado.xlsx" not in " ".join(opciones_observadas[0])
    estado["wattwise_proyecto_id"] = a
    otra = seleccionar_fuente(ruta, "motores", ["xlsx"])
    assert otra is not None
    assert otra.getvalue() == b"datos A"


def test_no_importar_sin_proyecto(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Sin proyecto se bloquea la subida y no se almacena ningún archivo."""
    import sys
    from types import SimpleNamespace

    from wattwise.interfaz.panel_archivos import seleccionar_fuente

    ruta, proyecto = _crear(tmp_path)
    mensajes: list[str] = []
    fake_st = SimpleNamespace(
        session_state={},
        info=lambda texto: mensajes.append(texto),
        radio=lambda *_a, **_kw: pytest.fail("No debe mostrar cargador sin proyecto"),
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    assert seleccionar_fuente(ruta, "motores", ["xlsx"]) is None
    assert mensajes
    assert listar_archivos(ruta, proyecto) == []


def test_archivar_proyecto_b_sin_modificar_a(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """El mismo cargador guarda bytes idénticos en el proyecto elegido."""
    import sys
    from types import SimpleNamespace

    from wattwise.interfaz.panel_archivos import seleccionar_fuente

    ruta, a = _crear(tmp_path)
    b = crear_proyecto(ruta, "Segundo")
    upload = SimpleNamespace(name="equipo.xlsx", getvalue=lambda: b"fichero exacto")
    estado = {"wattwise_proyecto_id": a}
    fake_st = SimpleNamespace(
        session_state=estado,
        radio=lambda *_a, **_kw: "Subir archivo",
        file_uploader=lambda *_a, **_kw: upload,
        caption=lambda *_a: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    seleccionar_fuente(ruta, "motores", ["xlsx"])
    estado["wattwise_proyecto_id"] = b
    seleccionar_fuente(ruta, "motores", ["xlsx"])
    archivos_a = listar_archivos(ruta, a)
    archivos_b = listar_archivos(ruta, b)
    assert len(archivos_a) == len(archivos_b) == 1
    assert archivos_a[0].id != archivos_b[0].id
    assert recuperar_archivo(ruta, a, archivos_a[0].id)[1] == b"fichero exacto"
    assert recuperar_archivo(ruta, b, archivos_b[0].id)[1] == b"fichero exacto"


def test_cambio_proyecto_limpia_widgets_sin_tocar_originales(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No se conserva texto, uploader ni nota temporal al pasar de A a B."""
    import sys
    from types import SimpleNamespace

    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace())
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    import app

    ruta, a = _crear(tmp_path)
    b = crear_proyecto(ruta, "Segundo")
    guardar_archivo(ruta, a, "inventario", "a.xlsx", b"original A")
    estado: dict[str, object] = {
        "wattwise_proyecto_id": b,
        "wattwise_proyecto_elegido": b,
        "_ww_contexto_proyecto": a,
        "fuente_subir_inventario_1": "archivo anterior",
        "nt_observacion_a": "nota antigua",
        "md_grafica_para_guardar": "grafico anterior",
    }

    class StreamlitFalso:
        session_state = estado

        @staticmethod
        def error(_texto: str) -> None:
            pytest.fail("No debería haber errores")

    monkeypatch.setattr(app, "st", StreamlitFalso())
    monkeypatch.setattr(app, "RUTA_PROYECTOS", ruta)
    assert app._sincronizar_contexto_proyecto() == "Segundo"
    assert estado["wattwise_proyecto_id"] == b
    assert estado["wattwise_proyecto_elegido"] == b
    assert estado["_ww_contexto_proyecto"] == b
    assert "nt_observacion_a" not in estado
    assert "fuente_subir_inventario_1" not in estado
    assert "md_grafica_para_guardar" not in estado
    assert recuperar_archivo(ruta, a, listar_archivos(ruta, a)[0].id)[1] == b"original A"


def test_proyecto_eliminado_no_queda_activo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """El contexto inválido se desactiva antes de utilizar otras pestañas."""
    import sys
    from types import SimpleNamespace

    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace())
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    import app

    ruta, a = _crear(tmp_path)
    eliminar_proyecto(ruta, a)
    estado: dict[str, object] = {
        "wattwise_proyecto_id": a,
        "_ww_contexto_proyecto": a,
        "texto_pendiente": "no mostrar",
    }
    fake = type("StreamlitFalso", (), {"session_state": estado})
    monkeypatch.setattr(app, "st", fake)
    monkeypatch.setattr(app, "RUTA_PROYECTOS", ruta)
    assert app._sincronizar_contexto_proyecto() is None
    assert estado["wattwise_proyecto_id"] is None
    assert "texto_pendiente" not in estado
