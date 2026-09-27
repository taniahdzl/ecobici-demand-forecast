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

# Algunos meses vienen con nombres de columna distintos (mayúsculas, acentos,
# variaciones de "Ciclo_Estacion" vs "CicloEstacion"). Este mapa normaliza
# los que nos hemos encontrado; si un CSV nuevo trae otros nombres, agrégalos aquí.
COLUMN_ALIASES = {
    "genero_usuario": "genero",
    "edad_usuario": "edad",
    "bici": "bici_id",
    "ciclo_estacion_retiro": "estacion_origen",
    "fecha_retiro": "fecha_origen",
    "hora_retiro": "hora_origen",
    "ciclo_estacion_arribo": "estacion_destino",
    "fecha_arribo": "fecha_destino",
    "hora_arribo": "hora_destino",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns=COLUMN_ALIASES)
    return df


def load_one_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = normalize_columns(df)

    missing = {"estacion_origen", "fecha_origen", "hora_origen",
               "estacion_destino", "fecha_destino", "hora_destino"} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: faltan columnas esperadas: {missing}")

    df["origen_dt"] = pd.to_datetime(
        df["fecha_origen"].astype(str) + " " + df["hora_origen"].astype(str),
        errors="coerce",
    )
    df["destino_dt"] = pd.to_datetime(
        df["fecha_destino"].astype(str) + " " + df["hora_destino"].astype(str),
        errors="coerce",
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

    # ids de estación como string (evita que pandas los trate como floats con .0)
    for col in ["estacion_origen", "estacion_destino"]:
        df[col] = df[col].astype("Int64").astype("string")

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
