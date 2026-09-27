"""
Ingesta y limpieza básica de los CSVs históricos de viajes de Ecobici.

Uso:
    python src/ingest.py

Espera que los CSVs mensuales estén en data/raw/*.csv, descargados desde
https://ecobici.cdmx.gob.mx/en/open-data/

Columnas esperadas en los CSVs (pueden variar ligeramente entre años, el
script normaliza los nombres más comunes que se han visto en el portal):
    Genero_Usuario, Edad_Usuario, Bici,
    Ciclo_Estacion_Retiro, Fecha_Retiro, Hora_Retiro,
    Ciclo_Estacion_Arribo, Fecha_Arribo, Hora_Arribo
"""

import glob
import os

import numpy as np
import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

# Algunos meses vienen con nombres de columna ligeramente distintos
# (mayúsculas, con o sin guión bajo entre palabras, ej. "Ciclo_EstacionArribo"
# vs "Ciclo_Estacion_Arribo"). Para no depender de que cada variante esté
# escrita exactamente, la normalización quita TODOS los guiones bajos y
# compara en minúsculas, así "Ciclo_Estacion_Arribo" y "Ciclo_EstacionArribo"
# terminan siendo la misma clave ("cicloestacionarribo").
COLUMN_ALIASES = {
    "generousuario": "genero",
    "edadusuario": "edad",
    "bici": "bici_id",
    "cicloestacionretiro": "estacion_origen",
    "fecharetiro": "fecha_origen",
    "horaretiro": "hora_origen",
    "cicloestacionarribo": "estacion_destino",
    "fechaarribo": "fecha_destino",
    "horaarribo": "hora_destino",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # clave de comparación: minúsculas, sin espacios ni guiones bajos
    lookup_keys = [c.strip().lower().replace("_", "").replace(" ", "") for c in df.columns]
    new_names = []
    for original, key in zip(df.columns, lookup_keys):
        new_names.append(COLUMN_ALIASES.get(key, original.strip().lower()))
    df.columns = new_names
    return df


def load_one_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = normalize_columns(df)

    missing = {"estacion_origen", "fecha_origen", "hora_origen",
               "estacion_destino", "fecha_destino", "hora_destino"} - set(df.columns)
    if missing:
        raise ValueError(
            f"{path}: faltan columnas esperadas: {missing}\n"
            f"Columnas originales encontradas en el CSV: {list(pd.read_csv(path, nrows=0).columns)}\n"
            "-> Agrega la variante que falte a COLUMN_ALIASES en este archivo "
            "(clave = nombre de columna en minúsculas y sin guiones bajos)."
        )

    df["origen_dt"] = pd.to_datetime(
        df["fecha_origen"].astype(str) + " " + df["hora_origen"].astype(str),
        errors="coerce",
        dayfirst=True,
    )
    df["destino_dt"] = pd.to_datetime(
        df["fecha_destino"].astype(str) + " " + df["hora_destino"].astype(str),
        errors="coerce",
        dayfirst=True,
    )

    df["archivo_origen"] = os.path.basename(path)
    return df


def build_dataset() -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(RAW_DIR, "*.csv")))
    if not paths:
        raise SystemExit(
            f"No encontré CSVs en {RAW_DIR}. Baja los meses del portal de "
            "datos abiertos y ponlos ahí primero."
        )

    print(f"Encontrados {len(paths)} archivo(s):")
    for p in paths:
        print(f"  - {os.path.basename(p)}")

    frames = [load_one_csv(p) for p in paths]
    df = pd.concat(frames, ignore_index=True)

    # --- columnas derivadas útiles para el EDA y el modelo ---
    df["duracion_min"] = (df["destino_dt"] - df["origen_dt"]).dt.total_seconds() / 60
    df["hora_del_dia"] = df["origen_dt"].dt.hour
    df["dia_semana"] = df["origen_dt"].dt.day_name()
    df["fecha"] = df["origen_dt"].dt.date
    df["es_fin_de_semana"] = df["origen_dt"].dt.dayofweek >= 5

    # ids de estación como string (evita que pandas los trate como floats con .0).
    # Algunos registros traen ids corruptos (ej. "192-193", dos ids pegados) —
    # se convierten a nulo en vez de tronar, y se reporta cuántos fueron.
    for col in ["estacion_origen", "estacion_destino"]:
        numeric = pd.to_numeric(df[col], errors="coerce")
        n_corruptos = numeric.isna().sum() - df[col].isna().sum()
        if n_corruptos > 0:
            print(f"  aviso: {n_corruptos} valores no numéricos en '{col}' -> convertidos a nulo")
        df[col] = numeric.astype("Int64").astype("string")
    return df


def print_quick_summary(df: pd.DataFrame) -> None:
    print("\n--- Resumen rápido ---")
    print(f"Filas totales: {len(df):,}")
    print(f"Rango de fechas: {df['origen_dt'].min()} -> {df['origen_dt'].max()}")
    print(f"Tamaño en memoria: {df.memory_usage(deep=True).sum() / 1e6:.1f} MB")
    print("\nNulos por columna (top 10):")
    print(df.isna().sum().sort_values(ascending=False).head(10))
    print("\nDuración de viaje (min) - describe:")
    print(df["duracion_min"].describe())


if __name__ == "__main__":
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    dataset = build_dataset()
    print_quick_summary(dataset)

    out_path = os.path.join(PROCESSED_DIR, "trips_clean.parquet")
    dataset.to_parquet(out_path, index=False)
    print(f"\nGuardado en: {out_path}")
