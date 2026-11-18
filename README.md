
# ⚡ Energy Scope Planner

### Plataforma auditable para la integración y el análisis de información energética

**Energy Scope Planner** es un proyecto de software orientado a organizar, explorar, analizar y documentar información energética de instalaciones comerciales y de servicios. Su primera implementación es **WattWise**, una aplicación local que apoya la **planificación y revisión energética** a partir de inventarios eléctricos, mediciones y datos operativos de motores.

El objetivo es convertir archivos y registros dispersos en información estructurada, visualizaciones interpretables, observaciones técnicas e informes trazables, **sin reemplazar el criterio del profesional de ingeniería**.

> **Estado:** prototipo funcional en desarrollo y evaluación. Las capacidades futuras se distinguen expresamente de las que ya están implementadas.

**Repositorio:** [energy-scope-planner-wattwise](https://github.com/karolldahian/energy-scope-planner-wattwise)

---

## 1. ¿Qué es WattWise?

WattWise es el **primer módulo funcional de Energy Scope Planner**. Centraliza tres tipos de información:

1. **Inventarios eléctricos:** equipos, cantidades, potencias nominales, áreas y tipos de carga.
2. **Mediciones eléctricas:** series temporales de potencia, energía estimada, tensión, corriente y otras variables disponibles.
3. **Motores:** datos nominales, corrientes medidas y horas de operación declaradas.

La aplicación permite crear proyectos, cargar y conservar archivos fuente, revisar la calidad de los datos, explorar indicadores, filtrar gráficas, guardar vistas y observaciones, y elaborar informes en PDF.

**Alcance:** WattWise es una herramienta de apoyo al análisis. No diagnostica automáticamente fallas, no certifica mediciones y no garantiza cumplimiento normativo.

---

## 2. Funcionalidades implementadas

| Área | ¿Qué permite hacer? | ¿Para qué sirve? |
|---|---|---|
| **Inicio** | Presentar la plataforma y sus capacidades. | Orientar el flujo de trabajo del usuario. |
| **Proyectos** | Crear, seleccionar y organizar proyectos separados. | Evitar mezclar información de instalaciones distintas. |
| **Inventarios** | Calcular potencia instalada y generar Pareto, barras por área, distribución por carga y matrices. | Identificar concentraciones de potencia instalada y prioridades de revisión. |
| **Mediciones** | Explorar series temporales, potencia por fase, perfiles horarios, energía importada/exportada estimada y desbalances. | Detectar periodos y variables que ameritan revisión profesional. |
| **Motores** | Comparar corrientes medidas y nominales, potencias mecánicas y horas de operación. | Señalar equipos que requieren comprobaciones adicionales. |
| **Calidad de datos** | Revisar integridad, valores faltantes, registros inválidos y continuidad temporal. | Conocer la confiabilidad y los límites de los resultados. |
| **Vistas y observaciones** | Guardar configuraciones de gráficas, capturas y notas vinculadas a proyectos. | Facilitar la revisión posterior y la trazabilidad. |
| **Informes** | Preparar PDF con indicadores, imágenes seleccionadas y comentarios técnicos. | Comunicar y documentar el análisis. |

### Visualizaciones destacadas de Mediciones

- **Flujos diarios de energía importada y exportada:** muestran la estimación de energía por jornada, diferenciando el sentido del flujo cuando los datos lo permiten.
- **Potencia activa total y por fase:** permite reconocer perfiles operativos, máximos y distribución de potencia entre fases.
- **Desbalance de corriente:** ayuda a localizar intervalos que merecen comprobarse por posibles diferencias relevantes entre fases.

Los valores calculados dependen de la calidad de los datos, su intervalo temporal y el punto de medición. **No se deben combinar automáticamente fronteras eléctricas diferentes ni interpretar la energía estimada como una factura certificada.**

### Límites de interpretación importantes

- **Potencia instalada ≠ demanda máxima ≠ energía consumida.**
- **Corriente medida superior a nominal ≠ diagnóstico automático de falla.**
- **Registro cero ≠ dato faltante.**
- Un indicador descriptivo o un umbral de revisión no sustituye las verificaciones eléctricas de campo.

---

## 3. Arquitectura tecnológica

WattWise utiliza una organización modular en Python. La interfaz presenta y recoge acciones del usuario; el dominio contiene las reglas y los cálculos; y la infraestructura se ocupa de archivos, almacenamiento local y reportes.

### 3.1. Tecnologías y su función

| Tecnología / herramienta | Función en WattWise |
|---|---|
| **Python 3.12** | Lenguaje base; conecta los módulos y ejecuta los cálculos. |
| **Streamlit** | Interfaz local: navegación, formularios, filtros, indicadores y paneles. |
| **pandas** | Lectura, organización y transformación de tablas y series temporales. |
| **NumPy** | Operaciones numéricas de apoyo al procesamiento. |
| **Apache ECharts** | Gráficas interactivas, zoom, series seleccionables y capturas. |
| **SQLite** | Persistencia local de proyectos, archivos asociados, vistas y observaciones. |
| **openpyxl** | Lectura y creación de archivos Excel (`.xlsx`). |
| **ReportLab** | Construcción de informes PDF con texto, resultados e imágenes. |
| **`hashlib` / SHA-256** | Huellas de integridad para archivos originales almacenados. |
| **`pathlib`** | Manejo de archivos y rutas del proyecto. |
| **pytest** | Pruebas automatizadas de lógica, lectura, almacenamiento e interfaz. |
| **Ruff** | Comprobación de estilo, importaciones, errores y complejidad del código. |
| **uv** | Gestión del entorno, las dependencias y la ejecución. |
| **Git / GitHub** | Historial y alojamiento del código fuente. |
| **VS Code** | Edición y mantenimiento del código. |

**Nota:** las tecnologías listadas describen el desarrollo actual; esto no implica que WattWise tenga un servicio de IA desplegado. Las funciones de aprendizaje automático siguen siendo propuestas de evolución.

### 3.2. Responsabilidad de cada capa

| Capa | Ubicación | Responsabilidad |
|---|---|---|
| **Entrada y navegación** | `app.py` | Inicia Streamlit, configura la aplicación y conecta los paneles. |
| **Dominio** | `src/wattwise/dominio/` | Valida conceptos eléctricos, calcula indicadores y expresa reglas de negocio. |
| **Infraestructura** | `src/wattwise/infraestructura/` | Lee archivos, conserva originales, gestiona SQLite y genera informes. |
| **Interfaz** | `src/wattwise/interfaz/` | Muestra paneles, gráficas, controles de usuario, capturas y exportaciones. |
| **Pruebas** | `tests/` | Comprueba reglas, entradas, persistencia e interacciones relevantes. |

### 3.3. Flujo de información

```text
ENERGY SCOPE PLANNER (plataforma general)
└── WATTWISE (primer módulo funcional)
    │
    ├── Usuario crea o selecciona un proyecto
    │
    ├── Carga archivos Excel / CSV
    │       └── Lectores + validaciones de estructura y calidad
    │
    ├── Análisis del dominio
    │       ├── Inventarios y potencia instalada
    │       ├── Mediciones y series temporales
    │       ├── Energía estimada y continuidad
    │       ├── Motores y variables nominales/medidas
    │       └── Calidad de datos y comparaciones condicionadas
    │
    ├── Interfaz Streamlit + gráficas ECharts
    │       └── Filtros, indicadores y selección de visualizaciones
    │
    ├── SQLite + archivos originales + huellas SHA-256
    │       └── Proyectos, vistas, capturas y observaciones
    │
    └── ReportLab
            └── Informe PDF con resultados y notas del ingeniero
```

El flujo no es exclusivamente lineal: el usuario puede regresar a sus archivos originales, modificar filtros, reconstruir vistas y actualizar observaciones dentro de un mismo proyecto.

---

## 4. Estructura del código fuente

El siguiente árbol muestra el paquete principal **`src/wattwise/` abierto por completo**, con una explicación breve al lado de cada archivo. Se omiten cachés, entornos virtuales y datos locales porque no son parte del código que se publica.

```text
wattwise/                                   # Carpeta local del proyecto
│
├── app.py                                  # Entrada de la aplicación Streamlit
│
├── src/
│   └── wattwise/                          # Paquete Python principal
│       ├── __init__.py                    # Identifica el paquete WattWise
│       │
│       ├── dominio/                       # REGLAS ELÉCTRICAS Y CÁLCULOS
│       │   ├── calidad_integral.py        # Audita datos originales y genera hallazgos por hoja/columna
│       │   ├── calidad_mediciones.py      # Evalúa cobertura y continuidad de series temporales
│       │   ├── comparacion.py             # Compara potencia declarada con un pico medido compatible
│       │   ├── energia_temporal.py        # Estima energía respetando tiempos, signos y huecos de datos
│       │   ├── inventario.py              # Valida inventarios y calcula potencia y cantidades
│       │   ├── mediciones.py              # Valida mediciones y calcula resúmenes básicos
│       │   ├── motores.py                 # Analiza datos nominales, corrientes y motores
│       │   └── vistas.py                  # Valida configuraciones reproducibles de gráficas
│       │
│       ├── infraestructura/               # ARCHIVOS, BASE DE DATOS Y REPORTES
│       │   ├── analisis_sqlite.py         # Guarda y consulta análisis asociados a proyectos
│       │   ├── archivos_proyecto.py       # Conserva originales y comprueba su huella SHA-256
│       │   ├── capturas_sqlite.py         # Almacena capturas PNG por proyecto
│       │   ├── capturas_vistas_sqlite.py   # Guarda capturas ECharts y notas ligadas a vistas
│       │   ├── comparaciones_sqlite.py    # Persiste comparaciones y referencias de origen
│       │   ├── informes_pdf.py            # Genera informes descriptivos en PDF
│       │   ├── informe_graficas_pdf.py    # Construye PDF con capturas gráficas seleccionadas
│       │   ├── informe_por_secciones.py   # Gestiona borradores e informes por análisis
│       │   ├── lector_inventario_excel.py # Importa inventarios XLSX con límites de validación
│       │   ├── lector_mediciones_csv.py   # Importa mediciones CSV y valida su estructura
│       │   ├── lector_mediciones_detalladas.py # Lee XLSX con variables parciales o ausentes
│       │   ├── lector_mediciones_excel.py # Importa mediciones XLSX sin alterar la fuente
│       │   ├── lector_motores_excel.py    # Importa datos de motores desde XLSX
│       │   ├── notas_calidad_sqlite.py    # Almacena observaciones vinculadas a calidad de datos
│       │   ├── observaciones_sqlite.py    # Guarda notas técnicas por proyecto y contexto
│       │   ├── plantillas_completas.py    # Genera plantillas oficiales de carga de datos
│       │   ├── plantilla_inventario.py    # Genera plantilla de inventarios eléctricos
│       │   ├── plantilla_motores.py       # Genera plantilla de motores
│       │   ├── proyectos_sqlite.py        # Crea, consulta y elimina metadatos de proyectos
│       │   └── vistas_sqlite.py           # Guarda, consulta y elimina vistas reproducibles
│       │
│       └── interfaz/                      # PANTALLAS, GRÁFICAS Y ACCIONES
│           ├── acciones_inventario.py     # Exporta y guarda análisis de inventarios
│           ├── echarts_capturable.py      # Captura gráficas ECharts y su estado visual
│           ├── exportacion_html.py        # Exporta gráficas ECharts a documentos HTML
│           ├── graficos.py                # Define opciones base de gráficas eléctricas
│           ├── graficos_completos.py      # Gráficas e indicadores ampliados de inventarios/motores
│           ├── graficos_mediciones_adaptativos.py # Perfiles horarios y gráficas de mediciones
│           ├── graficos_mediciones_extra.py # Mapas y perfiles horarios complementarios
│           ├── guardado_inventario_capturado.py # Vincula capturas con su inventario fuente
│           ├── guardar_vista_final.py     # Guarda vistas desde los paneles de análisis
│           ├── informe_secciones_ui.py    # Presenta la edición de informes por secciones
│           ├── mediciones_avanzadas.py    # Panel avanzado de variables y estadísticas
│           ├── mediciones_botones_vistas.py # Controles de acciones/vistas de Mediciones
│           ├── paneles_botones_vistas.py  # Controles de Inventarios y Motores
│           ├── paneles_completos.py       # Dashboards con filtros, KPI y notas técnicas
│           ├── panel_archivos.py          # Selección y reapertura de archivos de proyectos
│           ├── panel_calidad_integral.py  # Pantalla de hallazgos y observaciones de calidad
│           ├── panel_comparacion.py       # Comparación condicionada de inventario y medición
│           ├── panel_energia.py           # Gráficas de energía diaria y acumulada
│           ├── panel_guardado_inventario.py # Captura y guardado de vistas de inventarios
│           ├── panel_informes.py          # Selección de análisis y exportación de PDF
│           ├── panel_vistas.py            # Explora y administra vistas guardadas
│           ├── progreso.py               # Registra hitos verificables del desarrollo
│           └── reproduccion_vistas.py     # Reconstruye vistas desde originales y filtros
│
├── tests/                                 # Pruebas automatizadas (archivos test_*.py)
│   ├── test_inventario.py                 # Indicadores y validación de inventarios
│   ├── test_mediciones.py                 # Validación y resumen de mediciones
│   ├── test_motores.py                    # Indicadores y validación de motores
│   ├── test_energia_temporal.py           # Integración temporal y condiciones de cálculo
│   ├── test_calidad_integral.py           # Auditoría de calidad de datos
│   ├── test_archivos_proyecto.py          # Almacenamiento seguro de archivos originales
│   ├── test_proyectos_sqlite.py           # Persistencia y aislamiento entre proyectos
│   ├── test_vistas_reproducibles.py       # Guardado y reconstrucción de vistas
│   ├── test_capturas_informes.py          # Capturas y generación de informes
│   └── ...                                # Otras pruebas de gráficos, lectores y paneles
│
├── .vscode/                               # Preferencias del entorno de edición
│   └── settings.json
│
├── pyproject.toml                         # Metadatos, dependencias y configuración de QA
├── uv.lock                                # Versiones resueltas de las dependencias
├── .python-version                        # Versión objetivo: Python 3.12
├── .gitignore                             # Exclusiones de datos, bases y archivos privados
├── .dockerignore                          # Exclusiones para contextos de construcción
├── .pre-commit-config.yaml                # Configuración de comprobaciones pre-commit
├── .env.example                           # Ejemplo de variables, sin credenciales reales
├── Makefile                               # Atajos para tareas de desarrollo y verificación
└── README.md                              # Documentación del proyecto
```

### 4.1. ¿Qué hace cada carpeta de `src/wattwise/`?

**`dominio/` — lógica de ingeniería.** Reúne las reglas que dan significado a los datos eléctricos: validación de registros, potencia instalada, estimación de energía, comparación de señales compatibles, auditoría temporal y revisión descriptiva de motores. Su objetivo es que los resultados no dependan directamente de cómo se dibujan las gráficas.

**`infraestructura/` — comunicación con archivos y almacenamiento.** Contiene lectores de Excel/CSV, plantillas, operaciones con SQLite, recuperación de archivos originales, huellas de integridad y generación de informes PDF. Su objetivo es conservar los datos y permitir recuperar el contexto de los análisis.

**`interfaz/` — experiencia de uso.** Implementa los paneles Streamlit, las opciones ECharts, los filtros, la captura de gráficas, las vistas guardadas y la selección de contenidos para informes. Presenta los resultados y permite la interacción del usuario con el dominio y la infraestructura.

**`tests/` — comprobación del comportamiento.** Incluye pruebas de reglas eléctricas, importación de datos, persistencia por proyecto, gráficos, capturas e informes. La existencia de pruebas no equivale a garantía de funcionamiento ni certificación de ingeniería.

### 4.2. Separación de responsabilidades

- La **interfaz** solicita acciones y muestra resultados; no debe inventar mediciones ausentes.
- El **dominio** calcula y valida lo que los datos permiten sostener.
- La **infraestructura** lee y guarda información sin alterar silenciosamente los originales.
- Las **pruebas** buscan detectar errores y regresiones al modificar el software.

Esta separación facilita mantenimiento, revisión del código y futuras ampliaciones de Energy Scope Planner.

---

## 5. Instalación y ejecución local

### Requisitos

- **Python 3.12**, según `.python-version` y `pyproject.toml`.
- **Git**.
- **uv**, gestor de entornos y dependencias de Python.

### Clonar el repositorio

```bash
git clone https://github.com/karolldahian/energy-scope-planner-wattwise.git
cd energy-scope-planner-wattwise
```

### Instalar las dependencias

```bash
uv sync --locked
```

### Iniciar la aplicación

```bash
uv run streamlit run app.py
```

La terminal mostrará la dirección local donde abrir WattWise (habitualmente `http://localhost:8501`). La publicación del código en GitHub **no despliega por sí misma** la aplicación en Internet.

> Los proyectos y archivos que un usuario carga en la aplicación se almacenan localmente. El archivo `data/proyectos.sqlite3` y los datos privados no forman parte del repositorio.

---

## 6. Pruebas y calidad del software

El repositorio incorpora verificaciones para detectar errores, problemas de formato y regresiones.

**Análisis estático e importaciones:**

```bash
uv run ruff check app.py src tests
```

**Formato:**

```bash
uv run ruff format --check app.py src tests
```

**Compilación de módulos Python:**

```bash
uv run python -m compileall -q app.py src tests
```

**Pruebas automatizadas:**

```bash
uv run pytest -q
```

El archivo `pyproject.toml` configura, entre otras reglas, la organización de importaciones y el límite de complejidad ciclomática (`C901`, máximo 10). Los resultados de estas verificaciones deben obtenerse mediante ejecución real; esta documentación no afirma que las pruebas pasen en cualquier entorno.

---

## 7. Datos, trazabilidad y privacidad

WattWise incorpora un enfoque de revisión documentada que incluye:

- **Identidad por proyecto:** separación de información y análisis de diferentes instalaciones.
- **Archivos originales:** conservación y recuperación dentro del almacenamiento local.
- **Integridad:** huellas SHA-256 para comprobar la correspondencia de archivos guardados.
- **Contexto:** asociación de observaciones, vistas y capturas con sus fuentes cuando corresponde.
- **Calidad:** indicación de ausencias, irregularidades y límites de cálculo, sin inventar valores.

Por privacidad y seguridad, el repositorio **no debe contener** bases de datos de proyectos, mediciones o inventarios confidenciales, claves privadas, archivos `.env` reales ni respaldos personales. `.gitignore` ayuda a excluirlos, pero también se debe revisar manualmente el contenido antes de cada publicación.

El procesamiento es local y no requiere publicar en GitHub los datos eléctricos utilizados por el usuario.

---

## 8. Evaluación del prototipo

El desarrollo y las revisiones funcionales se han apoyado en tres tipos de material:

1. **Fuente de referencia académica anonimizada**, utilizada bajo un contexto de evaluación.
2. **Escenario sintético completo**, con información consistente para probar recorridos funcionales.
3. **Escenario sintético con incidencias**, incluyendo datos faltantes, discontinuidades y distintas condiciones operativas.

Estos materiales sirven para ejercitar lecturas, indicadores, visualizaciones, filtros y reportes. **Los escenarios sintéticos no son mediciones de campo realizadas por el proyecto**, y los resultados sobre esas fuentes no deben generalizarse como validación universal de ingeniería.

---

## 9. Alcance y limitaciones técnicas

WattWise es una herramienta para **apoyar** la planificación y revisión energética, no para emitir por sí sola dictámenes eléctricos definitivos.

La interpretación de sus resultados depende de la calidad de los datos, los intervalos de medición, la identidad del punto eléctrico, las condiciones operativas y la revisión del profesional responsable.

La herramienta **no acredita cumplimiento ni certificación** con ISO 50001, RETIE u otras normas. ISO 50001 se contempla como referencia conceptual para la gestión energética, no como condición certificada del software.

---

## 10. Evolución prevista de Energy Scope Planner

Como plataforma general, Energy Scope Planner puede crecer mediante módulos adicionales. Entre las líneas de trabajo consideradas están:

- Líneas base e indicadores de desempeño energético.
- Integración de nuevas fuentes y tipos de medición.
- Análisis complementarios de eficiencia energética.
- Detección exploratoria de anomalías con aprendizaje automático.
- Agrupación de perfiles operativos.
- Asistencia contextual basada en inteligencia artificial.

**Estas capacidades son proyecciones y no se presentan como funcionalidades ya implementadas de WattWise.**

---

## 11. Contexto académico

| Campo | Información |
|---|---|
| **Proyecto** | Energy Scope Planner |
| **Primera implementación** | WattWise |
| **Institución** | Universidad Autónoma de Occidente — Cali, Colombia |
| **Campo** | Ingeniería eléctrica y análisis de datos |
| **Ponencia** | Desarrollo de una plataforma auditable para la integración y análisis de información energética en instalaciones comerciales y de servicios |
| **Evento** | VII Encuentro Internacional de Semilleros de Investigación (EISI 2026) |

---

## 12. Licencia y uso

El archivo `pyproject.toml` identifica el proyecto mediante `LicenseRef-Proprietary`. **La publicación del código fuente no implica una autorización automática para redistribuirlo o comercializarlo.** Las condiciones de uso deben estar definidas expresamente por sus titulares.

---

## 13. Propósito del proyecto

Energy Scope Planner busca facilitar que el profesional pase de **archivos eléctricos dispersos** a **información organizada, gráficas interpretables y análisis documentados**.

WattWise demuestra esta propuesta mediante una primera implementación local, modular y orientada a la trazabilidad. Su contribución principal es **fortalecer la revisión técnica, no sustituir el juicio del ingeniero**.

**Energy Scope Planner — WattWise**  
*Tecnología para apoyar la revisión, documentación y planificación energética.*
