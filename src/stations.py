"""
Cruza el id de estación con su ubicación (lat/lon) y captura una foto del
estado en tiempo real, usando el feed GBFS oficial de Ecobici.

Uso:
    python src/stations.py

Genera:
    data/processed/stations.csv
        station_id, nombre, lat, lon, capacidad
    data/processed/station_status_snapshot.csv
        station_id, bicis_disponibles, espacios_disponibles, timestamp_snapshot

Estos dos archivos son la pieza que conecta:
    - el histórico de viajes (que solo trae station_id) -> mapa
    - el estado en tiempo real -> comparación en vivo contra tu predicción
"""

import datetime as dt
import os

import pandas as pd
import requests

PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

STATION_INFO_URL = "https://gbfs.mex.lyftbikes.com/gbfs/es/station_information.json"
STATION_STATUS_URL = "https://gbfs.mex.lyftbikes.com/gbfs/es/station_status.json"


def fetch_station_information() -> pd.DataFrame:
    r = requests.get(STATION_INFO_URL, timeout=15)
    r.raise_for_status()
    stations = r.json()["data"]["stations"]

    df = pd.DataFrame(stations)
    cols = {
        "station_id": "station_id",
        "name": "nombre",
        "lat": "lat",
        "lon": "lon",
        "capacity": "capacidad",
    }
    keep = [c for c in cols if c in df.columns]
    df = df[keep].rename(columns=cols)
    return df


def fetch_station_status() -> pd.DataFrame:
    r = requests.get(STATION_STATUS_URL, timeout=15)
    r.raise_for_status()
    stations = r.json()["data"]["stations"]

    df = pd.DataFrame(stations)
    cols = {
        "station_id": "station_id",
        "num_bikes_available": "bicis_disponibles",
        "num_docks_available": "espacios_disponibles",
        "is_renting": "esta_rentando",
        "is_returning": "esta_recibiendo",
    }
    keep = [c for c in cols if c in df.columns]
    df = df[keep].rename(columns=cols)
    df["timestamp_snapshot"] = dt.datetime.now().isoformat(timespec="seconds")
    return df


if __name__ == "__main__":
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    info = fetch_station_information()
    info_path = os.path.join(PROCESSED_DIR, "stations.csv")
    info.to_csv(info_path, index=False)
    print(f"Catálogo de estaciones ({len(info)} estaciones) -> {info_path}")

    status = fetch_station_status()
    status_path = os.path.join(PROCESSED_DIR, "station_status_snapshot.csv")
    status.to_csv(status_path, index=False)
    print(f"Snapshot de estado en tiempo real ({len(status)} estaciones) -> {status_path}")

    # Vista previa de cómo se cruzan (útil para el mapa)
    merged = info.merge(status, on="station_id", how="left")
    print("\nEjemplo cruzado (primeras 5 filas):")
    print(merged.head())
