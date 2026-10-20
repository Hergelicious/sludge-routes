"""Ranking robustness: Monte Carlo over parameter ranges, and one-at-a-time swings of the gap between two routes."""
import numpy as np

from .params import P, central
from .routes import ROUTES, route


def draws(n, seed=1):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        d = {}
        for k, (c, lo, hi, _) in P.items():
            d[k] = c if hi == lo else rng.triangular(lo, min(max(c, lo), hi), hi)
        out.append(d)
    return out


def monte_carlo(ef, n=2000, routes=ROUTES):
    ps = draws(n)
    ghg = np.array([[route(r, ef, p).total() for r in routes] for p in ps])
    best = np.bincount(ghg.argmin(axis=1), minlength=len(routes)) / n
    return {r: (np.percentile(ghg[:, i], 5), np.median(ghg[:, i]), np.percentile(ghg[:, i], 95), best[i])
            for i, r in enumerate(routes)}


def swing(a, b, ef):
    """Change in GHG(a) - GHG(b) when each parameter goes to its low and high value."""
    c = central()
    base = route(a, ef, c).total() - route(b, ef, c).total()
    rows = []
    for k, (_, lo, hi, _) in P.items():
        v = []
        for x in (lo, hi):
            q = dict(c, **{k: x})
            v.append(route(a, ef, q).total() - route(b, ef, q).total())
        rows.append((k, v[0], v[1], max(abs(v[0] - base), abs(v[1] - base))))
    rows.sort(key=lambda t: -t[3])
    return base, rows


def plant_monte_carlo(n=300, cod_mg_l=278.0, digesting=True, bound="mid", seed=1):
    """Distribution of the total saving across the plants (Mt CO2e/yr) and of the winning route, over parameter draws."""
    from .plants import plant_totals
    out = []
    for p in draws(n, seed):
        df = plant_totals(cod_mg_l, digesting, bound, p)
        w = df.groupby("best")["ds_kt_yr"].sum() / df["ds_kt_yr"].sum()
        out.append(dict(saving=df["saving_kt"].sum() / 1e3, step_lf=df["step_lf_kt"].sum() / 1e3,
                        step_ad=df["step_ad_kt"].sum() / 1e3, step_best=df["step_best_kt"].sum() / 1e3, **{f"win:{k}": v for k, v in w.items()}))
    import pandas as pd
    return pd.DataFrame(out).fillna(0.0)


def structural_attribution(n=1000, seed=3):
    """Share of the variance of the total saving across the plants explained by each unreported plant condition and by the
    engineering parameters (first-order indices). Conditions: theta = where sludge goes in countries without a
    reported mix (0 all land, 1 all landfill; also moves 'other' in reported mixes), d = share of plants already
    digesting, c = influent COD (log-uniform 278-600 mg/L; the saving scales with sludge mass, so with COD).
    The saving is linear in theta and d, so four plant runs per parameter draw give it for any theta and d."""
    import pandas as pd
    from .plants import plant_totals
    rng = np.random.default_rng(seed)
    rows = []
    for k, p in enumerate(draws(n, seed)):
        cor = {(b, dg): plant_totals(278.0, dg, b, p)["saving_kt"].sum() / 1e3 for b in ("low", "high") for dg in (True, False)}
        th, d, c = rng.uniform(), rng.uniform(), np.exp(rng.uniform(np.log(278.0), np.log(600.0))) / 278.0
        lo = d * cor[("low", True)] + (1 - d) * cor[("low", False)]
        hi = d * cor[("high", True)] + (1 - d) * cor[("high", False)]
        y = c * ((1 - th) * lo + th * hi)
        mean_corners = np.mean(list(cor.values()))
        rows.append(dict(k=k, theta=th, d=d, c=c, y=y, e_given_params=mean_corners))
    df = pd.DataFrame(rows)
    ec = np.mean(np.exp(np.random.default_rng(0).uniform(np.log(278), np.log(600), 200000)) / 278.0)
    var = df.y.var()
    out = {}
    for f in ("theta", "d", "c"):
        bins = pd.qcut(df[f], 20, labels=False)
        out[f] = df.groupby(bins).y.mean().var() / var
    out["parameters"] = (df.e_given_params * ec).var() / var
    out["interactions"] = 1 - sum(out.values())
    return out, df
