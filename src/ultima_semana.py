"""
Prueba hacia adelante: predecir una semana que el modelo nunca vio (notebook 11).

Para la tercera presentación se pide mostrar el mejor modelo, compararlo con los otros y dar ejemplos
concretos. Aquí se predice una semana completa (lunes a domingo) de datos que no estaban en la
presentación anterior, con dos versiones del mismo XGBoost:

  - congelado:    entrenado solo con lo que había en la presentación anterior (hasta `corte_congelado`)
  - reentrenado:  entrenado con todo lo anterior al primer día de la semana de prueba

Los dos usan los mismos hiperparámetros (versión 1, primera fila de busqueda_hiperparametros.csv) y las
mismas variables que 06 y 10, todas con al menos 7 días de rezago: para el último día de la semana de
prueba (inicio + 6) el rezago más reciente es inicio - 1, así que ninguna variable usa datos de la semana
que se predice. Se comparan con el promedio histórico, la media de 4 semanas, la regresión lineal y,
opcionalmente, el MLP.

Los CSV mensuales se leen con `mismo_mes.py` (misma limpieza que la ingesta y caché en parquet).
"""

import time

import numpy as np
import pandas as pd

import mismo_mes as MM
import modelo as M

MODELOS_BASE = ["Media 4 semanas", "Promedio histórico", "Regresión lineal"]


# ---------------------------------------------------------------- datos

def meses_necesarios(inicio_prueba: str, dias: int, desde: str) -> list:
    """Meses desde `desde` hasta el mes del último día de la semana de prueba."""
    fin = pd.Timestamp(inicio_prueba) + pd.Timedelta(days=dias - 1)
    ult = f"{fin:%Y-%m}"
    meses, m = [], desde
    while m <= ult:
        meses.append(m)
        m = MM.sumar_meses(m, 1)
    return meses


def revisar(inicio_prueba: str, dias: int = 7, desde: str = "2025-09") -> list:
    """Lista de meses que faltan (CSV o caché). Lista vacía = se puede correr."""
    return [m for m in meses_necesarios(inicio_prueba, dias, desde) if not MM.disponible(m)]


def preparar_tabla(inicio_prueba: str, dias: int, desde: str, estaciones: pd.DataFrame, log=print) -> pd.DataFrame:
    """Tabla estación-fecha-hora con rezagos, hasta el último día de la semana de prueba."""
    t0 = time.time()
    meses = meses_necesarios(inicio_prueba, dias, desde)
    siguiente = MM.sumar_meses(meses[-1], 1)
    if MM.disponible(siguiente):
        meses.append(siguiente)          # cola: viajes de la última noche del mes
    tabla = MM.tabla_ventana(meses, estaciones)
    fin = pd.Timestamp(inicio_prueba) + pd.Timedelta(days=dias - 1)
    tabla = tabla[tabla["fecha"] <= fin].reset_index(drop=True)
    log(f"Tabla lista en {time.time() - t0:.0f} s: {len(tabla):,} filas, "
        f"{tabla['fecha'].min().date()} a {tabla['fecha'].max().date()}, meses {meses[0]} a {meses[-1]}")
    return tabla


def partir(tabla: pd.DataFrame, inicio_prueba: str, dias: int = 7, corte_congelado: str = None):
    """(train congelado, train reentrenado, prueba).

    reentrenado: todo lo anterior al primer día de prueba. congelado: hasta `corte_congelado`
    (por omisión, igual que reentrenado)."""
    ini = pd.Timestamp(inicio_prueba)
    fin = ini + pd.Timedelta(days=dias - 1)
    corte = pd.Timestamp(corte_congelado) if corte_congelado else ini - pd.Timedelta(days=1)
    if corte >= ini:
        raise ValueError("El corte del modelo congelado debe ser anterior al primer día de la prueba.")
    test = tabla[(tabla["fecha"] >= ini) & (tabla["fecha"] <= fin)].copy().reset_index(drop=True)
    if test["fecha"].nunique() < dias:
        raise ValueError(f"En la tabla solo hay {test['fecha'].nunique()} de {dias} días de prueba; "
                         "revisa que el CSV del mes esté completo.")
    reent = tabla[tabla["fecha"] < ini]
    cong = tabla[tabla["fecha"] <= corte]
    return cong, reent, test


# ---------------------------------------------------------------- modelos

def xgb_predecir(train: pd.DataFrame, test: pd.DataFrame, params: dict, log=print):
    """Elige árboles por early stopping, entrena con todo train y predice test. Regresa (pred, n_árboles)."""
    t0 = time.time()
    n_arb = M.elegir_arboles(train, params)
    modelo = M.entrenar_xgb(train, params, n_arb)
    pred = np.clip(modelo.predict(test[M.FEATURES]), 0, None)
    log(f"  XGBoost: {n_arb} árboles, {len(train):,} filas, {time.time() - t0:.0f} s")
    return pred, n_arb


def predecir(cong: pd.DataFrame, reent: pd.DataFrame, test: pd.DataFrame, params: dict,
             usar_lineal: bool = True, usar_mlp: bool = False, log=print) -> pd.DataFrame:
    """Predicciones de todos los modelos sobre la semana de prueba (una columna por modelo)."""
    out = test[["estacion", "fecha", "hora", "dia_semana", M.TARGET]].copy()
    out["estacion"] = out["estacion"].astype(str)

    out["Media 4 semanas"] = M.baseline_media_4sem(test)
    out["Promedio histórico"] = M.baseline_promedio(reent, test)
    if usar_lineal:
        out["Regresión lineal"] = M.entrenar_lineal(reent).predict(test)
    if usar_mlp:
        t0 = time.time()
        mlp, _ = M.entrenar_mlp(reent)
        out["MLP"] = mlp.predict(test)
        log(f"  MLP: {time.time() - t0:.0f} s")
    out["XGBoost congelado"], _ = xgb_predecir(cong, test, params, log)
    out["XGBoost reentrenado"], _ = xgb_predecir(reent, test, params, log)
    return out.reset_index(drop=True)


def columnas_modelo(pred: pd.DataFrame) -> list:
    return [c for c in pred.columns if c not in ("estacion", "fecha", "hora", "dia_semana", M.TARGET)]


# ---------------------------------------------------------------- resultados

def tabla_metricas(pred: pd.DataFrame) -> pd.DataFrame:
    """RMSE, MAE y sesgo de cada modelo sobre toda la semana, ordenado por RMSE."""
    y = pred[M.TARGET].to_numpy(dtype=float)
    filas = [{"modelo": c, **M.metricas(y, pred[c]), "demanda_real": float(y.mean())} for c in columnas_modelo(pred)]
    t = pd.DataFrame(filas).sort_values("RMSE").reset_index(drop=True)
    t["Sesgo_%_de_demanda"] = 100 * t["Sesgo"] / t["demanda_real"]
    return t


def metricas_por_dia(pred: pd.DataFrame, modelos=None) -> pd.DataFrame:
    """RMSE por día de la semana de prueba (una fila por fecha)."""
    modelos = modelos or columnas_modelo(pred)
    y = pred[M.TARGET].to_numpy(dtype=float)
    d = pd.DataFrame({"fecha": pred["fecha"]})
    for c in modelos:
        d[c] = (pred[c].to_numpy(dtype=float) - y) ** 2
    return np.sqrt(d.groupby("fecha").mean())


def sesgo_por_hora(pred: pd.DataFrame, modelos=None) -> pd.DataFrame:
    """Sesgo medio (predicho menos real) por hora del día."""
    modelos = modelos or columnas_modelo(pred)
    y = pred[M.TARGET].to_numpy(dtype=float)
    d = pd.DataFrame({"hora": pred["hora"].to_numpy()})
    for c in modelos:
        d[c] = pred[c].to_numpy(dtype=float) - y
    return d.groupby("hora").mean()


def red_por_hora(pred: pd.DataFrame, modelos) -> pd.DataFrame:
    """Salidas totales de toda la red por fecha y hora: real y predicho (indexado por fecha-hora)."""
    g = pred.groupby(["fecha", "hora"])[[M.TARGET] + list(modelos)].sum().reset_index()
    g["momento"] = g["fecha"] + pd.to_timedelta(g["hora"], unit="h")
    return g.set_index("momento")


def resumen_estaciones(pred: pd.DataFrame, modelo: str, min_demanda: float = 1.0) -> pd.DataFrame:
    """Por estación: demanda media por hora, RMSE, MAE, sesgo y error relativo (MAE / demanda media)."""
    d = pred[["estacion", M.TARGET]].copy()
    d["err"] = pred[modelo].to_numpy(dtype=float) - d[M.TARGET].to_numpy(dtype=float)
    d["abs"] = d["err"].abs()
    d["sq"] = d["err"] ** 2
    g = d.groupby("estacion")
    t = pd.DataFrame({
        "demanda_media": g[M.TARGET].mean(),
        "RMSE": np.sqrt(g["sq"].mean()),
        "MAE": g["abs"].mean(),
        "Sesgo": g["err"].mean(),
    })
    t = t[t["demanda_media"] >= min_demanda].copy()
    t["error_relativo_%"] = 100 * t["MAE"] / t["demanda_media"]
    return t.sort_values("error_relativo_%")


def casos_estacion_hora(pred: pd.DataFrame, modelo: str, n: int = 5, min_real: int = 5) -> dict:
    """Los `n` mejores y peores aciertos a nivel estación-fecha-hora entre las filas con demanda real alta.

    Aciertos: menor error absoluto relativo; fallos: mayor error absoluto (en salidas)."""
    d = pred[pred[M.TARGET] >= min_real].copy()
    d["error"] = d[modelo] - d[M.TARGET]
    d["error_abs"] = d["error"].abs()
    cols = ["estacion", "fecha", "hora", M.TARGET, modelo, "error"]
    return {
        "aciertos": d.sort_values("error_abs").head(n)[cols],
        "fallos": d.sort_values("error_abs", ascending=False).head(n)[cols],
    }
