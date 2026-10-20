"""Route comparison at the screened HydroWASTE plants treating >= 100,000 m3/d outside high-income economies (data.py).

Primary sludge per plant: captured COD = 0.59 x flow x influent COD (278 or 600 mg/L),
converted to raw dry solids with the COD/VS and VS/TS ratios of params.py. Plants with secondary treatment also
produce waste activated sludge from the remaining COD (params.mix). Digester status is not reported, so both bounds are
run (all plants digest / none do). The counterfactual is each country's reported disposal mix; where none is
reported, it is bounded by all-to-land and all-to-dump-landfill.
"""
import numpy as np
import pandas as pd

from . import data as WP
from .data import DISPOSAL, LEAN, load_plants

from .params import central
from .routes import route

# DISPOSAL (data/disposal.csv): reported shares to land, landfill, incineration and other uses; "other" (building
# materials, undefined destinations) is split evenly between land and landfill and bounded. LEAN (data/countries.csv):
# no shares reported but qualitative evidence points one way; used for the central case only. India: cGanga/NMCG
# 2022 states current practice is not quantified; Indonesia: none found.

CANDIDATES = ["AD-CHP land", "AD-biomethane land", "AD-CHP solar-dry incin",
              "AD-CHP thermal-dry incin", "AD-CHP solar-dry pyro", "AD-CHP thermal-dry pyro",
              "raw solar-dry pyro", "raw thermal-dry pyro", "raw incin"]


def raw_ds(flow_m3d, cod_mg_l, p):
    """Raw primary-sludge dry solids, t DS/d."""
    cpv, vsf = p.get("prim_cod_per_vs", p["cod_per_vs"]), p.get("prim_vs_frac", p["vs_frac_raw"])   # raw keys if unmixed
    return WP.CAPTURE * flow_m3d * cod_mg_l / 1000.0 / (cpv * vsf) / 1000.0


def was_ds(flow_m3d, cod_mg_l, p):
    """Waste activated sludge dry solids, t DS/d, from the COD that passes primary settling."""
    return (1.0 - WP.CAPTURE) * flow_m3d * cod_mg_l / 1e6 * p["was_yield_per_cod"]


def sludge_ds(df, cod_mg_l, p):
    """t DS/d per plant: primary sludge, plus WAS where the plant has secondary treatment."""
    sec = (df["treatment_level"] != "Primary").values
    return raw_ds(df["flow_m3d"].values, cod_mg_l, p) + sec * was_ds(df["flow_m3d"].values, cod_mg_l, p)


def current_ghg(iso, ef, digesting, p, bound="mid", alt=None, no_landfill=False):
    """t CO2e per t DS for today's practice. bound: 'land' / 'landfill' for countries without data; 'mid' splits
    'other' evenly; 'low'/'high' send 'other' to land/landfill. no_landfill: the same practice with every tonne
    that goes to landfill sent to land instead (digestion status and incineration unchanged)."""
    pre = "AD-CHP " if digesting else "raw "
    g = {k: route(pre + k, ef, p).total() for k in ("land", "landfill")}
    if no_landfill:              # diverted to farmland, with the extra haul of interventions.state_ghg
        haul = p["extra_haul_km"] * p["truck_kgco2_per_tkm"] / p["cake_ds"] / 1000.0
        g["landfill"] = g["land"] + haul
    g["incin"] = route(("AD-CHP thermal-dry incin" if digesting else "raw incin"), ef, p).total()
    d = DISPOSAL.get(alt or iso)
    if isinstance(bound, float):                      # numeric: the landfilled share of unreported sludge
        split = (1.0 - bound) * g["land"] + bound * g["landfill"]
    else:
        split = 0.5 * (g["land"] + g["landfill"])
    if d is None:
        if bound == "mid" and iso in LEAN:            # qualitative evidence only: central case follows it
            return g[LEAN[iso]]
        return g["landfill"] if bound in ("landfill", "high") else g["land"] if bound in ("land", "low") else split
    other = {"low": g["land"], "high": g["landfill"]}.get(bound, split)
    return d["land"] * g["land"] + d["landfill"] * g["landfill"] + d["incin"] * g["incin"] + d["other"] * other


def country_table(ef_override=None, p=None, digesting=True, bound="mid", candidates=CANDIDATES, alt_map=None):
    p = central() if p is None else p
    rows = []
    for iso, (name, ef, diesel, _) in WP.COUNTRY_INPUTS.items():
        ef = ef if ef_override is None else ef_override
        alt = (alt_map or {}).get(iso)
        cur = current_ghg(iso, ef, digesting, p, bound, alt=alt)
        nolf = current_ghg(iso, ef, digesting, p, bound, alt=alt, no_landfill=True)     # stop landfilling
        nolf_ad = current_ghg(iso, ef, True, p, bound, alt=alt, no_landfill=True)       # ... and digest
        res = {n: route(n, ef, p).total() for n in candidates}
        best = min(res, key=res.get)
        rows.append(dict(iso=iso, country=name, grid_ef=ef, disposal_data=iso in DISPOSAL, current=cur,
                         no_landfill=nolf, no_landfill_ad=nolf_ad,
                         best=best, best_ghg=res[best], saving=cur - res[best],
                         saving_vs_current_land_route=cur - res.get("AD-CHP land", np.nan), **res))
    return pd.DataFrame(rows)


def plant_totals(cod_mg_l=278.0, digesting=True, bound="mid", p=None, ef_override=None, solar_lat=35.0, alt_map=None,
                 documented=False):
    """Annual t CO2e saved if every plant moves from today's practice to its lowest-emission route.
    Solar drying is offered only to plants within +-solar_lat degrees of the equator. Plants with
    secondary treatment send mixed primary + waste activated sludge; primary-only plants send primary sludge.
    documented=True: the documented-practice scenario, in which every plant with a documented flow, digester status
    or sludge destination (data/plant_screening.csv) uses those instead of the inventory flow and the country-level
    assumptions; the others are unchanged."""
    p = central() if p is None else p
    cols = ["current", "no_landfill", "no_landfill_ad", "best", "best_ghg", "saving"]
    df = load_plants()
    doc = WP.documented().reindex(df.waste_id) if documented else None
    if documented:
        f = doc["documented_flow_m3d"].values
        df["flow_m3d"] = np.where(np.isnan(f), df["flow_m3d"].values, f)
    df["ds_t_d"] = sludge_ds(df, cod_mg_l, p)
    df["ds_kt_yr"] = df["ds_t_d"] * 365 / 1000.0
    is_warm = pd.Series((df["lat"].abs() <= solar_lat).values, index=df.index)
    is_sec = pd.Series((df["treatment_level"] != "Primary").values, index=df.index)
    parts = {}
    for sec in (1, 0):
        q = dict(p, with_secondary=sec)
        for warm in (True, False):
            cand = CANDIDATES if warm else [c for c in CANDIDATES if "solar" not in c]
            t = country_table(ef_override, q, digesting, bound, alt_map=alt_map, candidates=cand).set_index("iso")
            parts[(sec, warm)] = df.join(t[cols], on="iso")
    out = parts[(1, True)].copy()
    for (sec, warm), part in parts.items():
        m = (is_sec == bool(sec)) & (is_warm == warm)
        out.loc[m, cols] = part.loc[m, cols]
    df = out
    if documented:                                        # per-plant digester status and destination where documented
        for i, (wid, dg, fate) in enumerate(zip(df.waste_id, doc["digesting"].values, doc["fate"].values)):
            if np.isnan(dg) and not isinstance(fate, str):
                continue
            iso, sec, warm = df.iso.iat[i], bool(is_sec.iat[i]), bool(is_warm.iat[i])
            cand = CANDIDATES if warm else [c for c in CANDIDATES if "solar" not in c]
            t = country_table(ef_override, dict(p, with_secondary=int(sec)), digesting if np.isnan(dg) else bool(dg), bound,
                              candidates=cand, alt_map={iso: f"doc_{fate}"} if isinstance(fate, str) else alt_map).set_index("iso")
            df.loc[df.index[i], cols] = t.loc[iso, cols].values
    df["current_kt"] = df["ds_kt_yr"] * df["current"]
    df["best_kt"] = df["ds_kt_yr"] * df["best_ghg"]
    df["saving_kt"] = df["ds_kt_yr"] * df["saving"]
    # the saving as a chain of three changes, each measured from the one before
    df["step_lf_kt"] = df["ds_kt_yr"] * (df["current"] - df["no_landfill"])             # 1 stop landfilling
    df["step_ad_kt"] = df["ds_kt_yr"] * (df["no_landfill"] - df["no_landfill_ad"])      # 2 digest where not yet
    df["step_best_kt"] = df["ds_kt_yr"] * (df["no_landfill_ad"] - df["best_ghg"])       # 3 move to the best route
    return df


def plant_economics(cod_mg_l=278.0, p=None, route_name="AD-CHP solar-dry pyro", base="AD-CHP land", solar_lat=35.0):
    """Break-even carbon price per plant for adding pyrolysis after digestion, with the plant's own scale, its
    country's grid, electricity and diesel prices. Plants beyond solar_lat use thermal drying."""
    from .econ import break_even_carbon, pyro_cost_per_t_feed
    from .data import ELEC_PRICE
    from .params import mix
    p = central() if p is None else p
    df = load_plants()
    df["ds_kt_yr"] = sludge_ds(df, cod_mg_l, p) * 365 / 1000.0
    rows = []
    for r in df.itertuples(index=False):
        rn = route_name if abs(r.lat) <= solar_lat else route_name.replace("solar", "thermal")
        m = mix(dict(p, with_secondary=int(r.treatment_level != "Primary")))
        cost = pyro_cost_per_t_feed(r.ds_kt_yr * (1.0 - m["vs_destruction"] * m["vs_frac_raw"]), p)
        name, ef, diesel, _ = WP.COUNTRY_INPUTS[r.iso]
        q = dict(m, elec_price_usd_kwh=ELEC_PRICE[r.iso], diesel_usd_l=diesel)
        b = break_even_carbon(rn, base, ef, q, cost)
        rows.append(dict(waste_id=r.waste_id, iso=r.iso, ds_kt_yr=r.ds_kt_yr, route=rn, cost_usd_t_feed=cost,
                         be_market=b["market"], be_social=b["social"]))
    return pd.DataFrame(rows)
