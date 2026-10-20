"""Which intervention first? Four interventions on top of each country's current practice, in every combination.

  V  divert: sludge now landfilled goes to farmland instead (extra haul counted)
  G  capture: gas collection retrofitted at the landfills that still receive sludge
  A  digest: anaerobic digestion with CHP where the plant does not digest
  P  pyrolysis: all sludge dried (solar within 35 deg, thermal beyond) and pyrolysed, after digestion if present

V and G compete for the same landfilled tonnes; P replaces every destination, so V and G add nothing once P is in.
Emissions are t CO2e per t raw DS; savings are against current practice. Shares of the total saving are split
between interventions by Shapley values (the average extra saving of each intervention over all orders).
"""
from itertools import combinations
from math import factorial

from .plants import DISPOSAL, LEAN
from .routes import route

IV = ("V", "G", "A", "P")
STATES = [frozenset(c) for n in range(5) for c in combinations(IV, n)]


def fate(iso, bound="mid", alt=None):
    """Shares of sludge to land, landfill and incineration today ('other' split as in plants.current_ghg)."""
    d = DISPOSAL.get(alt or iso)
    if d is None:
        if bound == "mid" and iso in LEAN:
            return {"land": 0.0, "landfill": 0.0, "incin": 0.0, LEAN[iso]: 1.0}
        lf = bound if isinstance(bound, float) else {"low": 0.0, "land": 0.0, "high": 1.0, "landfill": 1.0}.get(bound, 0.5)
        return {"land": 1 - lf, "landfill": lf, "incin": 0.0}
    o = bound if isinstance(bound, float) else {"low": 0.0, "high": 1.0}.get(bound, 0.5)
    return {"land": d["land"] + (1 - o) * d["other"], "landfill": d["landfill"] + o * d["other"], "incin": d["incin"]}


def state_ghg(state, iso, ef, p, digesting, warm, bound="mid", alt=None):
    """t CO2e per t raw DS with the interventions in `state` applied to current practice."""
    dig = digesting or "A" in state
    pre = "AD-CHP " if dig else "raw "
    if "P" in state:
        opts = [pre + "thermal-dry pyro"] + ([pre + "solar-dry pyro"] if warm else [])
        return min(route(o, ef, p).total() for o in opts)
    f = fate(iso, bound, alt)
    land = route(pre + "land", ef, p).total()
    q = dict(p, lfg_capture=max(p["lfg_capture"], p["lfg_capture_upgrade"])) if "G" in state else p   # a retrofit never lowers capture
    landfill = route(pre + "landfill", ef, q).total()
    incin = route("AD-CHP thermal-dry incin" if dig else "raw incin", ef, p).total()
    if "V" in state:
        wet_t = 1.0 / p["cake_ds"]
        haul = wet_t * p["extra_haul_km"] * p["truck_kgco2_per_tkm"] / 1000.0
        lam = p.get("divert_share", 1.0)          # share of landfilled sludge farmland can take
        landfill = lam * (land + haul) + (1 - lam) * landfill
    return f["land"] * land + f["landfill"] * landfill + f["incin"] * incin


def table(iso, ef, p, digesting, warm, bound="mid", alt=None):
    """Emissions for all 16 states, savings alone / last / Shapley, and the best state."""
    e = {s: state_ghg(s, iso, ef, p, digesting, warm, bound, alt) for s in STATES}
    base = e[frozenset()]
    n = len(IV)
    out = {"current": base, "best_state": min(e, key=e.get)}
    out["best"] = e[out["best_state"]]
    for i in IV:
        alone = base - e[frozenset([i])]
        last = e[frozenset(IV) - {i}] - e[frozenset(IV)]
        sh = 0.0
        for s in STATES:
            if i in s:
                continue
            w = factorial(len(s)) * factorial(n - len(s) - 1) / factorial(n)
            sh += w * (e[s] - e[s | {i}])
        out[f"alone_{i}"], out[f"last_{i}"], out[f"shapley_{i}"] = alone, last, sh
    out["states"] = {"".join(sorted(s, key=IV.index)) or "-": v for s, v in e.items()}
    return out


def plant_table(cod_mg_l=278.0, digesting=True, bound="mid", p=None, solar_lat=35.0, alt_map=None, ef_override=None):
    """Per plant: t DS/yr and, in kt CO2e/yr, current emissions, each intervention's saving (alone, last, Shapley)
    and the saving of every combination of interventions."""
    import pandas as pd
    from . import data as WP
    from .data import load_plants
    from .params import central
    from .plants import sludge_ds
    p = central() if p is None else p
    df = load_plants()
    df["ds_kt_yr"] = sludge_ds(df, cod_mg_l, p) * 365 / 1000.0
    cache, rows = {}, []
    for r in df.itertuples(index=False):
        sec = int(r.treatment_level != "Primary")
        warm = abs(r.lat) <= solar_lat
        key = (r.iso, sec, warm)
        if key not in cache:
            ef = WP.COUNTRY_INPUTS[r.iso][1] if ef_override is None else ef_override
            cache[key] = table(r.iso, ef, dict(p, with_secondary=sec), digesting, warm, bound, (alt_map or {}).get(r.iso))
        t = cache[key]
        row = dict(waste_id=r.waste_id, iso=r.iso, country=r.country, lat=r.lat, lon=r.lon, ds_kt_yr=r.ds_kt_yr,
                   best_state="".join(sorted(t["best_state"], key=IV.index)), current_kt=t["current"] * r.ds_kt_yr)
        for k, v in t.items():
            if k.startswith(("alone_", "last_", "shapley_")):
                row[k + "_kt"] = v * r.ds_kt_yr
        for s, v in t["states"].items():
            row[f"save_{s}_kt"] = (t["current"] - v) * r.ds_kt_yr
        rows.append(row)
    return pd.DataFrame(rows)


def _value(name, ef, p):
    """Market value of a route's products, US$ per t raw DS, no carbon revenue."""
    from .econ import value
    return value(name, ef, p, carbon=0.0)[0]


def state_cost_parts(state, iso, ef, p, digesting, warm, bound="mid", alt=None):
    """Net cost of a state relative to current practice, US$ per t raw DS, except the pyrolysis plant itself
    (returned separately as the feed fraction, since its cost depends on plant size). Positive = costs more.
    Digestion is not costed (no comparable cost data for these countries); captured landfill gas is costed per t
    CO2e avoided; diversion pays extra haul and spreading and saves the landfill fee."""
    from .params import mix
    m = mix(p)
    dig = digesting or "A" in state
    pre = "AD-CHP " if dig else "raw "
    f = fate(iso, bound, alt)
    cur_pre = "AD-CHP " if digesting else "raw "
    cur_inc = "AD-CHP thermal-dry incin" if digesting else "raw incin"
    v_cur = (f["land"] * _value(cur_pre + "land", ef, p) + f["landfill"] * _value(cur_pre + "landfill", ef, p)
             + f["incin"] * _value(cur_inc, ef, p))
    wet_t = 1.0 / p["cake_ds"]
    fee = f["landfill"] * wet_t * p["tip_usd_t"]                      # landfill fee paid today
    if "P" in state:
        opts = [pre + "thermal-dry pyro"] + ([pre + "solar-dry pyro"] if warm else [])
        best = min(opts, key=lambda o: route(o, ef, p).total())
        feed = 1.0 - (m["vs_destruction"] * m["vs_frac_raw"] if dig else 0.0)
        return -(_value(best, ef, p) - v_cur) - fee, feed
    inc = "AD-CHP thermal-dry incin" if dig else "raw incin"
    v_new = f["land"] * _value(pre + "land", ef, p) + f["incin"] * _value(inc, ef, p)
    cost = 0.0
    lam = p.get("divert_share", 1.0) if "V" in state else 0.0
    if lam:
        v_new += lam * f["landfill"] * _value(pre + "land", ef, p)
        cost += lam * (f["landfill"] * wet_t * (p["extra_haul_km"] * p["haul_usd_tkm"] + p["spread_usd_t"]) - fee)
    if lam < 1.0:
        v_new += (1 - lam) * f["landfill"] * _value(pre + "landfill", ef, p)
        if "G" in state:
            avoided = state_ghg(state - {"G"}, iso, ef, p, digesting, warm, bound, alt) - \
                state_ghg(state, iso, ef, p, digesting, warm, bound, alt)
            cost += p["lfg_usd_tco2e"] * avoided
    return cost - (v_new - v_cur), 0.0


def plant_choice(carbon_values=(0, 50, 100, 150, 320), cod_mg_l=278.0, digesting=True, bound="mid", p=None,
                 solar_lat=35.0, allowed=None, land_ok=True, documented=False, divert_if_digested=False):
    """Per plant and carbon value: the combination of interventions that maximises net benefit (carbon value x
    t CO2e avoided - net cost), its saving and cost; plus each intervention's cost per t CO2e when applied alone.
    allowed: subset of interventions that may be used (e.g. {'V','G'} for no new treatment units).
    land_ok=False: farmland cannot take sludge (no diversion; land application and pyrolysis char still allowed
    only through pyrolysis).
    documented=True: plants with a documented digester status or sludge destination (data/plant_screening.csv) use
    it instead of the central assumption and the country mix.
    divert_if_digested=True: farmland takes only digested sludge, so diversion is not available where the plant
    does not digest (a compliance-aware variant)."""
    import numpy as np
    import pandas as pd
    from . import data as WP
    from .data import load_plants
    from .econ import pyro_cost_per_t_feed
    from .data import ELEC_PRICE
    from .params import central
    from .plants import sludge_ds
    p = central() if p is None else p
    df = load_plants()
    df["ds_kt_yr"] = sludge_ds(df, cod_mg_l, p) * 365 / 1000.0
    allowed = {"V", "G", "P"} if allowed is None else set(allowed)    # digestion is not costed: kept out of the choice
    states_all = [s for s in STATES if s <= allowed and (land_ok or "V" not in s)]
    doc = WP.documented().reindex(df.waste_id) if documented else None
    cache, rows = {}, []
    for idx, r in enumerate(df.itertuples(index=False)):
        sec = int(r.treatment_level != "Primary")
        warm = abs(r.lat) <= solar_lat
        dig, alt = digesting, None
        if documented:
            dg, ft = doc["digesting"].iat[idx], doc["fate"].iat[idx]
            dig = digesting if np.isnan(dg) else bool(dg)
            alt = f"doc_{ft}" if isinstance(ft, str) else None
        states = [s for s in states_all if not (divert_if_digested and not dig and "V" in s)]
        key = (r.iso, sec, warm, dig, alt, len(states))
        name, ef, diesel, _ = WP.COUNTRY_INPUTS[r.iso]
        q = dict(p, with_secondary=sec, elec_price_usd_kwh=ELEC_PRICE[r.iso], diesel_usd_l=diesel)
        if key not in cache:
            e = {s: state_ghg(s, r.iso, ef, q, dig, warm, bound, alt) for s in states}
            c = {s: state_cost_parts(s, r.iso, ef, q, dig, warm, bound, alt) for s in states}
            cache[key] = (e, c)
        e, c = cache[key]
        base = e[frozenset()]
        out = dict(waste_id=r.waste_id, iso=r.iso, ds_kt_yr=r.ds_kt_yr, lat=r.lat, lon=r.lon)
        cost = {}
        for s in states:
            other, feed = c[s]
            pyro = pyro_cost_per_t_feed(r.ds_kt_yr * feed, p) * feed if feed else 0.0
            cost[s] = other + pyro                                              # US$ per t DS
        for i in IV:
            s = frozenset([i])
            if s in e and base - e[s] > 1e-6:
                out[f"usd_per_t_{i}"] = cost[s] / (base - e[s])
        sv, sp = frozenset("V"), frozenset("P")
        if sv in e and sp in e and e[sv] - e[sp] > 1e-6:
            out["usd_per_t_P_after_V"] = (cost[sp] - cost[sv]) / (e[sv] - e[sp])
        sg = frozenset("G")
        if sg in e and sp in e and e[sg] - e[sp] > 1e-6:
            out["usd_per_t_P_after_G"] = (cost[sp] - cost[sg]) / (e[sg] - e[sp])
        for cv in carbon_values:
            best = max(states, key=lambda s: cv * (base - e[s]) - cost[s])
            out[f"state_{cv}"] = "".join(sorted(best, key=IV.index)) or "-"
            out[f"save_{cv}_kt"] = (base - e[best]) * r.ds_kt_yr
            out[f"cost_{cv}_musd"] = cost[best] * r.ds_kt_yr / 1000.0
        rows.append(out)
    return pd.DataFrame(rows)


def grid_tipping(p=None, warm=True, secondary=True):
    """Grid carbon intensities (t CO2/MWh) at which (a) digestion + CHP + land application stops being a net
    sink, and (b) pyrolysis of raw sludge overtakes pyrolysis after digestion, i.e. the digester stops paying
    for itself on climate grounds. Found by bisection on the grid factor."""
    from .params import central
    p = dict(central() if p is None else p, with_secondary=int(secondary))
    dig = ["AD-CHP thermal-dry pyro"] + (["AD-CHP solar-dry pyro"] if warm else [])
    raw = ["raw thermal-dry pyro"] + (["raw solar-dry pyro"] if warm else [])
    f_a = lambda e: route("AD-CHP land", e, p).total()
    f_b = lambda e: min(route(o, e, p).total() for o in dig) - min(route(o, e, p).total() for o in raw)

    def root(f, lo=0.0, hi=1.5):
        if f(lo) * f(hi) > 0:
            return float("nan")
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(lo) * f(mid) > 0 else (lo, mid)
        return (lo + hi) / 2
    return {"current_neutral": root(f_a), "digester_pays": root(f_b)}
