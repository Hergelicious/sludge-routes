"""Value of each route per t raw DS (US$), on two lenses.

market: what the route can sell or save - electricity, diesel displaced, fertiliser replaced, drying gas bought,
        and biochar carbon removal sold as credits.
social: market value plus every tonne of net GHG priced at the same carbon price.
The difference from current practice is the extra cost per t DS a route could carry and still break even
("allowable cost").
"""
from .params import central, mix
from .routes import ROUTES, route

N_IN_UREA = 0.46
P_IN_TSP = 0.46 * 62 / 142          # P2O5 46%
MMBTU_PER_KWH = 0.003412


def value(name, ef, p=None, carbon=None):
    p = mix(central() if p is None else p)
    carbon = p["cdr_usd_t"] if carbon is None else carbon
    r = route(name, ef, p)
    v = {}
    v["electricity"] = r.elec_mwh * 1000.0 * p["elec_price_usd_kwh"]
    if "diesel displaced" in r.ghg:
        litres = -r.ghg["diesel displaced"] * 1000.0 / p["diesel_kgco2e_per_mj"] / p["diesel_mj_per_l"]
        v["diesel"] = litres * p["diesel_usd_l"]
    v["fertiliser"] = r.n_avail_kg * p["urea_usd_t"] / 1000.0 / N_IN_UREA + r.p_avail_kg * p["tsp_usd_t"] / 1000.0 / P_IN_TSP
    if "drying fuel" in r.ghg:
        kwh = r.ghg["drying fuel"] * 1000.0 / p["fuel_kgco2_per_kwh"]
        v["drying gas"] = -kwh * MMBTU_PER_KWH * p["gas_usd_mmbtu"]
    if r.oil_t:
        v["bio-oil"] = r.oil_t * p["oil_price_usd_t"]
    if "biochar storage" in r.ghg:
        v["CDR credits"] = -r.ghg["biochar storage"] * carbon
    market = sum(v.values())
    social = market - (r.total() - r.ghg.get("biochar storage", 0.0)) * carbon
    return market, social, v, r


def table(ef, base="AD-CHP land", p=None, carbon=None):
    m0, s0, _, _ = value(base, ef, p, carbon)
    out = []
    for n in ROUTES:
        m, s, v, r = value(n, ef, p, carbon)
        out.append((n, m, s, m - m0, s - s0, v, r))
    return out


def break_even_carbon(route_name="AD-CHP solar-dry pyro", base="AD-CHP land", ef=0.563, p=None, cost_usd_t_feed=None):
    """Carbon price (US$/t CO2e) at which the route's extra value over `base` covers the pyrolysis plant's capital
    and labour cost, on the market lens (only removals sold) and the social lens (all GHG priced)."""
    p = mix(central() if p is None else p)
    vs = p["vs_frac_raw"]
    feed = 1.0 - (p["vs_destruction"] * vs if route_name.startswith("AD") else 0.0)
    cost = (p["pyro_cost_usd_t_feed"] if cost_usd_t_feed is None else cost_usd_t_feed) * feed
    out = {}
    for idx, lens in ((0, "market"), (1, "social")):
        v0 = value(route_name, ef, p, 0.0)[idx] - value(base, ef, p, 0.0)[idx]
        v1 = value(route_name, ef, p, 1.0)[idx] - value(base, ef, p, 1.0)[idx]
        slope = v1 - v0
        out[lens] = max((cost - v0) / slope, 0.0) if slope > 0 else float("inf")
    return out


from .data import ELEC_PRICE  # business electricity, US$/kWh (data/countries.csv)


def pyro_cost_per_t_feed(feed_kt_yr, p=None):
    """Capital + labour cost (US$/t dry feed) scaled from the Zimmer et al. reference plant; capital scales with
    capacity^scale_exp, labour per tonne held constant. Capacity clamped to 2-50 kt DS/yr (modular plants)."""
    p = central() if p is None else p
    q = min(max(feed_kt_yr, 2.0), 50.0) / p["pyro_ref_kt_ds"]
    c = p["pyro_cost_usd_t_feed"]
    return c * (p["capex_mult"] * p["pyro_cap_share"] * q ** (p["scale_exp"] - 1.0) + (1.0 - p["pyro_cap_share"]))
