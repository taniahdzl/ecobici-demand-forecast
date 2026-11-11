"""
Mismo mes de otro año (notebook 08).

Pregunta: para predecir un mes (por ejemplo marzo de 2026), ¿sirve más entrenar con el
mes inmediato anterior (febrero de 2026) o con el MISMO mes del año anterior (marzo de 2025)?
También se prueba entrenar con los dos juntos.

Este módulo carga los CSV mensuales de uno en uno (sin reconstruir `trips_clean.parquet`),
arma la tabla estación-fecha-hora con las mismas funciones de `modelo.py` y corre la comparación.

Dónde van los archivos:
  - data/raw/AAAA-MM.csv             los meses que ya se tienen (sep 2025 – sep 2026)
  - data/raw/anteriores/AAAA-MM.csv  los meses nuevos que se bajan (2024 y ene–ago 2025)
    (una subcarpeta aparte para que `src/ingest.py` NO los mezcle en trips_clean.parquet)
  - data/processed/cache_mensual/    caché de viajes limpios por mes (se crea sola; se puede borrar)

Los archivos de un mes contienen los viajes que LLEGAN en ese mes: los de la última noche del mes
anterior vienen en el archivo siguiente. Por eso, al armar una tabla se cargan también el mes
anterior (para los rezagos) y, si existe, el mes siguiente (para no perder los últimos viajes).
"""

import os
import time

import numpy as np
import pandas as pd

import ingest
import modelo as M

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(RAIZ, "data", "raw")
RAW_ANTERIORES = os.path.join(RAW, "anteriores")
CACHE = os.path.join(RAIZ, "data", "processed", "cache_mensual")


# ---------------------------------------------------------------- archivos

def sumar_meses(mes: str, n: int) -> str:
    """'2026-03' + (-1) -> '2026-02'."""
    return str(pd.Period(mes, freq="M") + n)


def ruta_mes(mes: str):
    """Ruta del CSV de un mes (busca en data/raw y en data/raw/anteriores); None si no está."""
    for carpeta in (RAW, RAW_ANTERIORES):
        p = os.path.join(carpeta, f"{mes}.csv")
        if os.path.exists(p):
            return p
    return None


def _ruta_cache(mes: str) -> str:
    return os.path.join(CACHE, f"{mes}.parquet")


def disponible(mes: str) -> bool:
    return ruta_mes(mes) is not None or os.path.exists(_ruta_cache(mes))


def plan_par(prueba: str) -> dict:
    """Qué meses hacen falta para evaluar `prueba` contra el mismo mes del año anterior.

    Requeridos: mes de prueba, mes anterior (entrena) y el mismo mes un año antes (entrena).
    Opcionales: dan historia para los rezagos (si faltan, se pierden los primeros días de ese
    mes de entrenamiento) o los últimos viajes de la noche del último día.
    """
    s = sumar_meses(prueba, -12)
    return {
        "prueba": prueba,
        "mismo_mes_anio_anterior": s,
        "requeridos": [sumar_meses(prueba, -1), prueba, s],
        "opcionales": [sumar_meses(prueba, -2), sumar_meses(prueba, 1), sumar_meses(s, -1), sumar_meses(s, 1)],
    }


def revisar_archivos(pruebas) -> pd.DataFrame:
    """Tabla con los archivos que faltan para cada mes de prueba y si el par se puede correr."""
    filas = []
    for p in pruebas:
        plan = plan_par(p)
        falt_req = [m for m in plan["requeridos"] if not disponible(m)]
        falt_opc = [m for m in plan["opcionales"] if not disponible(m)]
        filas.append({
            "prueba": p,
            "mismo mes, año anterior": plan["mismo_mes_anio_anterior"],
            "faltan (requeridos)": ", ".join(falt_req) or "—",
            "faltan (opcionales)": ", ".join(falt_opc) or "—",
            "corre": len(falt_req) == 0,
        })
    return pd.DataFrame(filas)


# ---------------------------------------------------------------- carga y limpieza

def _id_estacion(serie: pd.Series) -> pd.Series:
    """Mismo criterio que ingest.build_dataset: número entero como texto; los pares ('271-272')
    se conservan completos; 'Temporal N' y otros no numéricos quedan vacíos."""
    crudo = serie.astype(str)
    es_par = crudo.str.match(r"^\d+-\d+$")
    numerico = pd.to_numeric(serie, errors="coerce")
    id_final = numerico.astype("Int64").astype("string")
    return id_final.mask(es_par, crudo.str.strip())


def validos_mes(mes: str) -> pd.DataFrame:
    """Viajes de 1 a 45 min con estación de origen válida, de un archivo mensual.

    Regresa las mismas columnas que `modelo.cargar_validos()`. La primera vez lee el CSV
    (tarda ~1 min) y guarda una caché en parquet; después es casi instantáneo.
    """
    cache = _ruta_cache(mes)
    if os.path.exists(cache):
        return pd.read_parquet(cache)

    path = ruta_mes(mes)
    if path is None:
        raise FileNotFoundError(f"No encuentro {mes}.csv en {RAW} ni en {RAW_ANTERIORES}")
    df = ingest.load_one_csv(path)

    out = pd.DataFrame({
        "estacion_origen": _id_estacion(df["estacion_origen"]),
        "origen_dt": df["origen_dt"],
        "duracion_min": (df["destino_dt"] - df["origen_dt"]).dt.total_seconds() / 60,
    })
    ok = out["duracion_min"].between(1, 45) & out["estacion_origen"].notna() & out["origen_dt"].notna()
    out = out.loc[ok].reset_index(drop=True)
    out["hora_del_dia"] = out["origen_dt"].dt.hour.astype("int32")
    out = out[["estacion_origen", "origen_dt", "hora_del_dia", "duracion_min"]]

    os.makedirs(CACHE, exist_ok=True)
    out.to_parquet(cache, index=False)
    return out


PRUEBAS = [f"2026-{m:02d}" for m in range(1, 10)] + [f"2025-{m:02d}" for m in range(9, 13)]


def preparar_cache(pruebas=PRUEBAS) -> list:
    """Lee y guarda en caché todos los meses disponibles que necesitan los meses de prueba.

    Sirve para dejar listos los parquet (unos 14 MB por mes) antes de llevarlos a Colab:
    `python src/mismo_mes.py`. Regresa la lista de meses preparados.
    """
    meses = sorted({m for p in pruebas for m in plan_par(p)["requeridos"] + plan_par(p)["opcionales"] if disponible(m)})
    for m in meses:
        validos_mes(m)
        print(f"  {m}: listo")
    return meses


def tabla_ventana(meses, estaciones: pd.DataFrame) -> pd.DataFrame:
    """Tabla estación-fecha-hora (con rezagos) a partir de una lista de meses consecutivos.

    Se descartan los viajes que salieron antes del primer día del primer mes cargado: son los
    de la última noche del mes anterior que llegaron después de medianoche, y dejarían un día
    casi vacío que contaminaría los rezagos.
    """
    meses = [m for m in meses if disponible(m)]
    v = pd.concat([validos_mes(m) for m in meses], ignore_index=True)
    v = v[v["origen_dt"] >= pd.Timestamp(meses[0] + "-01")].reset_index(drop=True)
    return M.construir_tabla(v, estaciones)


def recortar(tabla: pd.DataFrame, mes: str) -> pd.DataFrame:
    ini = pd.Timestamp(mes + "-01")
    fin = ini + pd.offsets.MonthEnd(0)
    return tabla[(tabla["fecha"] >= ini) & (tabla["fecha"] <= fin)].copy()


def unificar_categorias(*tablas) -> None:
    """Las tablas de años distintos se construyen por separado; hay que darles las mismas
    categorías (estación, CP, alcaldía) para que XGBoost lea igual los códigos en train y test."""
    for c in M.FEATURES_CAT:
        cats = sorted(set().union(*[set(t[c].cat.categories) for t in tablas]))
        tipo = pd.CategoricalDtype(cats)
        for t in tablas:
            t[c] = t[c].astype(tipo)


# ---------------------------------------------------------------- experimento

def configurar_dispositivo() -> str:
    """Usa la GPU en XGBoost si hay una (Colab); si no, CPU."""
    import subprocess

    try:
        hay_gpu = subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0
    except FileNotFoundError:
        hay_gpu = False
    M.PARAM_BASE["device"] = "cuda" if hay_gpu else "cpu"
    return M.PARAM_BASE["device"]


def cargar_params(ruta_busqueda: str = None) -> dict:
    """Hiperparámetros de XGBoost de la versión 1 (primera fila de busqueda_hiperparametros.csv)."""
    ruta_busqueda = ruta_busqueda or os.path.join(M.PROCESSED_DIR, "busqueda_hiperparametros.csv")
    h = pd.read_csv(ruta_busqueda).iloc[0]
    return {k: (h[k] if k == "objective" else int(h[k]) if k in ("max_depth", "min_child_weight") else float(h[k]))
            for k in M.ESPACIO_BUSQUEDA}


def evaluar_par(prueba: str, params: dict, estaciones: pd.DataFrame,
                usar_lineal: bool = True, usar_mlp: bool = False, log=print) -> list:
    """Predice el mes `prueba` entrenando con (a) el mes anterior, (b) el mismo mes del año
    anterior y (c) ambos. Regresa una lista de filas (una por modelo) para el CSV de resultados."""
    plan = plan_par(prueba)
    s = plan["mismo_mes_anio_anterior"]
    t_ini = time.time()

    # Año de prueba: mes-2 (rezagos), mes-1 (entrena "reciente"), mes (prueba), mes+1 (cola)
    tabla_t = tabla_ventana([sumar_meses(prueba, k) for k in (-2, -1, 0, 1)], estaciones)
    test = recortar(tabla_t, prueba)
    reciente = recortar(tabla_t, sumar_meses(prueba, -1))
    # Año anterior: el mismo mes, con su mes previo para los rezagos y el siguiente como cola
    tabla_s = tabla_ventana([sumar_meses(s, k) for k in (-1, 0, 1)], estaciones)
    previo = recortar(tabla_s, s)
    del tabla_t, tabla_s
    unificar_categorias(test, reciente, previo)
    ambos = pd.concat([previo, reciente], ignore_index=True)
    log(f"  tablas listas en {time.time() - t_ini:.0f} s | prueba {len(test):,} filas | "
        f"mes anterior {len(reciente):,} ({reciente['fecha'].nunique()} días) | "
        f"{s} {len(previo):,} ({previo['fecha'].nunique()} días)")

    y = test[M.TARGET].to_numpy()
    origenes = {"mes anterior": reciente, "mismo mes, año anterior": previo}
    filas = []

    def registrar(nombre, pred, train, segundos):
        filas.append({
            "mes": prueba, "modelo": nombre,
            "dias_train": int(train["fecha"].nunique()) if train is not None else 0,
            "filas_train": int(len(train)) if train is not None else 0,
            "demanda_prueba": float(y.mean()),
            "demanda_train": float(train[M.TARGET].mean()) if train is not None else np.nan,
            **M.metricas(y, pred), "segundos": round(segundos, 1),
        })
        log(f"  {nombre:<42s} RMSE {filas[-1]['RMSE']:.3f}  ({segundos:.0f} s)")

    registrar("Media 4 semanas", M.baseline_media_4sem(test), None, 0.0)
    for etiqueta, tr in origenes.items():
        registrar(f"Promedio histórico ({etiqueta})", M.baseline_promedio(tr, test), tr, 0.0)

    if usar_lineal:
        for etiqueta, tr in origenes.items():
            t0 = time.time()
            registrar(f"Regresión lineal ({etiqueta})", M.entrenar_lineal(tr).predict(test), tr, time.time() - t0)

    if usar_mlp:
        for etiqueta, tr in origenes.items():
            t0 = time.time()
            mlp, _ = M.entrenar_mlp(tr)
            registrar(f"MLP ({etiqueta})", mlp.predict(test), tr, time.time() - t0)

    for etiqueta, tr in {**origenes, "ambos": ambos}.items():
        t0 = time.time()
        n_arb = M.elegir_arboles(tr, params)
        modelo = M.entrenar_xgb(tr, params, n_arb)
        pred = np.clip(modelo.predict(test[M.FEATURES]), 0, None)
        registrar(f"XGBoost ({etiqueta})", pred, tr, time.time() - t0)

    log(f"  total {prueba}: {time.time() - t_ini:.0f} s")
    return filas


if __name__ == "__main__":
    print("Preparando la caché de los meses disponibles...")
    preparar_cache()
