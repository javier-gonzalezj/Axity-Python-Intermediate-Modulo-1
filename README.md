# Proyecto: Librería

Programa de consola para administrar el catálogo de una librería: consultar, filtrar, agregar e importar libros, guardados en un archivo JSON.

Para los objetivos del nivel intermedio se toma el código base del último módulo del nivel básico.

Proyecto del curso **Axity Python Intermediate**.

## Características

- **Catálogo paginado** con los datos de la librería, el total de libros y el valor del inventario.
- **Filtros** por autor, género, disponibilidad, precio máximo y año mínimo, con opción de exportar el resultado a JSON.
- **Captura de libros por consola** con autocompletado por ISBN: el programa consulta [Open Library](https://openlibrary.org) y sugiere título, autor, géneros, año y editorial (Enter acepta la sugerencia).
- **Descarga de portadas** por streaming a `data/portadas/<isbn>.jpg`, sin dejar archivos a medias si la conexión se corta.
- **Importación desde CSV** que reporta las filas con errores sin detener la carga.
- **Validación de datos** con modelos de [pydantic](https://docs.pydantic.dev).
- **Guardado seguro**: el catálogo se escribe en un archivo temporal y solo reemplaza al original si todo salió bien.
- **Registro (logging)** detallado en `logs/libreria.log`.

## Requisitos

- Python 3.13 o superior
- [Poetry](https://python-poetry.org) 2.x
- Conexión a internet (opcional: solo para el autocompletado por ISBN y las portadas; sin ella, la captura es manual)

## Instalación

```bash
git clone https://github.com/javier-gonzalezj/Axity-Python-Fundamental-Modulo-7.git
cd Axity-Python-Fundamental-Modulo-7
poetry install
```

Para activar las revisiones automáticas antes de cada commit:

```bash
poetry run pre-commit install
```

## Uso

```bash
poetry run libreria
```

Al iniciar se muestra el catálogo y después el menú:

```
═════════════ MENU ═════════════
  1. Filtrar libros
  2. Cargar archivo CSV
  3. Agregar un libro
  4. Ver catalogo completo
  0. Salir
════════════════════════════════
```

### Agregar un libro (opción 3)

Al escribir el ISBN, el programa lo busca en Open Library y muestra los datos encontrados entre corchetes:

```
ISBN: 9780307474728
  🔎 Buscando el ISBN en Open Library...
  ✅ Encontrado: Cien años de soledad — Gabriel García Márquez
     Presiona Enter para aceptar el valor entre [corchetes] o escribe otro.
Título [Cien años de soledad]:
Nombre del autor [Gabriel García Márquez]:
Nacionalidad del autor: Colombiana
```

El precio, la cantidad disponible y la nacionalidad del autor siempre se capturan a mano. Si el libro no está en Open Library o no hay conexión, todos los campos se capturan manualmente.

> Open Library tiene menos libros en español, así que varios ISBN de editoriales mexicanas no aparecen. Los géneros que sugiere vienen en inglés.

### Importar desde CSV (opción 2)

El archivo debe estar en UTF-8 (en Excel: *Guardar como → CSV UTF-8*) y tener estas columnas:

| Columna | Obligatoria | Notas |
|---|---|---|
| `isbn` | Sí | No puede repetirse en el catálogo |
| `titulo` | Sí | |
| `autor` | Sí | Nombre del autor |
| `nacionalidad_autor` | No | Vacía por defecto |
| `genero` | Sí | Varios géneros separados por `;` |
| `año_publicacion` | Sí | Número entero |
| `precio` | Sí | Número, sin signo `$` |
| `cantidad_disponible` | Sí | Número entero |
| `editorial` | Sí | |
| `en_stock` | No | `sí`/`no`; si falta, se calcula con la cantidad |

Hay un ejemplo en [`data/ejemplos/libros_nuevos.csv`](data/ejemplos/libros_nuevos.csv).

## Estructura del proyecto

```
libreria/
├── data/
│   ├── libreria.json          # catálogo principal
│   ├── ejemplos/              # CSV de ejemplo para importar
│   ├── exportaciones/         # resultados de filtros exportados (ignorado por git)
│   └── portadas/              # portadas descargadas (ignorado por git)
├── logs/                      # archivo de log (ignorado por git)
├── src/libreria/
│   ├── main.py                # punto de entrada y menú
│   ├── modelos.py             # modelos Libro y Autor (pydantic)
│   ├── almacenamiento.py      # lectura y escritura del catálogo JSON
│   ├── catalogo.py            # reglas del catálogo: agregar y filtrar
│   ├── captura.py             # entrada de datos por consola
│   ├── vista.py               # salida por consola
│   ├── intercambio.py         # importar CSV y exportar JSON
│   ├── buscador.py            # consultas a Open Library y descarga de portadas
│   ├── excepciones.py         # jerarquía de errores del proyecto
│   ├── registro.py            # configuración del logging
│   └── utilidades.py          # reintentos, escritura atómica, cronómetro
├── tests/
│   └── test_buscador.py
└── pyproject.toml
```

## Dependencias principales

- [pydantic](https://docs.pydantic.dev): validación de los datos de cada libro.
- [httpx](https://www.python-httpx.org): consultas HTTP a Open Library y descarga de portadas.

## Créditos

- Datos de libros y portadas: [Open Library](https://openlibrary.org), un proyecto de Internet Archive.
- Autor: [javier-gonzalezj](https://github.com/javier-gonzalezj)
