# Predicción de demanda Ecobici CDMX

Proyecto de minería y análisis de datos para predecir la demanda de bicis por
estación (regresión) y cubrirla con oferta (restock).

## Estructura del repo

```
ecobici-demanda/
├── data/
│   ├── raw/            <- CSVs mensuales tal cual se bajan del portal (NO editar a mano)
│   └── processed/       <- outputs de los scripts (parquet/csv limpios)
├── notebooks/           <- EDA y exploración (un notebook por persona/tema)
├── src/
│   ├── ingest.py        <- une los CSVs crudos en un solo dataframe
│   ├── stations.py      <- descarga GBFS y cruza station_id <-> lat/lon
│   └── eda_utils.py     <- funciones reusables de limpieza/gráficas
├── figures/             <- gráficas exportadas para las slides
├── requirements.txt
└── README.md
```

## Cómo arrancar (cada integrante)

```bash
git clone <url-del-repo>
cd ecobici-demanda
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Flujo de trabajo

1. Bajar los CSVs mensuales del portal oficial:
   https://ecobici.cdmx.gob.mx/en/open-data/
   y ponerlos en `data/raw/` (respetar el nombre `YYYY-MM.csv`, o renombrar).

2. Correr la ingesta:
   ```bash
   python src/ingest.py
   ```
   Esto genera `data/processed/trips_clean.parquet` con todos los meses unidos,
   tipos de dato corregidos y columnas derivadas (duración del viaje, día de
   la semana, hora, etc).

3. Bajar catálogo de estaciones con coordenadas:
   ```bash
   python src/stations.py
   ```
   Esto genera `data/processed/stations.csv` (station_id, nombre, lat, lon,
   capacidad) y `data/processed/station_status_snapshot.csv` (foto del
   estado en tiempo real al momento de correrlo).

4. Trabajar el EDA en `notebooks/`, cada quien puede copiar
   `notebooks/00_template_eda.ipynb` como punto de partida.

## Reglas del repo (para no pisarse el trabajo)

- Los CSVs crudos (`data/raw/*.csv`) NO se suben a GitHub (pesan demasiado,
  ver `.gitignore`) — cada quien los baja localmente.
- Los notebooks sí se versionan, pero cada persona trabaja en su propia
  copia (`notebooks/eda_<nombre>.ipynb`) para evitar conflictos de merge.
- Los outputs reusables (`data/processed/*.parquet`) tampoco se suben si
  pesan mucho; si son chicos (agregados, no el histórico crudo) sí conviene
  subirlos para que todos partan del mismo punto.
