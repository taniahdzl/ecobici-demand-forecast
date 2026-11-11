"""
Diagnóstico de estaciones críticas (notebook 09).

Los profesores notaron que el modelo sobreestimaba. Aquí se revisa si ese sesgo se concentra en
las estaciones que más importan para el rebalanceo, y si un modelo hecho solo para ellas lo corrige.

"Críticas" se define de dos maneras, las dos calculadas SOLO con los datos de entrenamiento
(si se calcularan con todo el periodo, la lista conocería el futuro del conjunto de prueba):

  - por volumen:  el `fraccion` de estaciones con más salidas
  - por déficit:  el `fraccion` de estaciones que más bicicletas pierden por día laboral
                  (llegadas menos salidas) en el pico de la mañana o en el de la tarde
"""

import numpy as np
import pandas as pd

import modelo as M

PICO_MANANA = (7, 8, 9)
PICO_TARDE = (17, 18, 19)


# ---------------------------------------------------------------- definiciones

def _top(serie: pd.Series, fraccion: float) -> set:
    n = max(1, int(round(len(serie) * fraccion)))
    return set(serie.sort_values(ascending=False).index[:n].astype(str))


def volumen_train(train: pd.DataFrame) -> pd.Series:
    """Salidas totales por estación en el periodo de entrenamiento."""
    vol = train.groupby("estacion", observed=True)[M.TARGET].sum()
    vol.index = vol.index.astype(str)
    return vol


def criticas_por_volumen(vol: pd.Series, fraccion: float) -> set:
    return _top(vol, fraccion)


def flujo_neto_laboral(viajes: pd.DataFrame, estaciones) -> pd.DataFrame:
    """Llegadas menos salidas, por día laboral, en el pico de la mañana y en el de la tarde.

    `viajes` necesita estacion_origen, estacion_destino, origen_dt y destino_dt (solo viajes válidos
    del periodo de entrenamiento). Negativo = la estación pierde bicicletas en ese pico.
    """
    laboral_o = viajes["origen_dt"].dt.dayofweek < 5
    laboral_d = viajes["destino_dt"].dt.dayofweek < 5
    n_dias = viajes.loc[laboral_o, "origen_dt"].dt.normalize().nunique()

    salio = viajes["origen_dt"].dt.hour
    llego = viajes["destino_dt"].dt.hour
    out = pd.DataFrame(index=pd.Index(sorted(set(map(str, estaciones))), name="estacion"))
    for nombre, horas in (("neto_manana", PICO_MANANA), ("neto_tarde", PICO_TARDE)):
        sal = viajes[laboral_o & salio.isin(horas)].groupby("estacion_origen").size()
        lle = viajes[laboral_d & llego.isin(horas)].groupby("estacion_destino").size()
        sal.index, lle.index = sal.index.astype(str), lle.index.astype(str)
        neto = lle.sub(sal, fill_value=0)
        out[nombre] = neto.reindex(out.index).fillna(0) / n_dias
    return out


def criticas_por_deficit(neto: pd.DataFrame, fraccion: float):
    """Estaciones con mayor pérdida diaria de bicicletas en alguno de los dos picos."""
    deficit = -neto[["neto_manana", "neto_tarde"]].min(axis=1)
    return _top(deficit, fraccion), deficit


# ---------------------------------------------------------------- métricas por grupo

def resumen(real, pred) -> dict:
    real = np.asarray(real, dtype=float)
    pred = np.asarray(pred, dtype=float)
    err = pred - real
    dem = float(real.mean())
    return {
        "filas": int(len(real)),
        "demanda_media": dem,
        "RMSE": float(np.sqrt(np.mean(err ** 2))),
        "MAE": float(np.mean(np.abs(err))),
        "Sesgo": float(err.mean()),
        "Sesgo_%_de_demanda": 100 * float(err.mean()) / dem if dem else np.nan,
    }


def tabla_grupos(test: pd.DataFrame, definiciones: dict, modelos: dict) -> pd.DataFrame:
    """Métricas de cada modelo en las estaciones críticas y en el resto, para cada definición.

    `test` debe tener las columnas `_est` (id de estación como texto), `salidas` y una columna de
    predicción por modelo. `definiciones`: {nombre: set de estaciones}. `modelos`: {nombre: columna}.
    Incluye qué parte del error cuadrático total del modelo cae en cada grupo.
    """
    filas = []
    y = test[M.TARGET].to_numpy(dtype=float)
    for nombre_def, criticas in definiciones.items():
        mask = test["_est"].isin(criticas).to_numpy()
        for nombre_mod, col in modelos.items():
            p = test[col].to_numpy(dtype=float)
            sse_total = float(np.sum((p - y) ** 2))
            for grupo, m in (("críticas", mask), ("resto", ~mask)):
                fila = resumen(y[m], p[m])
                fila["% del error cuadrático total"] = 100 * float(np.sum((p[m] - y[m]) ** 2)) / sse_total
                filas.append({"definición": nombre_def, "grupo": grupo, "modelo": nombre_mod,
                              "estaciones": int(test.loc[m, "_est"].nunique()), **fila})
    return pd.DataFrame(filas)


def sesgo_por_decil(test: pd.DataFrame, vol: pd.Series, modelos: dict) -> pd.DataFrame:
    """Sesgo de cada modelo por decil de volumen de la estación (1 = menos salidas, 10 = más)."""
    decil = pd.qcut(vol.rank(method="first"), 10, labels=range(1, 11)).astype(int)
    d = test["_est"].map(decil)
    y = test[M.TARGET].to_numpy(dtype=float)
    filas = []
    for k in range(1, 11):
        m = (d == k).to_numpy()
        for nombre, col in modelos.items():
            r = resumen(y[m], test.loc[m, col].to_numpy())
            filas.append({"decil": k, "modelo": nombre, **r})
    return pd.DataFrame(filas)


def sesgo_por_hora(test: pd.DataFrame, criticas: set, modelo_col: str, relativo: bool = False) -> pd.DataFrame:
    """Sesgo medio por hora del día, en las críticas y en el resto.

    Con `relativo=True` el sesgo se expresa como % de la demanda media de esa hora y ese grupo.
    """
    real = test[M.TARGET].to_numpy(dtype=float)
    err = test[modelo_col].to_numpy(dtype=float) - real
    mask = test["_est"].isin(criticas).to_numpy()
    df = pd.DataFrame({"hora": test["hora"].to_numpy(), "err": err, "real": real, "critica": mask})
    g = df.groupby(["hora", "critica"])
    t = g["err"].mean().unstack("critica")
    if relativo:
        t = 100 * t / g["real"].mean().unstack("critica")
    t.columns = ["resto" if not c else "críticas" for c in t.columns]
    return t


# ---------------------------------------------------------------- modelo específico

def entrenar_especifico(train: pd.DataFrame, test: pd.DataFrame, criticas: set, params: dict):
    """XGBoost entrenado solo con las filas de las estaciones críticas (mismos hiperparámetros).

    Regresa (predicciones sobre las filas críticas de `test`, índices de esas filas, número de árboles).
    `test` debe tener índice 0..n-1 y la columna `_est`.
    """
    tr = train[train["estacion"].astype(str).isin(criticas)]
    n_arboles = M.elegir_arboles(tr, params)
    modelo = M.entrenar_xgb(tr, params, n_arboles)
    idx = test.index[test["_est"].isin(criticas)]
    pred = np.clip(modelo.predict(test.loc[idx, M.FEATURES]), 0, None)
    return pred, idx, n_arboles, len(tr)
