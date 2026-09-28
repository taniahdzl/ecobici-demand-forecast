"""
Prepara la capa geográfica del proyecto: polígonos de código postal de la
CDMX recortados al área de Ecobici, y el catálogo de estaciones con su código
postal y alcaldía.

Uso:
    python src/geo.py

Requiere data/processed/stations.csv (generado por src/stations.py) y acceso
a internet (descarga ~3 MB de polígonos + ~14 MB del catálogo de códigos
postales en cada corrida; no guarda caché).

Genera (todos se versionan en git, pesan poco):
    data/processed/cdmx_cp_ecobici.geojson
        polígonos de código postal que tocan el área de Ecobici, propiedad "cp"
    data/processed/stations_geo.csv
        station_id, ce, nombre, lat, lon, capacidad, cp, alcaldia, colonia
        (station_id = id GBFS; ce = id de estación que usan los datos de viajes)
    data/processed/cp_colonias.csv
        cp, nombre, colonias, n_colonias, alcaldia
        (nombre legible de cada CP del mapa, ej. 06700 -> "Roma Norte")

Fuente: https://github.com/open-mexico/mexico-geojson (MIT, datos SEPOMEX),
archivo 09-Cdmx.geojson fijado a un commit para que el resultado sea
reproducible. Ojo: son CÓDIGOS POSTALES, no colonias; la alcaldía se deriva
del prefijo del CP (coincide con el municipio oficial de SEPOMEX).

Nombres de colonia: Catálogo Nacional de Códigos Postales de Correos de
México (https://www.correosdemexico.gob.mx/datosabiertos/cp/cpdescarga.txt).

Correrlo de nuevo solo si cambia el catálogo de estaciones:
    python src/stations.py && python src/geo.py
"""

import io
import json
import os
from collections import Counter

import pandas as pd
import requests

from geo_utils import (
    CP_COLONIAS_PATH,
    CP_GEOJSON_PATH,
    PROCESSED_DIR,
    STATIONS_GEO_PATH,
    alcaldia_de_cp,
    asignar_cp,
    normalizar_id_estacion,
    poligonos_de_geometria,
)

GEOJSON_REPO = "open-mexico/mexico-geojson"
GEOJSON_COMMIT = "ff9a744df9e9c1db66d5de40ae14a71920cb72e7"
GEOJSON_URL = f"https://raw.githubusercontent.com/{GEOJSON_REPO}/{GEOJSON_COMMIT}/09-Cdmx.geojson"

CATALOGO_CP_URL = "https://www.correosdemexico.gob.mx/datosabiertos/cp/cpdescarga.txt"
PALABRAS_VACIAS = {"de", "del", "la", "las", "los", "el", "y", "barrio"}

# Margen (en grados, ~1 km) alrededor del rectángulo que envuelve a las
# estaciones: un polígono se conserva si su rectángulo toca esta zona.
MARGEN_GRADOS = 0.01
DECIMALES = 6  # ~10 cm; reduce el tamaño del archivo versionado


def descargar_geojson(url: str = None) -> dict:
    url = url or GEOJSON_URL
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        raise SystemExit(
            f"No pude descargar el GeoJSON de CP de la CDMX.\n  URL: {url}\n  Error: {e}\n"
            "No se modificó ningún archivo en data/processed/."
        )


def descargar_catalogo_cp(url: str = None) -> pd.DataFrame:
    """Catálogo de Correos de México filtrado a la CDMX: una fila por
    colonia (asentamiento) con su CP y municipio."""
    url = url or CATALOGO_CP_URL
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        # 1a línea = nota legal; 2a = encabezado. Viene en latin-1.
        cat = pd.read_csv(io.StringIO(r.content.decode("latin-1")), sep="|", skiprows=1, dtype=str)
        cat = cat[cat["c_estado"] == "09"]
        if cat.empty:
            raise ValueError("el catálogo no trae registros de la CDMX (c_estado = 09)")
        return cat
    except (requests.RequestException, ValueError, KeyError, pd.errors.ParserError) as e:
        raise SystemExit(
            f"No pude descargar/leer el catálogo de códigos postales.\n  URL: {url}\n  Error: {e}\n"
            "No se modificó ningún archivo en data/processed/."
        )


def nombre_legible(colonias: list) -> str:
    """1 colonia -> su nombre; 2 -> "A / B"; 3+ -> prefijo común de palabras
    + "(N colonias)", o "A y N-1 más" si no hay prefijo común útil."""
    if len(colonias) == 1:
        return colonias[0]
    if len(colonias) == 2:
        return " / ".join(colonias)
    comun = []
    for grupo in zip(*[c.split() for c in colonias]):
        if len(set(grupo)) > 1:
            break
        comun.append(grupo[0])
    while comun and comun[-1].lower() in PALABRAS_VACIAS:
        comun.pop()
    if comun:
        return f"{' '.join(comun)} ({len(colonias)} colonias)"
    return f"{colonias[0]} y {len(colonias) - 1} más"


def construir_cp_colonias(recorte: dict, catalogo: pd.DataFrame) -> pd.DataFrame:
    filas = []
    por_cp = catalogo.groupby("d_codigo")
    for cp in sorted({f["properties"]["cp"] for f in recorte["features"]}):
        if cp in por_cp.groups:
            g = por_cp.get_group(cp)
            colonias = list(dict.fromkeys(g["d_asenta"].str.strip()))
            filas.append({"cp": cp, "nombre": nombre_legible(colonias), "colonias": " / ".join(colonias),
                          "n_colonias": len(colonias), "alcaldia": g["D_mnpio"].iloc[0]})
        else:
            filas.append({"cp": cp, "nombre": cp, "colonias": "", "n_colonias": 0, "alcaldia": None})
    return pd.DataFrame(filas)


def _redondear(coords):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], DECIMALES), round(coords[1], DECIMALES)]
    return [_redondear(c) for c in coords]


def _bbox_feature(feat: dict):
    xs, ys = [], []
    for poligono in poligonos_de_geometria(feat["geometry"]):
        for x, y in poligono[0]:
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def recortar(gj: dict, stations: pd.DataFrame, margen: float = MARGEN_GRADOS) -> dict:
    """Conserva los polígonos completos cuyo rectángulo toca el área de las
    estaciones (+ margen). Renombra d_codigo -> cp (5 dígitos)."""
    x0, x1 = stations["lon"].min() - margen, stations["lon"].max() + margen
    y0, y1 = stations["lat"].min() - margen, stations["lat"].max() + margen

    features = []
    for feat in gj["features"]:
        bbox = _bbox_feature(feat)
        if bbox is None:
            continue
        fx0, fy0, fx1, fy1 = bbox
        if fx1 < x0 or fx0 > x1 or fy1 < y0 or fy0 > y1:
            continue
        geometry = feat["geometry"]
        features.append({
            "type": "Feature",
            "properties": {"cp": str(feat["properties"]["d_codigo"]).zfill(5)},
            "geometry": {"type": geometry["type"], "coordinates": _redondear(geometry["coordinates"])},
        })

    # orden estable -> corridas repetidas generan exactamente el mismo archivo
    features.sort(key=lambda f: f["properties"]["cp"])
    return {"type": "FeatureCollection", "features": features}


def enriquecer_estaciones(stations: pd.DataFrame, recorte: dict) -> pd.DataFrame:
    out = stations.copy()
    # Los viajes NO usan el station_id de GBFS: usan el número "CE-xxx" que
    # viene al inicio del nombre ("CE-710 Molino del Rey..." -> "710").
    out["ce"] = normalizar_id_estacion(out["nombre"].str.extract(r"^\s*CE-(\d+(?:-\d+)?)", expand=False))
    out["cp"] = asignar_cp(out["lon"], out["lat"], recorte["features"])
    out["alcaldia"] = [alcaldia_de_cp(cp) if cp else None for cp in out["cp"]]
    return out[["station_id", "ce", "nombre", "lat", "lon", "capacidad", "cp", "alcaldia"]]


def _escribir_atomico(path: str, contenido: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(contenido)
    os.replace(tmp, path)


def main(url: str = None, url_catalogo: str = None) -> None:
    stations_path = os.path.join(PROCESSED_DIR, "stations.csv")
    if not os.path.exists(stations_path):
        raise SystemExit(f"No encontré {stations_path}. Corre primero: python src/stations.py")
    stations = pd.read_csv(stations_path, dtype={"station_id": "string"}, encoding="utf-8")

    print("Descargando GeoJSON de códigos postales de la CDMX...")
    gj = descargar_geojson(url)
    print("Descargando catálogo de códigos postales (Correos de México)...")
    catalogo = descargar_catalogo_cp(url_catalogo)

    recorte = recortar(gj, stations)
    geo = enriquecer_estaciones(stations, recorte)
    cp_colonias = construir_cp_colonias(recorte, catalogo)
    geo["colonia"] = geo["cp"].map(cp_colonias.set_index("cp")["nombre"])

    # Se escribe hasta el final: si algo falla antes, no se toca nada.
    geojson_txt = json.dumps(recorte, ensure_ascii=False, separators=(",", ":")) + "\n"
    csv_txt = geo.to_csv(index=False, lineterminator="\n")
    _escribir_atomico(CP_GEOJSON_PATH, geojson_txt)
    _escribir_atomico(STATIONS_GEO_PATH, csv_txt)
    _escribir_atomico(CP_COLONIAS_PATH, cp_colonias.to_csv(index=False, lineterminator="\n"))

    sin_cp = geo[geo["cp"].isna()]
    print("\n--- Resumen de cobertura ---")
    print(f"Polígonos de CP conservados: {len(recorte['features'])} de {len(gj['features'])}")
    print(f"Estaciones con CP: {len(geo) - len(sin_cp)} de {len(geo)}")
    if len(sin_cp):
        print(f"Estaciones SIN CP ({len(sin_cp)}):")
        for _, fila in sin_cp.iterrows():
            print(f"  - {fila['station_id']}: {fila['nombre']}")
    sin_ce = geo[geo["ce"].isna()]
    ce_repetido = geo[geo["ce"].notna() & geo["ce"].duplicated(keep=False)]
    print(f"Estaciones con id de viajes (ce): {len(geo) - len(sin_ce)} de {len(geo)}")
    for titulo, df in [("SIN número CE en el nombre", sin_ce), ("con CE REPETIDO", ce_repetido)]:
        if len(df):
            print(f"Estaciones {titulo} ({len(df)}):")
            for _, fila in df.iterrows():
                print(f"  - {fila['station_id']} (ce={fila['ce']}): {fila['nombre']}")
    sin_nombre = cp_colonias[cp_colonias["n_colonias"] == 0]
    print(f"CPs con nombre de colonia: {len(cp_colonias) - len(sin_nombre)} de {len(cp_colonias)}")
    if len(sin_nombre):
        print(f"CPs SIN registro en el catálogo: {sin_nombre['cp'].tolist()}")
    print("\nEstaciones por alcaldía (aprox. por prefijo de CP):")
    for alcaldia, n in Counter(geo["alcaldia"].dropna()).most_common():
        print(f"  {alcaldia:<25} {n}")
    print(f"\nGuardado en:\n  {os.path.normpath(CP_GEOJSON_PATH)}\n  {os.path.normpath(STATIONS_GEO_PATH)}"
          f"\n  {os.path.normpath(CP_COLONIAS_PATH)}")


if __name__ == "__main__":
    main()
