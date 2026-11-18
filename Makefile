
# ============================================================
# ENERGY SCOPE PLANNER - AUTOMATIZACION DE TAREAS DE DESARROLLO
# ============================================================
# Proyecto: Energy Scope Planner
#
# OBJETIVO:
# - Centralizar comandos de desarrollo y mantenimiento.
# - Ejecutar Energy Scope Planner localmente.
# - Verificar formato, tipado, pruebas y seguridad.
# - Generar y comprobar el archivo uv.lock.
# - Construir el paquete Python cuando corresponda.
# - Limpiar caches sin afectar datos privados.
#
# COMPATIBILIDAD:
# - GNU Make 3.82 o superior.
# - Python 3.12.
# - uv.
# - Windows, Linux y macOS con GNU Make instalado.
#
# IMPORTANTE:
# - GNU Make es opcional en Windows.
# - scripts/tareas.py ofrecera comandos equivalentes.
# - No se necesitan servicios de nube ni APIs de pago.
#
# NOTA DE SINTAXIS:
# Se utiliza > como prefijo de recetas para evitar errores
# causados por tabulaciones invisibles.
# ============================================================

# ------------------------------------------------------------
# 1. CONFIGURACION GENERAL
# ------------------------------------------------------------

.DEFAULT_GOAL := ayuda

.RECIPEPREFIX := >

UV := uv

.PHONY: \
    ayuda \
    bloquear \
    comprobar-bloqueo \
    instalar \
    instalar-bloqueado \
    iniciar \
    formato \
    verificar-formato \
    verificar-lint \
    verificar-tipos \
    verificar \
    pruebas \
    pruebas-criticas \
    integracion \
    seguridad-local \
    seguridad-dependencias \
    seguridad \
    precommit \
    revisar \
    construir \
    limpiar

# ------------------------------------------------------------
# 2. AYUDA
# ------------------------------------------------------------

ayuda:
>@echo ""
>@echo "ENERGY SCOPE PLANNER - COMANDOS DISPONIBLES"
>@echo "----------------------------------------"
>@echo "make bloquear                 - Generar o actualizar uv.lock"
>@echo "make comprobar-bloqueo        - Comprobar vigencia de uv.lock"
>@echo "make instalar                 - Instalar dependencias locales"
>@echo "make instalar-bloqueado       - Instalar usando uv.lock"
>@echo "make iniciar                  - Ejecutar Energy Scope Planner en local"
>@echo "make formato                  - Aplicar Ruff formatter"
>@echo "make verificar                - Revisar formato, lint y tipos"
>@echo "make pruebas                  - Ejecutar todas las pruebas"
>@echo "make pruebas-criticas         - Ejecutar pruebas criticas"
>@echo "make integracion              - Ejecutar pruebas de integracion"
>@echo "make seguridad-local          - Analizar seguridad estatica"
>@echo "make seguridad-dependencias   - Auditar dependencias conocidas"
>@echo "make seguridad                - Ejecutar ambas auditorias"
>@echo "make precommit                - Ejecutar todos los hooks"
>@echo "make revisar                  - Verificar, probar y revisar codigo"
>@echo "make construir                - Construir distribucion Python"
>@echo "make limpiar                  - Eliminar caches temporales"
>@echo ""

# ------------------------------------------------------------
# 3. DEPENDENCIAS Y BLOQUEO DE VERSIONES
# ------------------------------------------------------------

bloquear:
> $(UV) lock

comprobar-bloqueo:
> $(UV) lock --check

instalar:
> $(UV) sync

instalar-bloqueado:
> $(UV) sync --locked

# ------------------------------------------------------------
# 4. EJECUCION LOCAL
# ------------------------------------------------------------

iniciar:
> $(UV) run --no-sync streamlit run app.py --server.address 127.0.0.1

# ------------------------------------------------------------
# 5. FORMATO PYTHON
# ------------------------------------------------------------

formato:
> $(UV) run --no-sync ruff format .

verificar-formato:
> $(UV) run --no-sync ruff format --check .

# ------------------------------------------------------------
# 6. ANALISIS ESTATICO
# ------------------------------------------------------------

verificar-lint:
> $(UV) run --no-sync ruff check .

verificar-tipos:
> $(UV) run --no-sync mypy

verificar: verificar-formato verificar-lint verificar-tipos

# ------------------------------------------------------------
# 7. PRUEBAS AUTOMATIZADAS
# ------------------------------------------------------------

pruebas:
> $(UV) run --no-sync pytest

pruebas-criticas:
> $(UV) run --no-sync pytest -m critica

integracion:
> $(UV) run --no-sync pytest -m integracion

# ------------------------------------------------------------
# 8. SEGURIDAD
# ------------------------------------------------------------

# Auditar codigo Python y scripts usando la configuracion
# centralizada de Bandit en pyproject.toml.

seguridad-local:
> $(UV) run --no-sync bandit -c pyproject.toml -r src/wattwise scripts

# Puede necesitar internet para consultar vulnerabilidades.
# No requiere una API de pago.

seguridad-dependencias:
> $(UV) run --no-sync pip-audit

seguridad: seguridad-local seguridad-dependencias

# ------------------------------------------------------------
# 9. HOOKS DE GIT
# ------------------------------------------------------------

precommit:
> $(UV) run --no-sync pre-commit run --all-files

# ------------------------------------------------------------
# 10. REVISION COMPLETA DEL NUCLEO LOCAL
# ------------------------------------------------------------

# No ejecuta consultas externas de seguridad.
# La auditoria de dependencias se ejecuta por separado.

revisar: verificar pruebas seguridad-local

# ------------------------------------------------------------
# 11. CONSTRUCCION DEL PAQUETE
# ------------------------------------------------------------

construir:
> $(UV) build

# ------------------------------------------------------------
# 12. LIMPIEZA SEGURA DE CACHES
# ------------------------------------------------------------

# Elimina unicamente caches y artefactos regenerables.
# No toca datos_locales/, plantillas/, .env ni bases SQLite.
# Tampoco recorre el entorno virtual .venv/.

limpiar:
> $(UV) run --no-sync python -c "from pathlib import Path; import shutil; raices = [Path('src/wattwise'), Path('scripts'), Path('tests')]; [shutil.rmtree(p, ignore_errors=True) for raiz in raices if raiz.is_dir() for p in raiz.rglob('__pycache__')]; [shutil.rmtree(Path(p), ignore_errors=True) for p in ('.pytest_cache', '.mypy_cache', '.ruff_cache', 'build', 'dist')]"

# ============================================================
# FIN DEL MAKEFILE - ENERGY SCOPE PLANNER
# ============================================================
