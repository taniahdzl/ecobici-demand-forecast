# Checklist: mismo mes, otro año (notebook 08)

Qué se va a correr: `notebooks/08_mismo_mes_otro_anio.ipynb`. Para cada mes de prueba compara entrenar con **el mes anterior**, con **el mismo mes del año anterior** y con **los dos juntos**. Responde a la sugerencia de los profesores (enero de 2025 contra enero de 2026, y así).

## 1. ¿Hace falta Colab?

Se probó el notebook completo en la máquina local con el único par que ya tiene todos sus archivos (septiembre de 2026 contra septiembre de 2025), en CPU de 4 núcleos y 3.9 GB de RAM:

| Paso | Tiempo medido |
|---|---|
| Leer y limpiar un CSV mensual (la primera vez; después sale de la caché) | 13 s |
| Armar las tablas de un mes de prueba | 10 s con caché |
| XGBoost, mes anterior | 18 s |
| XGBoost, mismo mes del año anterior | 7 s |
| XGBoost, ambos | 44 s |
| Regresión lineal (los dos orígenes) | 3 s |
| **Un mes de prueba completo** | **82 s** |
| RAM máxima | 1.5 GB |

Extrapolando a los 13 meses de prueba: unos **20 a 25 minutos** en total, sin GPU. Es una estimación hecha con un solo mes, no una medición de los 13.

Con esos números, el experimento tal como está escrito **cabe en una laptop**. Colab ayudaría si se agrega algo más pesado, por ejemplo una búsqueda de hiperparámetros por mes o el MLP (`USAR_MLP = True`). Propuesta: correr primero local, anotar los tiempos reales y decidir con eso.

## 2. Archivos a descargar

Portal: <https://ecobici.cdmx.gob.mx/en/open-data/>. Cada archivo pesa unos 100 MB. Los nombres en el portal no son uniformes y la carpeta del enlace depende de cuándo se subió el archivo, así que hay que bajarlos desde la página y **renombrarlos a `AAAA-MM.csv`**.

Ponerlos en **`data/raw/anteriores/`** (no en `data/raw/`): así `src/ingest.py` no los mezcla en `trips_clean.parquet`. Esa carpeta y la caché ya están en `.gitignore`.

Ya se tienen (en `data/raw/`): septiembre de 2025 a septiembre de 2026.

### Para los 9 meses de 2026 contra 2025 (prioridad 1)

| Bajar | Nombre en el portal | Guardar como | Para qué |
|---|---|---|---|
| Ene 2025 | `2025-01.csv` | `data/raw/anteriores/2025-01.csv` | Mismo mes de ene 2026 |
| Feb 2025 | **ver nota abajo** | `data/raw/anteriores/2025-02.csv` | Mismo mes de feb 2026 |
| Mar 2025 | `2025-03.csv` | `data/raw/anteriores/2025-03.csv` | Mismo mes de mar 2026 |
| Abr 2025 | `2025-04.csv` | `data/raw/anteriores/2025-04.csv` | Mismo mes de abr 2026 |
| May 2025 | `2025-05.csv` | `data/raw/anteriores/2025-05.csv` | Mismo mes de may 2026 |
| Jun 2025 | `2025-06.csv` | `data/raw/anteriores/2025-06.csv` | Mismo mes de jun 2026 |
| Jul 2025 | `2025-07.csv` | `data/raw/anteriores/2025-07.csv` | Mismo mes de jul 2026; historia para sep 2025 |
| Ago 2025 | `2025-08.csv` | `data/raw/anteriores/2025-08.csv` | Mismo mes de ago 2026; mes anterior de sep 2025 |

Sep 2025 ya está, y sirve para el mismo mes de sep 2026.

**Nota sobre febrero de 2025:** al leer el portal, el enlace de febrero de 2025 parecía apuntar al mismo archivo que enero. No está confirmado. Si de verdad no existe, el par feb 2026 contra feb 2025 se omite solo, y hay que decirlo en el reporte. Al bajar enero y febrero, abrir los dos y comprobar que las fechas sean distintas.

### Para los 4 meses de 2025 contra 2024 (prioridad 2)

Estos cubren los meses que todavía no existen en 2026 (octubre a diciembre) y septiembre.

| Bajar | Nombre en el portal | Guardar como | Para qué |
|---|---|---|---|
| Ago 2024 | `2024-08.csv` | `data/raw/anteriores/2024-08.csv` | Historia para sep 2024 |
| Sep 2024 | `2024-09.csv` | `data/raw/anteriores/2024-09.csv` | Mismo mes de sep 2025 |
| Oct 2024 | `2024-10.csv` | `data/raw/anteriores/2024-10.csv` | Mismo mes de oct 2025 |
| Nov 2024 | `2024-11.csv` | `data/raw/anteriores/2024-11.csv` | Mismo mes de nov 2025 |
| Dic 2024 | `2024-12.csv` | `data/raw/anteriores/2024-12.csv` | Mismo mes de dic 2025; historia para ene 2025 |

Total: **13 archivos** (8 + 5), unos 1.3 GB.

### Comprobar cada archivo al bajarlo

- [ ] El nombre quedó como `AAAA-MM.csv` y está en `data/raw/anteriores/`.
- [ ] La primera línea trae las columnas `Genero_Usuario,Edad_Usuario,Bici,Ciclo_Estacion_Retiro,Fecha_Retiro,Hora_Retiro,Ciclo_EstacionArribo,Fecha_Arribo,Hora_Arribo` (puede variar el guion bajo; `ingest.py` lo normaliza). Si una columna tiene otro nombre, la lectura falla con un mensaje que lo dice y hay que agregar la variante a `COLUMN_ALIASES` en `src/ingest.py`.
- [ ] Las fechas corresponden al mes del nombre (un archivo mensual trae también los viajes que llegan en ese mes pero salieron la noche anterior; es normal).
- [ ] Al correr la sección 1 del notebook, el mes aparece sin "faltan (requeridos)".

Los archivos de 2024 no se han visto todavía: pueden traer un formato de fecha o de columnas distinto al de 2025 y 2026. La sección 1 del notebook y el primer mes que se corra lo detectan.

## 3. Qué se procesa

1. **Lectura:** `ingest.load_one_csv` normaliza los nombres de columna y convierte las fechas (día primero).
2. **Limpieza** (la misma que ya se usa): viajes de 1 a 45 minutos; estación de origen válida; las estaciones pareadas como `271-272` se conservan completas; las temporales quedan fuera. Cada mes se guarda como parquet en `data/processed/cache_mensual/` (unos 14 MB por mes), así que la segunda vez no se vuelve a leer el CSV.
3. **Tabla por estación, fecha y hora** con `modelo.construir_tabla`, y los rezagos de 7 días o más. Para cada mes de prueba se arman dos tablas: la del año de prueba (meses -2, -1, 0 y +1) y la del año anterior (mes -1, mes y +1 del mismo mes).
4. **Orígenes de entrenamiento:** el mes anterior al de prueba; el mismo mes del año anterior; y los dos juntos.
5. **Modelos:** XGBoost con los hiperparámetros de la versión 1, regresión lineal, promedio histórico y media de 4 semanas.
6. **Salida:** `data/processed/resultados_mismo_mes.csv` (se guarda después de cada mes y se puede retomar) y `figures/20_mismo_mes_rmse.png`.

**Comprobado:** para septiembre de 2026, la lectura mes por mes da los mismos 1,473,838 viajes que `trips_clean.parquet`, con el mismo conteo en cada estación. La sección 1 del notebook repite esa comprobación.

Los archivos de enero, febrero y septiembre de 2026, y los de septiembre y octubre de 2025, ya tienen su caché creada en esta máquina.

## 4. Correrlo en la computadora

- [ ] Descargar y renombrar los archivos (sección 2). Si solo se quiere probar, no hace falta nada: el notebook corre ya el mes de septiembre de 2026.
- [ ] Desde la carpeta del proyecto: `cd notebooks` y abrir `08_mismo_mes_otro_anio.ipynb`.
- [ ] Restart & Run All. Tarda unos 20 a 25 minutos con los 13 meses (estimado).
- [ ] Si se interrumpe, volver a correr: retoma los meses que faltan. Para rehacer todo, poner `REHACER = True`.
- [ ] Anotar el tiempo real que imprime la última celda.

## 5. Si se usa Colab

Solo si los tiempos locales no alcanzan o se agrega algo pesado. El repositorio no se puede clonar en Colab con estos cambios mientras no estén subidos a GitHub, así que se usa una carpeta de Drive.

**Antes (en la computadora):**

- [ ] Dejar creada la caché de todos los meses (lee cada CSV una vez; unos 13 s por archivo): desde la carpeta del proyecto, `python src/mismo_mes.py`.
- [ ] Armar la carpeta `ecobici-demanda` con **solo** esto (cabe en unos 300 MB):
  - `src/` completa
  - `notebooks/08_mismo_mes_otro_anio.ipynb`
  - `data/processed/stations_geo.csv`
  - `data/processed/busqueda_hiperparametros.csv`
  - `data/processed/cache_mensual/` (los parquet; **no** hace falta subir los CSV)
  - una carpeta vacía `resultados/`
- [ ] Subirla a Drive en `Mi unidad/ecobici-demanda/`.

**En Colab (la cuenta con Colab Pro; se vieron 235.58 unidades):**

- [ ] Anotar las unidades disponibles antes de empezar.
- [ ] Entorno de ejecución > Cambiar tipo de entorno de ejecución: **GPU T4**, RAM amplia apagada.
- [ ] Montar Drive: `from google.colab import drive; drive.mount('/content/drive')`.
- [ ] Copiar la carpeta a disco local: `!cp -r /content/drive/MyDrive/ecobici-demanda /content/` (leer miles de operaciones directo de Drive es lento).
- [ ] Verificar la GPU: `!nvidia-smi`.
- [ ] Abrir `/content/ecobici-demanda/notebooks/08_mismo_mes_otro_anio.ipynb` y correr todo. El notebook detecta Colab, cambia de carpeta, usa la GPU en XGBoost y copia `resultados_mismo_mes.csv` a `resultados/` en Drive después de cada mes.
- [ ] Dejar la pestaña del navegador abierta mientras corre (Colab Pro no tiene ejecución en segundo plano).
- [ ] Al terminar, Entorno de ejecución > Cancelar la conexión y eliminar el entorno, para no gastar unidades.
- [ ] Anotar las unidades que quedaron y cuántas se gastaron.

## 6. Después de correr

- [ ] Llevar `resultados_mismo_mes.csv` a `data/processed/` y `figures/20_mismo_mes_rmse.png` a `figures/`.
- [ ] Completar la sección "Lectura de resultados" del notebook con lo que salga.
- [ ] Decidir si entra al reporte como un experimento más (sección "Validación en distintos meses y experimentos") y mover el punto de "Próximos pasos" a hecho.

## Pendientes que no cubre este notebook

- **Modelo para las estaciones críticas.** Es el otro comentario de los profesores. Primero hay que revisar si el sesgo positivo se concentra en las estaciones de mayor volumen; está planteado como diagnóstico en el reporte.
- **Búsqueda de hiperparámetros por mes.** Aquí se reutilizan los de la versión 1. Es lo que más justificaría Colab.
- **Limitaciones del experimento:** un mes de entrenamiento solo ve un ciclo mensual; el catálogo de estaciones es el de 2026, así que las estaciones que ya no existen entran sin latitud, longitud ni capacidad; y los hiperparámetros se eligieron con datos de 2026, lo que favorece un poco a los casos que entrenan con 2026.
