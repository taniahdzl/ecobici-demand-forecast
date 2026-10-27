# Estado del proyecto — predicción de demanda Ecobici CDMX

Corte: 27 de octubre de 2026. Último commit del repo antes de este documento: 28 de septiembre de 2026.

## Resumen

- **Hecho:** ingesta de datos, catálogo de estaciones, capa geográfica, EDA completo (nulos, outliers, hora, día de la semana, estaciones top, flujo neto, geografía por alcaldía y origen-destino), figuras para las slides y la primera presentación.
- **Pendiente, y es lo que más pesa en la segunda presentación:** el modelo. No hay todavía código de entrenamiento, ni baseline, ni partición entrenamiento/prueba, ni búsqueda de hiperparámetros, ni resultados. El Modelo vale 40 de 100 puntos.
- **Dos correcciones de ids, ya hechas en el código pero sin recalcular:** (1) las estaciones pareadas (ej. `271-272`) son estaciones reales y `ingest.py` las dejaba sin estación; (2) `make_figures.py`, `make_network.py` y el notebook 00 nombraban estaciones con el `station_id` de GBFS en vez de `ce`. Hay que volver a correr `ingest.py` y los scripts de figuras. Ver "Corrección: ids de estación".

## Qué hay en el repo

| Componente | Archivo | Estado |
| --- | --- | --- |
| Ingesta de viajes | `src/ingest.py` | Listo. Genera `data/processed/trips_clean.parquet` (no se versiona, está en `.gitignore`) |
| Catálogo de estaciones | `src/stations.py` | Listo. Genera `stations.csv` y `station_status_snapshot.csv` |
| Funciones de EDA | `src/eda_utils.py` | Listo. Incluye `demanda_por_estacion_hora`, la tabla de entrada del modelo |
| EDA general | `notebooks/00_template_eda.ipynb` | Listo |
| EDA geográfico | `notebooks/01_eda_JL_geo.ipynb`, `src/geo.py`, `src/geo_utils.py` | Listo |
| Figuras de las slides | `src/make_figures.py` (genera `figures/01` a `06`) y `src/make_network.py` (genera `07`) | Listo |
| Mapa real vs predicción | `src/map_real_vs_pred.py` | Provisional: la predicción es un promedio histórico por hora, no un modelo |
| **Modelo** | — | **No existe** |

## Decisiones de diseño tomadas

| Decisión | Justificación |
| --- | --- |
| Problema de regresión supervisada; objetivo: salidas por estación-hora | La variable objetivo es continua (número de bicis), no una categoría |
| Periodo de 1 de marzo a 31 de agosto de 2026: 9,325,132 viajes, 184 días, 677 estaciones | Seis meses completos del portal oficial de datos abiertos |
| Filtro de duración de 1 a 45 minutos: quedan 9,160,389 viajes (98.2%) | 45 minutos es el límite oficial del servicio (criterio de dominio, no IQR). Se descartan 163,614 viajes de más de 45 min y 1,129 de menos de 1 min |
| No imputar los ids de estación faltantes; clasificarlos en `estacion_*_tipo` (`valido`, `par_estaciones`, `temporal`, `otro_no_numerico`) | El faltante no es aleatorio (MNAR): depende del tipo de estación |
| Cruzar viajes con el catálogo por `ce`, no por `station_id` de GBFS | Son ids distintos; cruzar mal da ~31% de viajes a más de 30 km/h, físicamente imposible |
| Mapas por código postal, con la alcaldía derivada del prefijo del CP | Los polígonos son de CP, no de colonias; la alcaldía es una aproximación validada en las 6 alcaldías con estaciones |
| Modelo candidato: XGBoost global con la estación como variable | Un solo modelo escala a 677 estaciones y captura interacciones no lineales; SARIMA o Prophet necesitarían un modelo por estación |
| Partición por fechas (primeros ~80% de los días para entrenar, últimos ~20% para probar) | Predecir el futuro, no el pasado; una partición aleatoria filtraría información |

## Corrección: ids de estación

Lo que decíamos hasta ahora (comentarios de `ingest.py`, diapositiva de nulos, reporte): "los pares como `271-272` son dos estaciones, y ambos números existen en el catálogo". **Eso es incorrecto.**

- En `stations_geo.csv`, cada uno de los 12 pares es **una sola estación** cuyo id `ce` es el par completo. Ejemplo: `CE-271-272 Jesús García - Carlos J. Meneses`. Ningún número del par existe por separado.
- La verificación de la celda 5 de `00_template_eda.ipynb` comparó los números contra el `station_id` de GBFS en lugar de `ce`. Por eso salió "274 no existe" en `273-274`: fue una falsa alarma.
- Los 4 ids `Temporal 1` a `Temporal 4` sí son los únicos que no están en el catálogo.

**Efecto.** `ingest.py` convierte los ids pareados a vacío, así que esos viajes pierden estación:

| | Retiros | Arribos |
| --- | --- | --- |
| Total sin estación | 331,089 (3.55%) | 380,029 (4.08%) |
| De pares reales (recuperables) | 330,367 | 379,208 |
| De temporales (no están en el catálogo) | 722 | 821 |

Los pares incluyen estaciones de mucho tráfico: `271-272` tiene 65,140 retiros y 105,805 arribos, y sus retiros superan las 49,839 salidas de la estación que encabeza la tabla "más se vacían" del notebook 00. Hoy esas estaciones están ausentes de las figuras de estaciones top y flujo neto, del origen-destino y de lo que alimentaría al modelo. **No se ha recalculado nada con ellas.**

**Segundo error, de llave.** Los ids de los viajes son el `ce`, pero `make_figures.py`, `make_network.py` y las celdas 20, 24, 26 y 27 del notebook 00 los buscaban en `stations.csv` por `station_id` de GBFS. Son ids distintos: el 208 salía como "CE-457 Av. Prado Norte-Explanada" cuando es "CE-208 Hesiodo-Lamartine", y el 711 no tenía nombre. Los rankings por id eran correctos, pero los **nombres** de las figuras 02, 05 y 06, y las coordenadas del grafo (07), estaban mal.

**Cambios hechos (en rama local, sin push):**

1. `src/ingest.py`: conserva el id pareado como texto (`"271-272"`); solo los `Temporal N` y otros no numéricos quedan vacíos. Comentario corregido.
2. `src/eda_utils.py`: nueva `load_stations_ce()` (catálogo con `station_id = ce`, incluye pares). La usan `make_figures.py` y `make_network.py`.
3. `src/map_real_vs_pred.py`: une predicción (por `ce`) y estado en vivo (por `station_id`) a través de `stations_geo.csv`.
4. Notebook 00, celda 5: compara contra `ce` y define `stations` con esa llave. Las celdas 20, 24, 26 y 27 ya la usan sin cambios, pero **hay que volver a ejecutar el notebook** (la celda 5 se guardó sin salida).

**Pendiente del lado de ustedes:** como los CSV y el parquet no están en el repo, nada se recalculó con datos reales (solo se probó con datos sintéticos). Hay que correr `ingest.py`, `make_figures.py`, `make_network.py` y el notebook 00, revisar qué cifras cambian (top de estaciones, flujo neto, % de viajes sin estación) y actualizar las slides afectadas (top, flujo, curva, red y la de nulos).

## Checklist para la segunda presentación

Rúbrica del profesor (total 100 puntos):

| Criterio | Valor | Qué piden |
| --- | --- | --- |
| Problema | 10 | Recordar el problema y los objetivos específicos; decir si es de regresión o clasificación |
| Datos | 20 | Origen, tamaño, tipo, formato y hallazgos más importantes del EDA |
| Modelo | 40 | Tratamiento de datos, arquitectura del modelo, hiperparámetros y resultados |
| Discusión | 30 | Justificación de las decisiones de diseño, éxito y limitaciones, conclusiones, sugerencias de mejora |

### Problema (10)

- [x] Problema y objetivos específicos (slide "Problema")
- [x] Declarado como regresión supervisada, con variable objetivo y variables de entrada

### Datos (20)

- [x] Origen: portal de datos abiertos de Ecobici y feed GBFS
- [x] Tamaño, periodo y formato (CSV mensual, un registro por viaje)
- [x] Tipos de atributos (slide "Dataset")
- [x] Hallazgos del EDA (hora, día de la semana, estaciones, flujo neto, geografía)
- [x] Corregir lo de las estaciones pareadas y la llave `ce` en el código (hecho; falta volver a correr y actualizar las slides)
- [ ] Recalcular las cifras que cambien y actualizar slides (top, flujo, curva, red, nulos)
- [ ] Verificar el número de atributos que dice la slide de dataset ("9.3M × 13"): el notebook muestra 19 columnas en `trips_clean`
- [ ] Resumir el EDA en pocas slides para dejar tiempo al modelo

### Modelo (40) — lo más pendiente

- [ ] **Tratamiento de datos:** tabla de entrada por estación, fecha y hora a partir de `demanda_por_estacion_hora`. Esa función solo cuenta las horas con viajes, así que hay que completar con cero las horas sin viajes
- [ ] Variables de entrada: estación, hora, día de la semana, fin de semana; opcionales: CP, alcaldía, latitud, longitud, capacidad
- [ ] Decidir cómo entra la estación al modelo (categórica) y cómo se tratan pares y temporales
- [ ] Partición entrenamiento/prueba por fechas
- [ ] **Baseline:** promedio histórico por estación, hora y tipo de día (ya hay una versión provisional en `map_real_vs_pred.py`)
- [ ] **Arquitectura:** XGBoost global; justificar frente a SARIMA y Prophet
- [ ] **Hiperparámetros:** definir cuáles (por ejemplo `n_estimators`, `learning_rate`, `max_depth`, `subsample`) y el método de búsqueda (grid o random) con validación respetando el orden del tiempo
- [ ] **Resultados:** RMSE y MAE en prueba contra el baseline; error por hora, por estación y por alcaldía; importancia de variables; gráfica de real contra predicho
- [ ] Reemplazar la predicción provisional de `map_real_vs_pred.py` por la del modelo
- [ ] Guardar el código en `src/` o en un notebook nuevo (por ejemplo `notebooks/02_modelo.ipynb`), las figuras en `figures/`, y agregar `xgboost` y `scikit-learn` a `requirements.txt`

### Discusión (30)

- [x] Decisiones de diseño justificadas (tabla de arriba)
- [x] Borrador de conclusiones y limitaciones en el reporte de avance
- [ ] Reescribir éxito, limitaciones y conclusiones con los resultados reales del modelo
- [ ] Sugerencias de mejora: variables externas (clima, festivos, cercanía a Metro y Metrobús), variables de rezago (salidas de la hora anterior), más meses de datos, tratamiento de pares, validación contra GBFS en vivo
- [ ] Reconocer las limitaciones conocidas: seis meses de datos, EDA descriptivo (no causal), y lo de los pares si no se alcanza a corregir

### Logística

- [ ] Actualizar el guion de las 3 personas con el contenido nuevo (el actual cubre 15 slides del EDA)
- [ ] Ensayar con cronómetro; la rúbrica pide que participen los tres
- [ ] Poner las presentaciones y el temario de la clase en `docs/clase/` (carpeta ignorada en `.gitignore`: se quedan solo en local, no se suben)

## Orden pendiente del repositorio

- `figures/` tiene dos juegos de figuras: las numeradas (`01_` a `07_`, generadas por los scripts) y otras sin número (`flujo.png`, `top_estaciones.png`, `viajes_por_hora.png`, `outliers_duracion.png`, `viajes_totales.png`, `curva_acumulacion.png`, `entre_semana_vs_finde.png`, `duracion_antes_despues.png`, `top_10_estaciones_por_salidas.png`). Probablemente son versiones anteriores; conviene dejar solo las numeradas.
- ~~README sin los scripts nuevos~~ y ~~nombre `ecobici-demanda/`~~: corregidos.
- `trips_clean.parquet` no se versiona: cualquiera que quiera entrenar el modelo tiene que bajar los CSV a `data/raw/` y correr `python src/ingest.py`.

## Cómo reproducir

```bash
pip install -r requirements.txt
# bajar los CSV mensuales (marzo a agosto de 2026) a data/raw/
python src/ingest.py          # data/processed/trips_clean.parquet
python src/stations.py        # stations.csv y station_status_snapshot.csv
python src/make_figures.py    # figures/01 a 06
python src/make_network.py    # figures/07
```
