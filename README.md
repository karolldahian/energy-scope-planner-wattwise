
# Energy Scope Planner

### Plataforma auditable para la integración y el análisis de información energética

**Energy Scope Planner** es un proyecto de desarrollo de software orientado a facilitar la organización, exploración, análisis y documentación de información energética en instalaciones comerciales y de servicios.

Su primera implementación, **WattWise**, es una herramienta funcional de apoyo a la planificación y revisión energética, desarrollada para profesionales del sector eléctrico.

El propósito es transformar información dispersa en archivos y registros de medición en resultados comprensibles, trazables y útiles para la toma de decisiones técnicas.

> **Estado del proyecto:** prototipo funcional en desarrollo y evaluación.

---

## 1. WattWise: primera implementación

WattWise integra en un mismo entorno tres fuentes principales de información:

- Inventarios de cargas eléctricas.
- Mediciones de variables eléctricas.
- Información técnica y operativa de motores.

Permite cargar archivos, explorar indicadores, aplicar filtros, visualizar gráficas interactivas, registrar observaciones profesionales y generar informes técnicos.

**WattWise no sustituye el criterio del ingeniero ni realiza diagnósticos eléctricos concluyentes de manera automática.**

---

## 2. Funcionalidades

### Gestión de proyectos

- Creación y selección de proyectos.
- Organización independiente de la información.
- Almacenamiento local mediante SQLite.
- Conservación de archivos originales asociados a cada proyecto.
- Verificación de integridad mediante SHA-256.

### Inventarios eléctricos

- Importación de inventarios desde Excel.
- Cálculo de indicadores de potencia instalada.
- Análisis de cargas por área y tipo de equipo.
- Diagramas de Pareto.
- Distribución de potencia por tipo de carga.
- Matrices de análisis por área y categoría.

Estas visualizaciones facilitan la identificación de concentraciones de potencia instalada y la priorización de puntos de revisión.

**La potencia instalada no representa directamente el consumo de energía.**

### Mediciones eléctricas

Permite explorar series temporales de variables eléctricas mediante gráficas interactivas.

Entre sus visualizaciones se encuentran:

**Flujos diarios de energía importada y exportada**

- Estimación de energía a partir de series temporales válidas.
- Comparación del comportamiento diario.
- Identificación de periodos de importación y exportación.
- Análisis del intercambio energético en puntos de medición.

**Potencia activa total y por fase**

- Exploración de perfiles temporales de potencia.
- Identificación de máximos y variaciones operativas.
- Comparación del comportamiento entre fases.
- Identificación de periodos relevantes para revisión técnica.

**Desbalance de corriente**

- Evaluación descriptiva del desbalance entre fases.
- Identificación de periodos con valores elevados.
- Apoyo a la priorización de verificaciones de distribución de cargas.

También incorpora visualizaciones de tensión, corriente, factor de potencia y otros indicadores según la disponibilidad de datos.

Las estimaciones energéticas dependen de la calidad y continuidad de las mediciones. No reemplazan registros certificados de facturación.

### Análisis de motores

- Registro de potencia nominal en HP.
- Comparación entre corriente nominal y medida.
- Análisis de horas de operación declaradas.
- Visualización de indicadores y diferencias operativas.
- Identificación de equipos que requieren revisión adicional.

Una corriente superior a la nominal constituye una señal para revisión, pero no demuestra por sí sola una falla o pérdida de eficiencia.

### Calidad de datos

- Revisión de integridad de registros.
- Identificación de valores ausentes e inválidos.
- Diferenciación entre valores cero y datos faltantes.
- Evaluación de continuidad temporal.
- Identificación de condiciones que limitan determinados cálculos.

### Vistas y observaciones

- Configuración de visualizaciones.
- Conservación de vistas de análisis.
- Registro de observaciones del ingeniero.
- Recuperación de información asociada al proyecto.

### Informes técnicos

- Generación de informes PDF.
- Incorporación de indicadores y gráficas.
- Inclusión de observaciones profesionales.
- Organización de resultados por secciones.
- Documentación de hallazgos y análisis realizados.

---

## 3. Arquitectura tecnológica

WattWise utiliza una arquitectura modular desarrollada principalmente en Python.

| Tecnología | Función |
|---|---|
| Python | Desarrollo principal |
| Streamlit | Interfaz de usuario |
| pandas | Procesamiento de datos |
| NumPy | Operaciones numéricas |
| Apache ECharts | Gráficas interactivas |
| SQLite | Persistencia local |
| openpyxl | Lectura de archivos Excel |
| ReportLab | Generación de informes PDF |
| pytest | Pruebas automatizadas |
| Ruff | Análisis estático y formato |
| Git y GitHub | Control de versiones |

### Flujo de funcionamiento

```text
        ENERGY SCOPE PLANNER
                 |
              WattWise
                 |
       Archivos Excel / CSV
                 |
       Lectura y validación
                 |
       Procesamiento de datos
                 |
       Indicadores eléctricos
                 |
      Visualización interactiva
                 |
      Observaciones del ingeniero
                 |
          Informe técnico PDF
```

La aplicación utiliza almacenamiento local y separa la información de los proyectos.

---

## 4. Estructura del proyecto

```text
wattwise/
|
|-- app.py
|
|-- src/
|   |-- wattwise/
|
|-- tests/
|
|-- scripts/
|
|-- pyproject.toml
|-- uv.lock
|-- .python-version
|-- .gitignore
|-- .dockerignore
|-- .pre-commit-config.yaml
|-- .env.example
|-- Makefile
|-- README.md
```

El proyecto separa la lógica de procesamiento, la interfaz y los componentes de persistencia para facilitar las pruebas y el mantenimiento.

---

## 5. Instalación y ejecución

### Requisitos

- Git.
- Python compatible con `pyproject.toml`.
- Gestor de dependencias `uv`.

### Clonar el repositorio

```bash
git clone https://github.com/karolldahian/energy-scope-planner-wattwise.git
cd energy-scope-planner-wattwise
```

### Instalar dependencias

```bash
uv sync
```

### Ejecutar WattWise

```bash
uv run streamlit run app.py
```

Streamlit mostrará una dirección local para abrir la aplicación en el navegador.

El proyecto se ejecuta localmente; la publicación del código en GitHub no representa un despliegue de la aplicación en la nube.

---

## 6. Pruebas y calidad del software

El desarrollo incorpora pruebas automatizadas y verificaciones de calidad del código.

### Análisis estático

```bash
uv run ruff check app.py src tests
```

### Verificación de formato

```bash
uv run ruff format --check app.py src tests
```

### Verificación de sintaxis

```bash
uv run python -m compileall -q app.py src tests
```

### Pruebas automatizadas

```bash
uv run pytest -q
```

Las pruebas permiten detectar errores y regresiones en los componentes evaluados. No constituyen una garantía absoluta de ausencia de errores ni certifican resultados de ingeniería.

---

## 7. Gestión de datos y privacidad

WattWise está diseñado para trabajar con información de instalaciones eléctricas que puede ser confidencial.

Por este motivo, el repositorio no debe incluir:

- Bases de datos locales de proyectos.
- Archivos originales de terceros.
- Inventarios o mediciones confidenciales.
- Credenciales o claves privadas.
- Archivos de configuración con secretos.
- Respaldos de información sensible.

El archivo `.gitignore` establece exclusiones para diferentes formatos de datos, bases SQLite, archivos temporales y configuraciones privadas.

La publicación de código fuente no implica la publicación de los datos utilizados durante el desarrollo.

---

## 8. Evaluación del prototipo

El desarrollo se ha apoyado en:

- Una fuente de referencia académica anonimizada.
- Escenarios sintéticos completos para pruebas funcionales.
- Escenarios sintéticos con datos faltantes, discontinuidades y diferentes condiciones operativas.

Estos conjuntos permiten evaluar la interpretación de archivos, los indicadores, los filtros, la generación de visualizaciones y el comportamiento del sistema ante distintas condiciones de entrada.

Los escenarios sintéticos no representan campañas de medición realizadas directamente en instalaciones reales.

---

## 9. Alcance y limitaciones

WattWise constituye una herramienta de apoyo a la revisión y planificación energética.

Sus resultados deben interpretarse considerando:

- Calidad de los datos de entrada.
- Disponibilidad de mediciones.
- Intervalos temporales.
- Condiciones de operación.
- Alcance de los indicadores implementados.
- Criterio profesional del responsable del análisis.

La aplicación no constituye una certificación de conformidad con ISO 50001, RETIE u otras normas técnicas.

ISO 50001 se considera un referente conceptual para la gestión energética.

---

## 10. Evolución futura

Energy Scope Planner se plantea como una plataforma extensible a nuevos módulos de análisis energético.

Entre las posibles líneas futuras de desarrollo se consideran:

- Líneas base e indicadores de desempeño energético.
- Análisis complementarios de eficiencia energética.
- Integración de nuevas fuentes de datos.
- Detección de anomalías mediante aprendizaje automático.
- Agrupación de perfiles operativos.
- Asistencia contextual mediante inteligencia artificial.
- Nuevas herramientas para apoyar la planificación energética.

Estas funcionalidades corresponden a propuestas de evolución y no deben interpretarse como características actualmente implementadas.

---

## 11. Contexto académico

**Proyecto:** Energy Scope Planner

**Primera implementación:** WattWise

**Institución:** Universidad Autónoma de Occidente, Cali, Colombia.

**Área:** Ingeniería eléctrica y tecnologías de análisis de datos.

**Ponencia:** Desarrollo de una plataforma auditable para la integración y análisis de información energética en instalaciones comerciales y de servicios.

**Evento:** VII Encuentro Internacional de Semilleros de Investigación — EISI 2026.

---

## 12. Estado y propósito

Energy Scope Planner continúa en desarrollo.

WattWise representa su primera implementación funcional y permite demostrar cómo integrar información eléctrica, procesarla, visualizarla y documentar los resultados dentro de un flujo de trabajo organizado.

El objetivo es proporcionar herramientas que fortalezcan el análisis profesional mediante información estructurada, trazable y técnicamente interpretable.

---

**Energy Scope Planner — WattWise**

*Tecnología para apoyar la revisión, documentación y planificación energética.*
