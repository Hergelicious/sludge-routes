"""Reproduce every result of the paper as CSV/JSON tables in results/.

    python run_all.py            # full run (about 10–15 min on one core)
    python run_all.py --quick    # same tables with 10x fewer Monte Carlo draws (about 1 min)

Central values use influent COD 278 mg/L, all plants digesting and each country's reported disposal mix
(bounded where none is reported). Grid factor for Gabal El-Asfar: Egypt, 0.563 t CO2/MWh.
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

from sludgeroutes import data as WP
from sludgeroutes.decisions import plant_voi
from sludgeroutes.interventions import grid_tipping, plant_choice, plant_table
from sludgeroutes.params import P, central, mix
from sludgeroutes.plants import plant_economics, plant_totals, raw_ds, was_ds
from sludgeroutes.data import population
from sludgeroutes.routes import ROUTES, gabal_ds_t_d, route
from sludgeroutes.uncertainty import draws, monte_carlo, plant_monte_carlo, structural_attribution, swing

EF_EGY = 0.563
GROUP = {"CH4 losses": "methane", "open-drying CH4": "methane", "landfill CH4": "methane",
         "land N2O": "nitrous_oxide", "incineration N2O": "nitrous_oxide", "stockpile N2O": "nitrous_oxide",
         "drying fuel": "drying_fuel", "electricity": "grid_electricity", "fertiliser offset": "products_displaced",
         "diesel displaced": "products_displaced", "fuel oil displaced": "products_displaced",
         "biochar storage": "biochar_storage"}


def wq(df, col, q):
    """Sludge-weighted quantile of a per-plant column."""
    s = df.dropna(subset=[col]).sort_values(col)
    cw = s.ds_kt_yr.cumsum() / s.ds_kt_yr.sum()
    return float(s[col].values[np.searchsorted(cw.values, q)])


def gabal(out, n):
    c = central()
    mc = monte_carlo(EF_EGY, n)
    rows = []
    for i, name in enumerate(ROUTES, 1):
        r = route(name, EF_EGY, c)
        g = dict.fromkeys(dict.fromkeys(GROUP.values()), 0.0)
        for k, v in r.ghg.items():
            g[GROUP[k]] += v
        lo, med, hi, best = mc[name]
        rows.append(dict(route=name, net_tco2e_per_t_ds=r.total(), p5=lo, p50=med, p95=hi, share_ranked_first=best,
                         p_available_kg=r.p_avail_kg, electricity_mwh=r.elec_mwh, **g))
    pd.DataFrame(rows).to_csv(f"{out}/gabal_routes.csv", index=False)
    efs = np.round(np.linspace(0, 0.9, 46), 3)
    pd.DataFrame([dict(grid_ef=e, **{n: route(n, e, c).total() for n in ROUTES}) for e in efs]) \
        .to_csv(f"{out}/gabal_grid_sweep.csv", index=False)
    mcfs = np.round(np.linspace(0, 0.2, 41), 3)
    pd.DataFrame([dict(dry_mcf_dig=m, **{n: route(n, EF_EGY, dict(c, dry_mcf_dig=m)).total() for n in ROUTES})
                  for m in mcfs]).to_csv(f"{out}/gabal_open_drying_sweep.csv", index=False)


def decision_map(out):
    c = central()
    cands = [r for r in ROUTES if r not in ("raw landfill", "raw land", "AD-CHP landfill")]
    rows = []
    for e in np.round(np.linspace(0, 0.9, 121), 4):
        for m in np.round(np.linspace(0, np.sqrt(0.2), 121) ** 2, 6):
            p = dict(c, dry_mcf_dig=m, dry_mcf_raw=min(0.2, m * 2.5))
            v = {n: route(n, e, p).total() for n in cands}
            best = min(v, key=v.get)
            rows.append(dict(grid_ef=e, dry_mcf_dig=m, best=best, best_ghg=v[best], current=v["AD-CHP land"],
                             gain=v["AD-CHP land"] - v[best]))
    pd.DataFrame(rows).to_csv(f"{out}/decision_map.csv", index=False)


def plants(out, n_struct):
    df = plant_totals()
    df[["waste_id", "iso", "country", "lat", "lon", "flow_m3d", "treatment_level", "ds_kt_yr", "current", "best",
        "best_ghg", "saving", "saving_kt", "step_lf_kt", "step_ad_kt", "step_best_kt"]].to_csv(f"{out}/plants.csv", index=False)
    lo, hi = plant_totals(bound="low"), plant_totals(bound="high")
    g = df.groupby("iso").agg(country=("country", "first"), plants=("waste_id", "size"), ds_kt=("ds_kt_yr", "sum"),
                              saving_kt=("saving_kt", "sum"), step_divert_kt=("step_lf_kt", "sum"),
                              step_best_route_kt=("step_best_kt", "sum"))
    win = df.step_lf_kt > df.step_ad_kt + df.step_best_kt            # where sludge goes beats how it is treated
    g["plants_where_diversion_beats_treatment"] = win.groupby(df.iso).sum()
    g["sludge_share_where_diversion_beats_treatment"] = df.loc[win].groupby("iso")["ds_kt_yr"].sum().reindex(g.index).fillna(0) / g.ds_kt
    g["saving_low_kt"] = lo.groupby("iso")["saving_kt"].sum()
    g["saving_high_kt"] = hi.groupby("iso")["saving_kt"].sum()
    g.sort_values("saving_kt", ascending=False).to_csv(f"{out}/countries.csv")
    rows = []
    for cod in (278.0, 600.0):
        for dig in (True, False):
            for b in ("low", "mid", "high"):
                m = plant_monte_carlo(n_struct, cod, dig, b, seed=2)
                rows.append(dict(cod=cod, digesting=dig, disposal=b,
                                 central=plant_totals(cod, dig, b)["saving_kt"].sum() / 1e3,
                                 p5=m.saving.quantile(.05), p50=m.saving.median(), p95=m.saving.quantile(.95)))
    pd.DataFrame(rows).to_csv(f"{out}/structural_scenarios.csv", index=False)
    return df


def interventions(out, n_mc):
    cv = list(range(0, 410, 10))
    d = plant_choice(carbon_values=cv)
    d[["waste_id", "iso", "ds_kt_yr"] + [c for c in d if c.startswith("usd_per_t")]] \
        .to_csv(f"{out}/intervention_costs.csv", index=False)
    rows, mc = [], []
    cases = (("central", {}), ("no further land application", dict(land_ok=False)))
    for lab, kw in cases:
        dd = d if lab == "central" else plant_choice(carbon_values=cv, **kw)
        rows += [dict(case=lab, carbon=x, save_Mt=dd[f"save_{x}_kt"].sum() / 1e3, cost_musd=dd[f"cost_{x}_musd"].sum())
                 for x in cv]
    for k, p in enumerate(draws(n_mc, 7)):
        for lab, kw in cases:
            dd = plant_choice(carbon_values=cv, p=p, **kw)
            mc += [dict(case=lab, carbon=x, save_Mt=dd[f"save_{x}_kt"].sum() / 1e3) for x in cv]
    m = pd.DataFrame(mc).groupby(["case", "carbon"]).save_Mt.quantile([0.05, 0.5, 0.95]).unstack()
    m.columns = ["p5", "p50", "p95"]
    pd.DataFrame(rows).merge(m.reset_index(), on=["case", "carbon"]).to_csv(f"{out}/cost_effective_potential.csv", index=False)
    c = central()
    lc = []
    for lam in (0.0, 0.25, 0.5, 0.75, 1.0):
        pc = plant_choice(carbon_values=(0, 50, 100, 150, 320), p=dict(c, divert_share=lam))
        lc += [dict(land_capacity=lam, carbon=x, save_Mt=pc[f"save_{x}_kt"].sum() / 1e3) for x in (0, 50, 100, 150, 320)]
    pd.DataFrame(lc).to_csv(f"{out}/land_capacity_sensitivity.csv", index=False)
    return d


def uncertainty(out, n_mc, n_attr):
    base, rows = swing("AD-CHP solar-dry pyro", "AD-CHP land", EF_EGY)
    pd.DataFrame(rows, columns=["parameter", "at_low", "at_high", "swing"]).assign(central=base) \
        .to_csv(f"{out}/tornado_gabal.csv", index=False)
    plant_monte_carlo(n_mc).to_csv(f"{out}/mc_total_saving.csv", index=False)
    att, dr = structural_attribution(n_attr)
    dr.to_csv(f"{out}/attribution_draws.csv", index=False)
    json.dump({k: float(v) for k, v in att.items()}, open(f"{out}/attribution.json", "w"), indent=1)
    return att


def grid_scenarios(out):
    """Current practice and the technical potential with every country's grid factor scaled down, as wind and solar
    replace fossil generation (1 = today's grids, 0 = carbon-free grids)."""
    base = dict(WP.COUNTRY_INPUTS)
    rows = []
    try:
        for s in (1.0, 0.75, 0.5, 0.25, 0.0):
            WP.COUNTRY_INPUTS.update({k: (v[0], v[1] * s, v[2], v[3]) for k, v in base.items()})
            df = plant_totals()
            win = df.groupby("best")["ds_kt_yr"].sum() / df["ds_kt_yr"].sum()
            rows.append(dict(grid_scale=s, current_practice_Mt=df.current_kt.sum() / 1e3,
                             best_routes_Mt=df.best_kt.sum() / 1e3, technical_potential_Mt=df.saving_kt.sum() / 1e3,
                             diversion_Mt=df.step_lf_kt.sum() / 1e3, then_best_route_Mt=df.step_best_kt.sum() / 1e3,
                             share_raw_pyrolysis=float(win.filter(like="raw").sum())))
    finally:
        WP.COUNTRY_INPUTS.update(base)
    pd.DataFrame(rows).to_csv(f"{out}/grid_decarbonisation.csv", index=False)


def methane_window_factor(k, horizon=100.0, tau_ch4=11.8):
    """Share of the ultimate landfill methane yield's GWP100 that is realised when every year's emission is weighted
    by its absolute warming potential over the years left in a fixed window (a dynamic metric), relative to the
    convention that gives each emission its own 100-year horizon. First-order decay at k per year."""
    t = np.arange(0, int(horizon)) + 0.5
    frac = k * np.exp(-k * t)                                            # emitted in each year
    agwp = (1.0 - np.exp(-(horizon - t) / tau_ch4)) / (1.0 - np.exp(-horizon / tau_ch4))
    return float((frac * agwp).sum())


def sensitivities(out):
    """Supplementary Table 3: technical potential under alternative assumptions, and the cost of diversion when
    utilities pay no landfill fee or haul further."""
    c = central()
    tp = lambda p=None, **kw: plant_totals(p=p, **kw)["saving_kt"].sum() / 1e3
    rows = [dict(case="central", technical_potential_Mt=tp()),
            dict(case="landfills already capture 50% of gas", technical_potential_Mt=tp(dict(c, lfg_capture=0.5))),
            dict(case="alternative disposal mix for China", technical_potential_Mt=tp(alt_map={"CHN": "CHN_alt"})),
            dict(case="direct N2O only", technical_potential_Mt=tp(dict(c, frac_gasm=0.0, frac_leach=0.0))),
            dict(case="biochar barred from farmland", technical_potential_Mt=tp(dict(c, p_avail_char=0.0, char_perm=0.65))),
            dict(case="IPCC AR5 GWP100 (CH4 28, N2O 265)", technical_potential_Mt=tp(dict(c, gwp_ch4=28.0, gwp_n2o=265.0))),
            dict(case="IPCC AR6 GWP20 (CH4 80, N2O 273)", technical_potential_Mt=tp(dict(c, gwp_ch4=79.7, gwp_n2o=273.0)))]
    for y in (0.40, 0.70):
        rows.append(dict(case=f"secondary-sludge yield {y}", technical_potential_Mt=tp(dict(c, was_yield_per_cod=y))))
    for v in (0.20, 0.40):
        rows.append(dict(case=f"secondary-sludge VS destroyed {v}", technical_potential_Mt=tp(dict(c, was_vs_destruction=v))))
    # the inventory: the screened population (default) against the unscreened 364 entries, the documented-practice
    # scenario, and incineration at every Chinese plant (Supplementary Table 7)
    d = plant_totals()
    rows.append(dict(case="screened inventory (the analytical population)", technical_potential_Mt=d.saving_kt.sum() / 1e3,
                     diversion_Mt=d.step_lf_kt.sum() / 1e3, sludge_Mt_DS=d.ds_kt_yr.sum() / 1e3, plants=len(d)))
    with population("all"):
        d = plant_totals()
        rows.append(dict(case="unscreened inventory: all 364 entries", technical_potential_Mt=d.saving_kt.sum() / 1e3,
                         diversion_Mt=d.step_lf_kt.sum() / 1e3, sludge_Mt_DS=d.ds_kt_yr.sum() / 1e3, plants=len(d)))
    d = plant_totals(documented=True)
    rows.append(dict(case="documented practice: documented flow, digester status and destination where found (Supplementary Table 7)",
                     technical_potential_Mt=d.saving_kt.sum() / 1e3, diversion_Mt=d.step_lf_kt.sum() / 1e3,
                     sludge_Mt_DS=d.ds_kt_yr.sum() / 1e3, plants=len(d)))
    d2 = plant_totals(alt_map={"CHN": "CHN_incin"})
    rows.append(dict(case="China: every plant incinerates its sludge, as documented at its largest plants",
                     technical_potential_Mt=d2.saving_kt.sum() / 1e3, diversion_Mt=d2.step_lf_kt.sum() / 1e3))
    d2 = plant_totals(alt_map={"CHN": "CHN_incin"}, documented=True)
    rows.append(dict(case="documented practice and incineration at every Chinese plant",
                     technical_potential_Mt=d2.saving_kt.sum() / 1e3, diversion_Mt=d2.step_lf_kt.sum() / 1e3))
    for ef, lab in ((0.37, "combined-cycle gas"), (0.90, "coal")):      # marginal rather than average electricity
        d = plant_totals(ef_override=ef)
        rows.append(dict(case=f"marginal electricity = {lab} ({ef} t CO2/MWh) at every plant",
                         technical_potential_Mt=d.saving_kt.sum() / 1e3, current_practice_Mt=d.current_kt.sum() / 1e3,
                         diversion_Mt=d.step_lf_kt.sum() / 1e3,
                         share_raw_pyrolysis=float(d.groupby("best")["ds_kt_yr"].sum().filter(like="raw").sum() / d.ds_kt_yr.sum())))
    for k in (0.06, 0.10, 0.185):                                        # landfill methane released over time
        f = methane_window_factor(k)
        rows.append(dict(case=f"landfill methane in a fixed 100-year window, decay constant {k} per yr (factor {f:.3f})",
                         technical_potential_Mt=tp(dict(c, docf=c["docf"] * f))))
    pd.DataFrame(rows).to_csv(f"{out}/sensitivity_technical_potential.csv", index=False)
    rows = []
    for th in (0.0, 0.25, 0.5, 0.75, 1.0):                               # where sludge goes beats how it is treated
        for dig in (True, False):
            d = plant_totals(digesting=dig, bound=th)
            win = d.step_lf_kt > d.step_ad_kt + d.step_best_kt
            rows.append(dict(landfilled_share_unreported=th, all_digest=dig, plants=int(win.sum()),
                             sludge_share=float(d.loc[win, "ds_kt_yr"].sum() / d.ds_kt_yr.sum())))
    pd.DataFrame(rows).to_csv(f"{out}/where_beats_how_sweep.csv", index=False)
    rows = []
    for lab, q in (("central", {}), ("no landfill fee", dict(tip_usd_t=0.0)), ("landfill fee US$40", dict(tip_usd_t=40.0)),
                   ("80 km extra haul", dict(extra_haul_km=80.0)),
                   ("no landfill fee and 80 km extra haul", dict(tip_usd_t=0.0, extra_haul_km=80.0))):
        d = plant_choice(carbon_values=(0, 50, 100, 320), p=dict(c, **q))
        rows.append(dict(case=lab, diversion_usd_per_t_median=wq(d, "usd_per_t_V", 0.5),
                         **{f"cost_effective_Mt_at_{x}": d[f"save_{x}_kt"].sum() / 1e3 for x in (0, 50, 100, 320)}))
    # the utility's own accounts: the fertiliser value goes to the farmer, not the utility; and a compliance-aware
    # variant in which farmland takes only digested sludge (no plant digests: diversion is unavailable)
    nofert = dict(c, urea_usd_t=0.0, tsp_usd_t=0.0)
    for lab, q, kw in (("utility accounts: no fertiliser revenue", nofert, {}),
                       ("utility accounts: no fertiliser revenue, no landfill fee", dict(nofert, tip_usd_t=0.0), {}),
                       ("utility accounts: no fertiliser revenue, no landfill fee, 80 km extra haul", dict(nofert, tip_usd_t=0.0, extra_haul_km=80.0), {}),
                       ("no plant digests, diversion of undigested sludge allowed", c, dict(digesting=False)),
                       ("no plant digests, farmland takes only digested sludge", c, dict(digesting=False, divert_if_digested=True)),
                       ("no plant digests, digested sludge only, utility accounts with no fee", dict(nofert, tip_usd_t=0.0), dict(digesting=False, divert_if_digested=True))):
        d = plant_choice(carbon_values=(0, 50, 100, 320), p=q, **kw)
        rows.append(dict(case=lab, diversion_usd_per_t_median=wq(d.dropna(subset=["usd_per_t_V"]), "usd_per_t_V", 0.5) if "usd_per_t_V" in d and d.usd_per_t_V.notna().any() else np.nan,
                         **{f"cost_effective_Mt_at_{x}": d[f"save_{x}_kt"].sum() / 1e3 for x in (0, 50, 100, 320)},
                         **{f"diversion_plants_at_{x}": int(d[f"state_{x}"].str.contains("V").sum()) for x in (0, 100)}))
    pd.DataFrame(rows).to_csv(f"{out}/sensitivity_diversion_costs.csv", index=False)
    # documented treatment process: plants that are UASB, SBR/extended aeration without primary settling, or lagoons
    # produce less sludge per unit COD than the activated-sludge-with-primary model; their sludge halved, and removed
    d = plant_totals(); pr = d.waste_id.map(dict(zip(WP.SCREENING.waste_id, WP.SCREENING.process.fillna("")))).fillna("")
    non = pr.ne("")
    rows2 = [dict(case="documented non-activated-sludge plants", plants=int(non.sum()), sludge_share=float(d.loc[non, "ds_kt_yr"].sum() / d.ds_kt_yr.sum()),
                  saving_share=float(d.loc[non, "saving_kt"].sum() / d.saving_kt.sum()))]
    for f in (0.5, 0.0):
        sc = np.where(non, f, 1.0)
        rows2.append(dict(case=f"their sludge x {f}", technical_potential_Mt=float((d.saving_kt * sc).sum() / 1e3),
                          diversion_Mt=float((d.step_lf_kt * sc).sum() / 1e3), sludge_Mt_DS=float((d.ds_kt_yr * sc).sum() / 1e3)))
    for k in ("UASB", "SBR/extended aeration", "lagoon"):
        m = pr.eq(k)
        rows2.append(dict(case=f"process {k}", plants=int(m.sum()), sludge_share=float(d.loc[m, "ds_kt_yr"].sum() / d.ds_kt_yr.sum())))
    pd.DataFrame(rows2).to_csv(f"{out}/sensitivity_process.csv", index=False)
    t = plant_table(digesting=False)
    pd.DataFrame([dict(intervention=i, alone_Mt=t[f"alone_{i}_kt"].sum() / 1e3, shapley_Mt=t[f"shapley_{i}_kt"].sum() / 1e3)
                  for i in ("V", "G", "A", "P")]).to_csv(f"{out}/interventions_no_digestion.csv", index=False)


def decisions(out, n):
    """Value of information: which unreported fact would change each plant's choice of intervention, and how six
    ways of choosing compare on the same draws. Reported values use n x n draws with seed 11; the convergence table
    repeats the totals at n/3, 2n/3 and n draws for three seeds."""
    from sludgeroutes.decisions import FACTS, _benefits, convergence, crossfit, strategies, survey_value
    rows = []; cf = []; sts = []
    for size in sorted({max(n // 3, 4), max(2 * n // 3, 4), n}):
        for seed in (11, 12, 13):
            arr = _benefits(size, size, seed)
            for cv in (100.0, 320.0):
                d = plant_voi(size, size, cv, seed, arrays=arr)
                if size == n and seed == 11:
                    d.to_csv(f"{out}/value_of_information_{int(cv)}.csv", index=False)
                if cv == 100.0:
                    rows.append(dict(n_params=size, n_facts=size, seed=seed, expected_benefit_musd=d.expected_benefit_usd_yr.sum() / 1e6,
                                     evpi_facts_musd=d.evpi_facts_usd_yr.sum() / 1e6, evpi_all_musd=d.evpi_all_usd_yr.sum() / 1e6,
                                     **{f"evpi_{f}_musd": d[f"evpi_{f}_usd_yr"].sum() / 1e6 for f in FACTS},
                                     plants_VG=int((d.expected_choice == "VG").sum()), plants_P=int((d.expected_choice == "P").sum()),
                                     median_best_share=d.expected_choice_best_share.median()))
            if size == n:
                st_ = strategies(size, size, seed, arrays=arr)
                sts.append(st_.assign(seed=seed)); pd.concat(sts).to_csv(f"{out}/strategies_seeds.csv", index=False)
            if size == n and seed == 11:
                st_.to_csv(f"{out}/strategies.csv", index=False)
                survey_value(size, size, 100.0, seed, arrays=arr).to_csv(f"{out}/survey_value_100.csv", index=False)
            if size == n and seed in (11, 12):
                cf.append(dict(seed=seed, **crossfit(size, size, 100.0, seed, arrays=arr)))
                pd.DataFrame(cf).to_csv(f"{out}/value_of_information_crossfit.csv", index=False)
            pd.DataFrame(rows).to_csv(f"{out}/value_of_information_convergence.csv", index=False)
            print(f"  voi {size}x{size} seed {seed} done", flush=True)
    # alternative uncertainty distribution: landfilled share (no reported mix) and farmland share from Beta(2, 2)
    arr = _benefits(n, n, 11, dist="beta22")
    d = plant_voi(n, n, 100.0, 11, arrays=arr)
    alt = strategies(n, n, 11, carbon_values=(100.0,), arrays=arr).assign(distribution="beta22")
    alt["evpi_facts_musd"] = d.evpi_facts_usd_yr.sum() / 1e6
    alt.to_csv(f"{out}/strategies_beta22.csv", index=False)
    print("  voi beta22 done", flush=True)


def economics(out):
    c = central()
    a = plant_economics(278.0, c).assign(case="no bio-oil")
    b = plant_economics(278.0, dict(c, oil_frac_of_vs=0.2)).assign(case="bio-oil sold")
    pd.concat([a, b]).to_csv(f"{out}/pyrolysis_breakeven.csv", index=False)


def headline(out, df, it, att):
    c = central()
    h = {}
    tot = df.saving_kt.sum() / 1e3
    h["population"] = WP.POPULATION; h["n_plants"] = int(len(df)); h["n_excluded_by_screening"] = len(WP.excluded_ids())
    h["sludge_Mt_DS"] = df.ds_kt_yr.sum() / 1e3
    h["technical_potential_Mt"] = tot
    h["diversion_Mt"] = df.step_lf_kt.sum() / 1e3
    h["diversion_share_of_technical"] = df.step_lf_kt.sum() / df.saving_kt.sum()
    h["then_best_route_Mt"] = df.step_best_kt.sum() / 1e3
    t = plant_table()
    for k in ("alone_V", "alone_G", "alone_P", "last_P", "shapley_V", "shapley_G", "shapley_P"):
        h[f"intervention_{k}_Mt"] = t[f"{k}_kt"].sum() / 1e3
    for col in [x for x in it if x.startswith("usd_per_t")]:
        h[f"{col}_p10_p50_p90"] = [wq(it, col, q) for q in (0.1, 0.5, 0.9)]
    h["grid_tipping_warm"] = grid_tipping(warm=True)
    h["grid_tipping_cold"] = grid_tipping(warm=False)
    h["gabal_ds_t_d"] = gabal_ds_t_d()
    h["mixed_sludge_properties"] = {k: mix(c)[k] for k in ("vs_frac_raw", "vs_destruction", "n_frac_ds", "p_frac_ds", "primary_share")}
    h["sludge_per_1000m3_at_278"] = dict(primary=float(raw_ds(1000.0, 278.0, c) * 1000), secondary=float(was_ds(1000.0, 278.0, c) * 1000))
    h["attribution"] = att
    h["n_parameters"] = len(P)
    h["n_working_assumptions"] = sum("ASSUMPTION" in v[3] for v in P.values())
    json.dump(h, open(f"{out}/headline.json", "w"), indent=1, default=float)
    return h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="10x fewer Monte Carlo draws")
    ap.add_argument("--out", default="results")
    ap.add_argument("--population", default="screened", choices=("screened", "all"),
                    help="screened: entries the screening removes are excluded (default); all: the 364 inventory entries")
    a = ap.parse_args()
    WP.POPULATION = a.population
    k = 10 if a.quick else 1
    os.makedirs(a.out, exist_ok=True)
    pd.DataFrame([dict(parameter=n, central=v[0], low=v[1], high=v[2], source=v[3],
                       working_assumption="ASSUMPTION" in v[3]) for n, v in P.items()]).to_csv(f"{a.out}/parameters.csv", index=False)
    gabal(a.out, 2000 // k)
    decision_map(a.out)
    df = plants(a.out, 300 // k)
    it = interventions(a.out, 200 // k)
    att = uncertainty(a.out, 1000 // k, 1000 // k)
    economics(a.out)
    grid_scenarios(a.out)
    sensitivities(a.out)
    decisions(a.out, 300 // k)
    h = headline(a.out, df, it, att)
    print(json.dumps({k_: h[k_] for k_ in ("technical_potential_Mt", "diversion_Mt", "diversion_share_of_technical",
                                            "then_best_route_Mt")}, indent=1, default=float))


if __name__ == "__main__":
    main()
