
# WattWise

Aplicacion local de analisis electrico y energetico.

## Estado del proyecto

WattWise se encuentra en integracion y pruebas.

Las funcionalidades no se consideraran disponibles
para uso de ingenieria hasta verificar su implementacion.

## Arquitectura

- Python 3.12
- Streamlit
- Apache ECharts
- SQLite
- pandas y NumPy
- Pydantic
- ReportLab
- pytest, Ruff, mypy y Bandit

## Principios tecnicos

- Procesamiento local y privacidad de los archivos.
- Validacion antes de realizar calculos electricos.
- Unidades, hipotesis y limitaciones explicitas.
- Separacion entre dominio e interfaz.
- Resultados reproducibles.
- Pruebas automatizadas.
- Ausencia de diagnosticos automaticos sin fundamento.

## Ejecucion

Una vez instaladas las dependencias:

    uv run --no-sync streamlit run app.py --server.address 127.0.0.1

## Alcance

Los modulos de importacion, calculos electricos,
persistencia, visualizacion e informes se
integraran progresivamente.

WattWise no sustituye la responsabilidad profesional
ni certifica el cumplimiento de normativa electrica.
