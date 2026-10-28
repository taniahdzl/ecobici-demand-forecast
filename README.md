# Predicción de demanda Ecobici CDMX

Proyecto de minería de datos (equipo de 3) para **predecir la demanda de bicis
por estación** y apoyar el restock. Es un problema de **regresión
supervisada**: la variable objetivo son las *salidas por estación y hora*.

## Estado del proyecto

| Etapa | Estado |
| --- | --- |
| Ingesta y limpieza de viajes | Listo (`src/ingest.py`) |
| Catálogo de estaciones y capa geográfica | Listo (`src/stations.py`, `src/geo.py`) |
| EDA (nulos, outliers, hora, semana/finde, top, flujo neto, geografía, red) | Listo (notebooks `00` y `01`, `figures/`) |
| Modelo: 3 referencias simples, regresión lineal, MLP y XGBoost, con hiperparámetros y métricas | Código listo (`src/modelo.py`, `notebooks/02_modelo.ipynb`); falta la corrida final con `RAPIDO = False` |
| Conclusiones y discusión con resultados reales | Pendiente (depende del modelo) |

## Datos

- **Origen:** portal de datos abiertos de Ecobici
  (https://ecobici.cdmx.gob.mx/en/open-data/) y feed GBFS para el catálogo de estaciones.
- **Tamaño y formato:** 6 CSV mensuales (marzo a agosto de 2026), un registro por
  viaje: 9,325,132 viajes, 677 estaciones, 184 días.
- **Filtro de duración:** se conservan los viajes de 1 a 45 minutos (límite
  oficial del servicio): 9,160,389 viajes (98.2 %). Se descartan 163,614 de más
  de 45 min y 1,129 de menos de 1 min.
- **Fechas fuera de periodo:** 3 viajes tienen fecha de 2022 a 2024 con
  duraciones de cientos de miles de minutos; el filtro de duración los elimina.
- **Estaciones sin id:** solo 722 retiros (0.008 %) y 821 arribos (0.009 %),
  todos `Temporal 1` a `Temporal 4`, que no están en el catálogo.

## Decisiones de diseño

| Decisión | Justificación |
| --- | --- |
| Regresión sobre salidas por estación-hora | La variable objetivo es continua (número de bicis) |
| Modelo candidato: XGBoost global con la estación como variable | Un solo modelo escala a 677 estaciones y captura interacciones no lineales; SARIMA o Prophet necesitarían un modelo por estación |
| Partición por fechas (~80 % de los días para entrenar, ~20 % para probar) | Hay que predecir el futuro; una partición aleatoria filtraría información |
| Baseline: promedio histórico por estación, hora y tipo de día | Referencia mínima que el modelo debe superar; métricas RMSE y MAE |
| No imputar ids de estación faltantes; se clasifican en `estacion_*_tipo` | El faltante no es aleatorio (depende del tipo de estación) |
| Cruzar viajes con el catálogo por `ce`, no por `station_id` de GBFS | Son ids distintos; cruzar mal pone viajes en estaciones equivocadas |
| Estaciones pareadas (`271-272`) se conservan como una sola estación | Son una estación real del catálogo cuyo `ce` es el par completo |
| Mapas por código postal, con la alcaldía derivada del prefijo | Los polígonos son de CP, no de colonias |

## Estructura del repo

```
ecobici-demand-forecast/
├── data/
│   ├── raw/            <- CSVs mensuales tal cual se bajan del portal (NO editar a mano)
│   └── processed/       <- outputs de los scripts (parquet/csv limpios)
│       ├── cdmx_cp_ecobici.geojson   <- polígonos de código postal recortados al área de Ecobici
│       ├── stations_geo.csv          <- station_id, ce, nombre, lat, lon, capacidad, cp, alcaldia, colonia
│       └── cp_colonias.csv           <- cp, nombre, colonias, n_colonias, alcaldia
├── notebooks/
│   ├── 00_template_eda.ipynb   <- EDA general; punto de partida para copiar
│   ├── 01_eda_JL_geo.ipynb     <- EDA geográfico (mapas por CP y alcaldía)
│   └── 02_modelo.ipynb         <- compara 6 modelos: métricas, sobreajuste, error por hora/alcaldía/estación
├── src/
│   ├── ingest.py        <- une los CSVs crudos en trips_clean.parquet
│   ├── stations.py      <- descarga GBFS y cruza station_id <-> lat/lon
│   ├── eda_utils.py     <- funciones reusables de limpieza/gráficas (load_stations_ce: catálogo con la llave de los viajes)
│   ├── modelo.py        <- tabla estación-hora con rezagos, partición por fechas, baselines, regresión lineal, MLP y XGBoost
│   ├── make_figures.py  <- genera figures/01 a 06 (duración, top estaciones, hora, semana/finde, flujo neto, curva)
│   ├── make_network.py  <- genera figures/07 (grafo de flujos entre estaciones)
│   ├── map_real_vs_pred.py <- mapa de bicis reales vs demanda esperada (hoy con predicción provisional)
│   ├── geo.py           <- prepara la capa geográfica (se corre rara vez)
│   └── geo_utils.py     <- funciones para unir datos con su geografía y dibujar mapas
├── figures/             <- gráficas exportadas para las slides
├── docs/
│   └── class/           <- slides del profesor y temario (solo local, está en .gitignore)
├── requirements.txt
└── README.md
```

## Cómo arrancar (cada integrante)

```bash
git clone <url-del-repo>
cd ecobici-demand-forecast
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Flujo de trabajo

Desde la raíz del repo, con el venv activo:

1. Bajar los CSVs mensuales del portal oficial y ponerlos en `data/raw/`
   (respetar el nombre `YYYY-MM.csv`, o renombrar).

2. Ingesta: `python src/ingest.py` genera `data/processed/trips_clean.parquet`
   con todos los meses unidos, tipos de dato corregidos y columnas derivadas
   (ver el diccionario de datos abajo).

3. Catálogo de estaciones: `python src/stations.py` genera
   `data/processed/stations.csv` (station_id de GBFS, nombre, lat, lon,
   capacidad) y `station_status_snapshot.csv` (foto del estado en tiempo real).

4. Figuras de las slides:
   ```bash
   python src/make_figures.py    # figures/01 a 06
   python src/make_network.py    # figures/07
   ```

5. EDA: abrir `notebooks/00_template_eda.ipynb` y ejecutarlo completo (usa el
   kernel del venv). Para geografía, `notebooks/01_eda_JL_geo.ipynb`.
   Cada persona trabaja en su propia copia (`notebooks/eda_<nombre>.ipynb`).

6. Modelo: ejecutar `notebooks/02_modelo.ipynb` (Restart & Run All).
   - Con `RAPIDO = True` (por defecto) hace una corrida corta para validar; los
     resultados se guardan con sufijo `_rapido`.
   - Con `RAPIDO = False` hace la corrida final: genera `figures/08` a `11` y
     `data/processed/resultados_modelo.csv`, `sobreajuste_modelo.csv` y
     `busqueda_hiperparametros.csv`.

7. Mapa real vs predicción (provisional): `python src/map_real_vs_pred.py`
   guarda `figures/mapa_real_vs_prediccion.html`.

## Diccionario de datos (`trips_clean.parquet`)

| Columna | Descripción |
| --- | --- |
| `genero`, `edad` | Género y edad declarados del usuario |
| `bici_id` | Identificador de la bici |
| `estacion_origen`, `estacion_destino` | Id `ce` de la estación, como texto. Los pares se conservan (`"271-272"`); `Temporal N` queda vacío |
| `estacion_origen_tipo`, `estacion_destino_tipo` | `valido`, `par_estaciones`, `temporal` u `otro_no_numerico` |
| `fecha_origen`, `hora_origen`, `fecha_destino`, `hora_destino` | Fecha y hora originales del CSV |
| `origen_dt`, `destino_dt` | Fecha y hora combinadas (datetime) |
| `duracion_min` | Duración del viaje en minutos |
| `hora_del_dia`, `dia_semana`, `fecha`, `es_fin_de_semana` | Derivadas de `origen_dt` |
| `archivo_origen` | CSV mensual de donde viene el viaje |

Variables del modelo (`src/modelo.py`, una fila por estación-fecha-hora): `salidas` (objetivo),
`estacion`, `cp`, `alcaldia`, `hora`, `dia_semana`, `es_fin_de_semana`, `lat`, `lon`, `capacidad`,
y tres de contexto reciente con 7 días o más de rezago: `lag_7d`, `media_4sem` y `nivel_semana`.

## Reglas del repo (para no pisarse el trabajo)

- Las slides del profesor y el temario van en `docs/class/` (ignorada en `.gitignore`): NO se suben.
- Los CSVs crudos (`data/raw/*.csv`) NO se suben a GitHub (pesan demasiado,
  ver `.gitignore`); cada quien los baja localmente.
- `trips_clean.parquet` tampoco se sube (se regenera con `ingest.py`); los
  archivos chicos de `data/processed/` (catálogo, capa geográfica) sí.
- Los notebooks sí se versionan, pero cada persona trabaja en su propia copia
  para evitar conflictos de merge.

## Capa geográfica (mapas del EDA)

Para hacer mapas sobre la geografía real de la CDMX (estaciones sobre
polígonos, coropletas por zona) hay una capa geográfica ya preparada y
versionada. **No hace falta internet ni instalar nada extra**.

### Archivos nuevos

```
src/
├── geo.py            <- prepara la capa geográfica (se corre rara vez)
└── geo_utils.py      <- funciones para unir datos con su geografía y dibujar mapas
data/processed/
├── cdmx_cp_ecobici.geojson   <- polígonos de código postal recortados al área de Ecobici
├── stations_geo.csv          <- station_id, ce, nombre, lat, lon, capacidad, cp, alcaldia, colonia
└── cp_colonias.csv           <- cp, nombre, colonias, n_colonias, alcaldia (nombre de cada CP)
```

### Los viajes y GBFS usan ids de estación DISTINTOS

Los ids de estación de los viajes (`estacion_origen`, `estacion_destino`)
**no son** el `station_id` de GBFS: son el número **CE** que aparece en el
nombre de la estación (`"CE-710 Molino del Rey..."` -> id de viajes `"710"`,
GBFS `station_id = "1"`). Cruzar viajes por `station_id` pone cada viaje en
una estación equivocada (sale ~31 % de viajes a >30 km/h, físicamente
imposible). `stations_geo.csv` trae ambas columnas:

| columna      | la usan                                     |
|--------------|---------------------------------------------|
| `ce`         | datos de **viajes** (`trips_clean.parquet`) |
| `station_id` | datos **GBFS** (`stations.py`, snapshot)    |

### ¿Cuándo correr `geo.py`?

Casi nunca: los dos archivos de `data/processed/` ya vienen en el repo. Solo
hay que regenerarlos si cambia el catálogo de estaciones:

```bash
python src/stations.py   # actualiza stations.csv
python src/geo.py        # vuelve a recortar y asignar CP/alcaldía
```

### Uso en notebooks

```python
import sys; sys.path.append("../src")
import matplotlib.pyplot as plt
from eda_utils import load_clean_trips, demanda_por_estacion_hora
from geo_utils import load_stations_geo, unir_geo, plot_mapa_base
```

**1. Unir cualquier tabla con su geografía** (`unir_geo`):

```python
demanda = demanda_por_estacion_hora(load_clean_trips())
demanda = unir_geo(demanda, col_id="estacion_origen")
# -> agrega columnas lat, lon, cp, alcaldia
```

Para viajes (dos estaciones por fila) se llama dos veces con prefijo:

```python
t = unir_geo(trips, "estacion_origen",  prefijo="origen_")
t = unir_geo(t,     "estacion_destino", prefijo="destino_")
# -> origen_lat, origen_cp, origen_alcaldia, destino_lat, ...
```

Por defecto `unir_geo` cruza por `ce` (datos de viajes). Para datos del feed
GBFS, como el snapshot de estado, hay que pedir `clave="station_id"`:

```python
from eda_utils import load_status_snapshot
snap = unir_geo(load_status_snapshot(), "station_id", clave="station_id")
```

Consejo: con el histórico completo conviene **agregar primero y unir
después** (unir millones de viajes pesa en memoria).

**2. Mapa base + tus propios puntos** (`plot_mapa_base`):

```python
est = load_stations_geo()
fig, ax = plt.subplots(figsize=(10, 10))
plot_mapa_base(ax)
ax.scatter(est["lon"], est["lat"], s=8)
```

**3. Coropleta por código postal** (`plot_mapa_base` con `valores`):

```python
salidas_por_cp = demanda.groupby("cp")["salidas"].sum()
fig, ax = plt.subplots(figsize=(10, 10))
ax, mappable = plot_mapa_base(ax, valores=salidas_por_cp)
fig.colorbar(mappable, ax=ax, label="Salidas totales")
```

**4. Nombres en vez de códigos postales** (`etiqueta_cp`):

```python
from geo_utils import etiqueta_cp
etiqueta_cp("06700")                  # 'Roma Norte (06700)'
etiqueta_cp("06700", con_cp=False)    # 'Roma Norte'
salidas_por_cp.index = etiqueta_cp(salidas_por_cp.index)   # tabla con nombres
```

Conviene dejar el CP entre paréntesis en tablas: hay colonias que se llaman
igual que una alcaldía (colonia Cuauhtémoc, colonia Juárez).

### Cosas a tener en cuenta

- **Los polígonos son códigos postales, no colonias.** En zonas como Roma o
  Condesa se parecen mucho, pero en títulos y leyendas digan "código postal".
- **La alcaldía se deriva del prefijo del CP** (06 = Cuauhtémoc, 03 = Benito
  Juárez, 11 = Miguel Hidalgo, ...). Es una aproximación de SEPOMEX, validada
  para las 6 alcaldías donde hay estaciones.
- **Estaciones pareadas** (~4 % de los extremos de viaje en mar–ago 2026).
  Ids como `"158-159"` son UNA estación real del catálogo cuyo `ce` es el par
  completo (ej. "CE-158-159 Huatabampo..."); ningún número del par existe por
  separado. `ingest.py` los conserva como texto. Solo los `Temporal 1` a
  `Temporal 4` (y otros no numéricos) quedan sin estación; `unir_geo` no borra esas filas: las deja
  con valores vacíos y muestra una advertencia.
- **Siempre cruzar viajes con `ce`.** Las figuras y notebooks que nombraban
  estaciones con el `station_id` de GBFS mostraban nombres equivocados
  (ej. el id 208 salía como "CE-457 ..." en vez de "CE-208 Hesiodo-Lamartine").
  Usar `eda_utils.load_stations_ce()` o `geo_utils.unir_geo`.
- **Fuentes:**
  - Polígonos: [open-mexico/mexico-geojson](https://github.com/open-mexico/mexico-geojson)
    (licencia MIT, datos de SEPOMEX), archivo `09-Cdmx.geojson` fijado al
    commit `ff9a744`.
  - Nombres de colonia (`cp_colonias.csv`): Catálogo Nacional de Códigos
    Postales de Correos de México
    (`https://www.correosdemexico.gob.mx/datosabiertos/cp/cpdescarga.txt`).
    Cuando un CP tiene varias colonias, `nombre` las resume (ej.
    "Lomas de Chapultepec (8 colonias)") y `colonias` las lista todas.
</content>
