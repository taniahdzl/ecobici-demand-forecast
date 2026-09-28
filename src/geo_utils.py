"""
Funciones reusables para trabajar con la parte geográfica del proyecto: unir
cualquier tabla con id de estación a su ubicación (lat/lon, código postal,
alcaldía) y dibujar el mapa base de códigos postales o una coropleta.

Uso (desde un notebook):

    import sys; sys.path.append("../src")
    from geo_utils import load_stations_geo, unir_geo, plot_mapa_base

Lee dos archivos ya versionados en data/processed/ (no necesita internet):
    stations_geo.csv          station_id, ce, nombre, lat, lon, capacidad, cp, alcaldia, colonia
    cdmx_cp_ecobici.geojson   polígonos de código postal recortados al área de Ecobici
    cp_colonias.csv           cp, nombre, colonias, n_colonias, alcaldia (nombre legible por CP)

Para mostrar zonas con nombre en vez de CP: etiqueta_cp("06700") -> "Roma Norte (06700)".

OJO con los ids de estación: hay DOS.
    ce          id que usan los datos de VIAJES (el "CE-710" del nombre -> "710")
    station_id  id del feed GBFS (stations.py, snapshot de estado)
unir_geo cruza por "ce" por defecto; para datos GBFS usa clave="station_id".

Si faltan, se generan con:
    python src/geo.py

Ojo: los polígonos son CÓDIGOS POSTALES (SEPOMEX), no colonias. La alcaldía
se deriva del prefijo del CP, así que es una aproximación.
"""

import json
import math
import os
import warnings

import numpy as np
import pandas as pd
from matplotlib.collections import PatchCollection
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import PathPatch
from matplotlib.path import Path

PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
STATIONS_GEO_PATH = os.path.join(PROCESSED_DIR, "stations_geo.csv")
CP_GEOJSON_PATH = os.path.join(PROCESSED_DIR, "cdmx_cp_ecobici.geojson")
CP_COLONIAS_PATH = os.path.join(PROCESSED_DIR, "cp_colonias.csv")

# Misma paleta que make_figures.py. Se copia en vez de importar ese módulo
# porque importarlo cambia plt.rcParams global como efecto secundario.
BLUE = "#2a78d6"
GRID = "#e1e0d9"
MUTED = "#898781"
INK_2 = "#52514e"
SURFACE = "#fcfcfb"

RELLENO_BASE = "#f0efea"   # polígonos del mapa base (un poco más oscuro que SURFACE)
BORDE_BASE = "#cfcdc4"
SIN_DATO = GRID            # polígonos sin valor en la coropleta
CMAP_SECUENCIAL = LinearSegmentedColormap.from_list(
    "geo_secuencial", ["#e6effa", BLUE, "#123f78"]
)

# Primeros dos dígitos del código postal en la CDMX -> alcaldía (SEPOMEX).
ALCALDIAS_POR_PREFIJO = {
    "01": "Álvaro Obregón",
    "02": "Azcapotzalco",
    "03": "Benito Juárez",
    "04": "Coyoacán",
    "05": "Cuajimalpa de Morelos",
    "06": "Cuauhtémoc",
    "07": "Gustavo A. Madero",
    "08": "Iztacalco",
    "09": "Iztapalapa",
    "10": "La Magdalena Contreras",
    "11": "Miguel Hidalgo",
    "12": "Milpa Alta",
    "13": "Tláhuac",
    "14": "Tlalpan",
    "15": "Venustiano Carranza",
    "16": "Xochimilco",
}

COLUMNAS_GEO = ["lat", "lon", "cp", "alcaldia"]


# ---------------------------------------------------------------------------
# Normalización de ids
# ---------------------------------------------------------------------------

def _normalizar_un_id(valor):
    if pd.isna(valor):
        return pd.NA
    if isinstance(valor, float):
        return str(int(valor)) if valor.is_integer() else pd.NA
    partes = str(valor).strip().split("-")
    if not all(p.isdigit() for p in partes):
        return pd.NA
    return "-".join(str(int(p)) for p in partes)


def normalizar_id_estacion(serie: pd.Series) -> pd.Series:
    """Id de estación como texto sin ceros a la izquierda en cada parte:
    "001" -> "1", 5 -> "5", "0158-0159" -> "158-159". Para ids simples es la
    misma regla que ingest.py. Lo que no tenga esa forma queda como <NA>.
    Se calcula sobre los valores únicos, así escala a millones de filas."""
    serie = pd.Series(serie)
    unicos = pd.unique(serie.to_numpy(dtype=object))
    mapa = {u: _normalizar_un_id(u) for u in unicos}
    return pd.Series(serie.to_numpy(dtype=object), index=serie.index).map(mapa).astype("string")


def normalizar_cp(valor):
    """Código postal como texto de 5 dígitos (6700 -> "06700"). None si no es
    numérico."""
    try:
        return str(int(float(str(valor).strip()))).zfill(5)
    except (TypeError, ValueError):
        return None


def alcaldia_de_cp(cp):
    """Alcaldía aproximada a partir del prefijo del CP, o None si el prefijo no
    es de la CDMX."""
    cp = normalizar_cp(cp)
    if cp is None:
        return None
    return ALCALDIAS_POR_PREFIJO.get(cp[:2])


# ---------------------------------------------------------------------------
# Geometría (sin geopandas: json + matplotlib.path)
# ---------------------------------------------------------------------------

def poligonos_de_geometria(geometry: dict) -> list:
    """Regresa la geometría como lista de polígonos; cada polígono es una
    lista de anillos [exterior, hueco1, hueco2, ...] con puntos [lon, lat]."""
    if geometry is None:
        return []
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return list(geometry["coordinates"])
    return []


def contiene_puntos(poligono: list, lons, lats) -> np.ndarray:
    """Máscara booleana: qué puntos caen dentro del polígono (dentro del
    anillo exterior y fuera de todos sus huecos)."""
    pts = np.column_stack([np.asarray(lons, dtype=float), np.asarray(lats, dtype=float)])
    dentro = Path(np.asarray(poligono[0], dtype=float)).contains_points(pts)
    for hueco in poligono[1:]:
        dentro &= ~Path(np.asarray(hueco, dtype=float)).contains_points(pts)
    return dentro


def asignar_cp(lons, lats, features: list) -> list:
    """Para cada punto regresa el CP (propiedad "cp") del primer polígono que
    lo contiene, o None si ninguno lo contiene."""
    lons = np.asarray(lons, dtype=float)
    lats = np.asarray(lats, dtype=float)
    resultado = [None] * len(lons)
    pendientes = np.ones(len(lons), dtype=bool)
    for feat in features:
        if not pendientes.any():
            break
        cp = feat["properties"]["cp"]
        for poligono in poligonos_de_geometria(feat["geometry"]):
            idx = np.flatnonzero(pendientes)
            dentro = contiene_puntos(poligono, lons[idx], lats[idx])
            for i in idx[dentro]:
                resultado[i] = cp
            pendientes[idx[dentro]] = False
    return resultado


def _area_con_signo(anillo: np.ndarray) -> float:
    x, y = anillo[:, 0], anillo[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _path_con_huecos(poligono: list) -> Path:
    """Path compuesto (exterior + huecos). Matplotlib rellena con la regla
    nonzero, así que el exterior va antihorario y los huecos horario para que
    los huecos queden vacíos."""
    vertices, codigos = [], []
    for i, anillo in enumerate(poligono):
        a = np.asarray(anillo, dtype=float)
        if len(a) < 3:
            continue
        antihorario = _area_con_signo(a) > 0
        if (i == 0) != antihorario:
            a = a[::-1]
        vertices.append(a)
        codigos.append([Path.MOVETO] + [Path.LINETO] * (len(a) - 2) + [Path.CLOSEPOLY])
    return Path(np.concatenate(vertices), np.concatenate(codigos))


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def _exigir_archivo(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No encontré {os.path.normpath(path)}. "
            "Genera la capa geográfica con: python src/geo.py"
        )


def load_stations_geo() -> pd.DataFrame:
    """Catálogo de estaciones con lat, lon, cp y alcaldía. station_id (GBFS),
    ce (id en datos de viajes) y cp se cargan como texto (cp con 5 dígitos,
    ej. "06700")."""
    _exigir_archivo(STATIONS_GEO_PATH)
    return pd.read_csv(
        STATIONS_GEO_PATH,
        dtype={"station_id": "string", "ce": "string", "cp": "string", "alcaldia": "string"},
        encoding="utf-8",
    )


def load_cp_geojson() -> dict:
    """GeoJSON (FeatureCollection) de códigos postales recortado al área de
    Ecobici. Cada feature tiene la propiedad "cp"."""
    _exigir_archivo(CP_GEOJSON_PATH)
    with open(CP_GEOJSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_cp_colonias() -> pd.DataFrame:
    """Nombre legible de cada CP del mapa (cp, nombre, colonias, n_colonias,
    alcaldia). cp se carga como texto de 5 dígitos."""
    _exigir_archivo(CP_COLONIAS_PATH)
    return pd.read_csv(CP_COLONIAS_PATH, dtype={"cp": "string"}, encoding="utf-8")


def etiqueta_cp(cp, con_cp: bool = True):
    """Nombre legible de un CP: "06700" -> "Roma Norte (06700)", o "Roma Norte"
    con con_cp=False. Acepta un CP o una colección (Serie, índice, lista) y
    regresa lo mismo. Un CP desconocido se regresa tal cual.

        tabla.index = etiqueta_cp(tabla.index)          # tabla agregada por CP
        ax.set_title(f"Lidera {etiqueta_cp(cp, con_cp=False)}")
    """
    nombres = load_cp_colonias().set_index("cp")["nombre"]

    def una(c):
        norm = normalizar_cp(c)
        if norm is None or norm not in nombres.index:
            return str(c)
        return f"{nombres[norm]} ({norm})" if con_cp else nombres[norm]

    if isinstance(cp, (pd.Series, pd.Index, list, tuple, np.ndarray)):
        etiquetas = [una(c) for c in cp]
        if isinstance(cp, pd.Series):
            return pd.Series(etiquetas, index=cp.index, name=cp.name)
        if isinstance(cp, pd.Index):
            return pd.Index(etiquetas, name=cp.name)
        return etiquetas
    return una(cp)


# ---------------------------------------------------------------------------
# Unir datos con su geografía
# ---------------------------------------------------------------------------

CLAVES_VALIDAS = ("ce", "station_id")


def unir_geo(df: pd.DataFrame, col_id: str = "station_id", prefijo: str = "", clave: str = "ce") -> pd.DataFrame:
    """Agrega {prefijo}lat, {prefijo}lon, {prefijo}cp y {prefijo}alcaldia a
    partir de la columna de id de estación `col_id`.

    `clave` dice contra qué id del catálogo se cruza:
      - "ce" (default): id que usan los datos de VIAJES (estacion_origen,
        estacion_destino). Es el número "CE-xxx" del nombre de la estación.
      - "station_id": id del feed GBFS (snapshot de estado, stations.py).

    - Es un left join: conserva todas las filas, en el mismo orden y con el
      mismo índice. No modifica `df` (regresa una copia).
    - Los ids se normalizan antes de cruzar ("001", 1 y "1" cruzan con "1";
      "0158-0159" cruza con la estación pareada "158-159").
    - Si hay filas sin coordenadas se conservan con valores vacíos y se emite
      un warning con cuántas son, ejemplos de ids y la clave usada.

    Ejemplos:

        # tabla de viajes agregada por estación
        demanda = unir_geo(demanda, col_id="estacion_origen")

        # viajes: dos estaciones por fila -> dos llamadas con prefijo
        t = unir_geo(trips, "estacion_origen",  prefijo="origen_")
        t = unir_geo(t,     "estacion_destino", prefijo="destino_")

        # datos GBFS (snapshot de estado): cruzar por station_id
        snap = unir_geo(load_status_snapshot(), "station_id", clave="station_id")

    Consejo: con el histórico completo de viajes conviene AGREGAR PRIMERO y
    unir después; unir millones de filas agrega 4 columnas a cada una.
    """
    if clave not in CLAVES_VALIDAS:
        raise ValueError(f"unir_geo: clave='{clave}' no es válida. Usa una de {list(CLAVES_VALIDAS)}.")
    if col_id not in df.columns:
        raise KeyError(
            f"unir_geo: no existe la columna '{col_id}'. "
            f"Columnas disponibles: {list(df.columns)}"
        )

    nuevas = [prefijo + c for c in COLUMNAS_GEO]
    choques = [c for c in nuevas if c in df.columns]
    if choques:
        raise ValueError(
            f"unir_geo: las columnas {choques} ya existen en el DataFrame. "
            "Usa un prefijo distinto (ej. prefijo='origen_') para no sobrescribirlas."
        )

    geo = load_stations_geo()
    geo["_llave"] = normalizar_id_estacion(geo[clave])
    geo = geo.dropna(subset=["_llave"])
    if geo["_llave"].duplicated().any():
        raise ValueError(f"unir_geo: stations_geo.csv tiene '{clave}' duplicados; regenera con python src/geo.py")
    geo = geo.set_index("_llave")

    llave = normalizar_id_estacion(df[col_id])
    out = df.copy()
    for col, nueva in zip(COLUMNAS_GEO, nuevas):
        out[nueva] = llave.map(geo[col])

    sin_geo = out[prefijo + "lat"].isna()
    if sin_geo.any():
        n, total = int(sin_geo.sum()), len(out)
        faltantes = df.loc[sin_geo.values, col_id]
        n_vacios = int(faltantes.isna().sum())
        ids = faltantes.dropna().astype(str).unique()
        detalle = f"{len(ids)} ids sin estación en el catálogo, ej. {list(ids[:10])}" if len(ids) else "ningún id sin estación"
        if n_vacios:
            detalle += f"; {n_vacios:,} filas con id vacío (ej. ids pareados que ingest.py deja vacíos)"
        warnings.warn(
            f"unir_geo: {n:,} de {total:,} filas ({100 * n / total:.1f}%) sin coordenadas "
            f"en '{col_id}' cruzando por clave='{clave}': {detalle}",
            stacklevel=2,
        )
    return out


# ---------------------------------------------------------------------------
# Mapa base / coropleta
# ---------------------------------------------------------------------------

def plot_mapa_base(ax, valores: pd.Series = None, margen: float = 0.01):
    """Dibuja los polígonos de código postal del área de Ecobici en `ax`.

    Sin `valores`: fondo neutro para dibujar encima (estaciones, flechas...).
    Regresa `ax`.

        fig, ax = plt.subplots(figsize=(10, 10))
        plot_mapa_base(ax)
        ax.scatter(est["lon"], est["lat"], s=8)

    Con `valores` (Serie indexada por CP): coropleta con escala secuencial;
    los CPs sin valor se pintan en gris neutro. Regresa `(ax, mappable)` para
    poder agregar la barra de color.

        ax, mappable = plot_mapa_base(ax, valores=salidas_por_cp)
        fig.colorbar(mappable, ax=ax, label="Salidas totales")

    El encuadre se ajusta a las estaciones (+ `margen` en grados) y el aspecto
    se corrige por la latitud para no deformar la geografía.
    """
    gj = load_cp_geojson()
    estaciones = load_stations_geo()

    parches, cps = [], []
    for feat in gj["features"]:
        for poligono in poligonos_de_geometria(feat["geometry"]):
            parches.append(PathPatch(_path_con_huecos(poligono)))
            cps.append(feat["properties"]["cp"])

    borde = dict(edgecolor=BORDE_BASE, linewidths=0.4)
    mappable = None

    if valores is None:
        ax.add_collection(PatchCollection(parches, facecolor=RELLENO_BASE, zorder=0, **borde))
    else:
        valores = pd.Series(valores)
        indice = [normalizar_cp(c) for c in valores.index]
        valores = pd.Series(valores.values, index=indice, dtype=float)
        if valores.index.duplicated().any():
            dup = sorted(set(valores.index[valores.index.duplicated()].dropna()))
            raise ValueError(f"plot_mapa_base: CPs repetidos en `valores`: {dup}. Agrega antes de graficar.")

        conocidos = set(cps)
        desconocidos = [c for c in valores.index if c not in conocidos]
        if desconocidos:
            warnings.warn(
                f"plot_mapa_base: {len(desconocidos)} CP(s) de `valores` no están en el mapa y se "
                f"ignoran: {desconocidos[:10]}",
                stacklevel=2,
            )

        con_valor = [(p, valores[c]) for p, c in zip(parches, cps) if c in valores.index and pd.notna(valores[c])]
        sin_valor = [p for p, c in zip(parches, cps) if not (c in valores.index and pd.notna(valores[c]))]

        if sin_valor:
            ax.add_collection(PatchCollection(sin_valor, facecolor=SIN_DATO, zorder=0, **borde))
        coleccion = PatchCollection([p for p, _ in con_valor], cmap=CMAP_SECUENCIAL, zorder=0, **borde)
        coleccion.set_array(np.array([v for _, v in con_valor], dtype=float))
        ax.add_collection(coleccion)
        mappable = coleccion

    lat_min, lat_max = estaciones["lat"].min(), estaciones["lat"].max()
    lon_min, lon_max = estaciones["lon"].min(), estaciones["lon"].max()
    ax.set_xlim(lon_min - margen, lon_max + margen)
    ax.set_ylim(lat_min - margen, lat_max + margen)
    ax.set_aspect(1 / math.cos(math.radians((lat_min + lat_max) / 2)))
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_facecolor(SURFACE)

    return ax if mappable is None else (ax, mappable)
