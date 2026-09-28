# Sugerencia de README (JL)

> **Nota:** esto es lo que me gustaría que se agregue **al final del
> `README.md`**, una vez que estén en el repo `src/geo.py`, `src/geo_utils.py`
> y los archivos geográficos en `data/processed/`. No modifiqué el README
> original; quien lo mantiene puede copiar lo de abajo tal cual o ajustarlo.

---

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
- **Algunos viajes no tienen coordenadas** (~4 % de los extremos de viaje
  en mar–ago 2026). Todos los ids de los datos crudos existen en el
  catálogo, incluidas las estaciones pareadas como `"158-159"` (son
  estaciones reales, ej. "CE-158-159 Huatabampo..."). El problema es que
  `ingest.py` convierte los ids pareados en vacío, así que en
  `trips_clean.parquet` esos viajes ya no tienen estación. `unir_geo` no
  borra esas filas: las deja con valores vacíos y muestra una advertencia
  que separa las filas con id vacío de los ids sin estación.
- **Fuentes:**
  - Polígonos: [open-mexico/mexico-geojson](https://github.com/open-mexico/mexico-geojson)
    (licencia MIT, datos de SEPOMEX), archivo `09-Cdmx.geojson` fijado al
    commit `ff9a744`.
  - Nombres de colonia (`cp_colonias.csv`): Catálogo Nacional de Códigos
    Postales de Correos de México
    (`https://www.correosdemexico.gob.mx/datosabiertos/cp/cpdescarga.txt`).
    Cuando un CP tiene varias colonias, `nombre` las resume (ej.
    "Lomas de Chapultepec (8 colonias)") y `colonias` las lista todas.
