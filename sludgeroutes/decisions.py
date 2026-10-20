"""Which missing fact would change the decision at each plant, and what knowing it is worth.

At a carbon value, each plant chooses the combination of the costed interventions (diversion V, gas capture G,
pyrolysis P) that maximises net benefit = carbon value x CO2e avoided - net cost (as interventions.plant_choice).
Four plant facts are unreported and are drawn with the model parameters:
  d      whether the plant digests today (0 or 1, equal odds)
  theta  where it sends its sludge: in countries without a reported disposal mix, the landfilled share (uniform 0-1);
         in countries with one, the plant's destination (land, landfill or incineration), drawn from the national
         mix, so the mix holds on average but each plant sends its sludge one way; where the plant's destination is
         documented (data/plant_screening.csv), that destination, with no uncertainty
  c      influent COD (log-uniform 278-600 mg/L)
  lam    share of the landfilled sludge that farmland can take (uniform 0-1)
Digestion status is likewise taken as known where it is documented.
Sampling is nested: n_p parameter draws x n_f fact draws, every fact draw evaluated under every parameter draw.
Emissions and costs are linear in theta and lam, so two runs per parameter draw bracket them; d gives two more; the
pyrolysis cost depends on plant size through c and is evaluated per sample.
The expected value of perfect information (EVPI) on the facts is
    E_facts[ max_s E_params(v_s | facts) ] - max_s E(v_s),
the gain from learning the facts before deciding; on one fact it is estimated by binning that fact; on everything
(facts and parameters) it is E[max_s v_s] - max_s E(v_s). All are zero where the same choice is best regardless.
"""
import numpy as np
import pandas as pd

from . import data as WP
from .data import DISPOSAL, ELEC_PRICE, load_plants
from .econ import pyro_cost_per_t_feed
from .interventions import STATES, plant_choice, state_cost_parts, state_ghg
from .params import central
from .plants import sludge_ds
from .uncertainty import draws

DEC = [s for s in STATES if s <= {"V", "G", "P"}]
LAB = {s: "".join(sorted(s, key="VGP".index)) or "-" for s in DEC}
FACTS = ("digestion", "disposal", "cod", "land")


def _corner_tables(p, iso, sec, warm, digesting, bound, lam, alt=None):
    q = dict(p, with_secondary=sec, divert_share=lam, elec_price_usd_kwh=ELEC_PRICE[iso], diesel_usd_l=WP.COUNTRY_INPUTS[iso][2])
    ef = WP.COUNTRY_INPUTS[iso][1]
    e = {s: state_ghg(s, iso, ef, q, digesting, warm, bound, alt) for s in DEC}
    c = {s: state_cost_parts(s, iso, ef, q, digesting, warm, bound, alt) for s in DEC}
    return e, c


CATS = ("land", "landfill", "incin")


def _plant_facts(df, D, TH, U):
    """Per plant: digestion status per fact draw (documented where known), the disposal corners
    [(alt, bound, weight per fact draw)] and the disposal classes a 2- and 5-class survey would report."""
    doc = WP.documented().reindex(df.waste_id)
    dig, corners, d2, d5 = [], [], [], []
    q5 = pd.qcut(TH, 5, labels=False); q2 = (TH >= np.median(TH)).astype(int)
    ones, zeros = np.ones(len(TH)), np.zeros(len(TH), dtype=int)
    for i, r in enumerate(df.itertuples(index=False)):
        dg, ft = doc["digesting"].iat[i], doc["fate"].iat[i]
        dig.append(D if np.isnan(dg) else np.full(len(D), int(dg)))
        if isinstance(ft, str):                                   # documented: known
            corners.append([(f"doc_{ft}", "mid", ones)]); d2.append(zeros); d5.append(zeros)
        elif r.iso in DISPOSAL:                                   # national mix reported: plant destination drawn from it
            m = DISPOSAL[r.iso]
            pr = np.array([m["land"] + m["other"] / 2, m["landfill"] + m["other"] / 2, m["incin"]])
            cls = np.minimum(np.searchsorted(np.cumsum(pr) / pr.sum(), U, side="right"), 2)
            corners.append([(f"doc_{c}", "mid", (cls == k).astype(float)) for k, c in enumerate(CATS) if pr[k] > 0])
            d2.append((cls == 1).astype(int)); d5.append(cls)
        else:                                                     # no mix reported: landfilled share uniform
            corners.append([(None, "low", 1 - TH), (None, "high", TH)]); d2.append(q2); d5.append(q5)
    return np.array(dig), corners, np.array(d2), np.array(d5)


def _bins(X, fact, i, k=5):
    """Classes of fact `fact` at plant i that a survey with k classes would report (exact for digestion)."""
    if fact == "digestion":
        return X["dig_p"][i]
    if fact == "disposal":
        return X["disp5"][i] if k == 5 else X["disp2"][i]
    return pd.qcut(X[fact], k, labels=False)


def _pyro_vec(feed_kt_yr, p):
    """pyro_cost_per_t_feed for an array of plant sizes."""
    q = np.clip(feed_kt_yr, 2.0, 50.0) / p["pyro_ref_kt_ds"]
    c = p["pyro_cost_usd_t_feed"]
    return c * (p["capex_mult"] * p["pyro_cap_share"] * q ** (p["scale_exp"] - 1.0) + (1.0 - p["pyro_cap_share"]))


def _benefits(n_p, n_f, seed, cod_range=(278.0, 600.0), dist="uniform"):
    """CO2e avoided (kt/yr) and net cost (US$/yr) per plant, parameter draw, fact draw and decision: two arrays
    (plants, n_p, n_f, decisions), plus the fact draws. Net benefit at carbon value p is p x 1000 x S - K.
    dist="beta22": the landfilled share where no mix is reported and the farmland share drawn from Beta(2, 2)
    rather than uniform (an alternative uncertainty distribution)."""
    df = load_plants()
    rng = np.random.default_rng(seed + 1000)                 # facts on their own stream
    ps = draws(n_p, seed) if n_p > 0 else [central()]        # n_p = 0: central parameters only
    D = rng.integers(0, 2, n_f)
    TH = rng.uniform(size=n_f)
    C = np.exp(rng.uniform(np.log(cod_range[0]), np.log(cod_range[1]), n_f))
    LAM = rng.uniform(size=n_f)
    U = rng.uniform(size=n_f)                                # plant destination where a national mix is reported
    if dist == "beta22":
        from scipy.stats import beta
        TH, LAM = beta.ppf(TH, 2, 2), beta.ppf(LAM, 2, 2)
    dig_p, corners, d2, d5 = _plant_facts(df, D, TH, U)
    S = np.zeros((len(df), len(ps), n_f, len(DEC)), dtype=np.float32)
    K = np.zeros_like(S)
    plants = list(df.itertuples(index=False))
    keys = [(r.iso, int(r.treatment_level != "Primary"), abs(r.lat) <= 35.0) for r in plants]
    wl = {0.0: 1 - LAM, 1.0: LAM}
    for k, p in enumerate(ps):
        tabs = {}
        DS = {c: sludge_ds(df, c, p) * 365 / 1000.0 for c in np.unique(C)}       # kt DS/yr per plant per COD draw
        dsf = np.stack([DS[c] for c in C], axis=1)                                 # (plants, n_f)
        for i in range(len(plants)):
            key = keys[i]
            ds = dsf[i]
            parts = []                                                             # (mask, weight, e, c) per corner
            for d in (0, 1):
                m = dig_p[i] == d
                if not m.any():
                    continue
                for alt, b, wd in corners[i]:
                    for L in (0.0, 1.0):
                        w = (wd * wl[L])[m]
                        if not w.any():
                            continue
                        tk = key + (d, alt, b, L)
                        if tk not in tabs:
                            tabs[tk] = _corner_tables(p, key[0], key[1], key[2], bool(d), b, L, alt)
                        parts.append((m, w) + tabs[tk])
            for j, s in enumerate(DEC):
                sav = np.zeros(n_f); cost = np.zeros(n_f)
                for m, w, e, cc in parts:
                    other, feed = cc[s]
                    pyro = _pyro_vec(ds[m] * feed, p) * feed if feed else 0.0
                    sav[m] += w * (e[frozenset()] - e[s])
                    cost[m] += w * (other + pyro)
                S[i, k, :, j] = sav * ds
                K[i, k, :, j] = cost * ds * 1000.0
    return df, S, K, dict(digestion=D, disposal=TH, cod=C, land=LAM, dig_p=dig_p, disp2=d2, disp5=d5)


def plant_voi(n_p=100, n_f=100, carbon_value=100.0, seed=11, arrays=None):
    """Per plant: the choice at central values (all plants digest, farmland takes everything), the choice that
    maximises expected net benefit over the joint draws, how often that choice is best, the expected net benefit,
    the EVPI of the four facts together, of each fact, and of everything, and the fact with the largest EVPI."""
    df, S, K, X = _benefits(n_p, n_f, seed) if arrays is None else arrays
    pc = plant_choice(carbon_values=(int(carbon_value),), documented=True).set_index("waste_id")
    out = []
    for i, r in enumerate(df.itertuples(index=False)):
        v = carbon_value * 1000.0 * S[i].astype(np.float64) - K[i].astype(np.float64)   # (n_p, n_f, dec)
        mean = v.mean(axis=(0, 1))
        best = int(mean.argmax())
        by_fact = v.mean(axis=0)                                      # E_params[v | facts]: (n_f, dec)
        evpi_facts = by_fact.max(axis=1).mean() - mean.max()
        evpi_all = v.max(axis=2).mean() - mean.max()
        row = dict(waste_id=r.waste_id, iso=r.iso, country=r.country, lat=r.lat, lon=r.lon,
                   central_choice=pc.loc[r.waste_id, f"state_{int(carbon_value)}"],
                   expected_choice=LAB[DEC[best]], expected_benefit_usd_yr=mean.max(),
                   expected_choice_best_share=float((v[:, :, best] >= v.max(axis=2) - 1.0).mean()),   # ties count as best
                   evpi_facts_usd_yr=evpi_facts, evpi_all_usd_yr=evpi_all)
        for fact in FACTS:
            bins = _bins(X, fact, i, 5)
            g = pd.DataFrame(by_fact).groupby(bins)
            m, w = g.mean(), g.size()
            row[f"evpi_{fact}_usd_yr"] = float((m.max(axis=1) * w).sum() / w.sum() - mean.max())
        ev = {f: row[f"evpi_{f}_usd_yr"] for f in FACTS}
        row["most_valuable_fact"] = max(ev, key=ev.get) if max(ev.values()) > 1.0 else "none"
        out.append(row)
    return pd.DataFrame(out)


def convergence(carbon_value=100.0, sizes=((50, 50), (100, 100), (150, 150)), seeds=(11, 12, 13)):
    """Totals across plants for several sample sizes and seeds, to show the estimates have converged. The
    standard error of each total is the across-seed standard deviation at that size."""
    rows = []
    for n_p, n_f in sizes:
        for seed in seeds:
            d = plant_voi(n_p, n_f, carbon_value, seed)
            rows.append(dict(n_params=n_p, n_facts=n_f, seed=seed, expected_benefit_musd=d.expected_benefit_usd_yr.sum() / 1e6,
                             evpi_facts_musd=d.evpi_facts_usd_yr.sum() / 1e6, evpi_all_musd=d.evpi_all_usd_yr.sum() / 1e6,
                             **{f"evpi_{f}_musd": d[f"evpi_{f}_usd_yr"].sum() / 1e6 for f in FACTS},
                             plants_VG=int((d.expected_choice == "VG").sum()), plants_P=int((d.expected_choice == "P").sum()),
                             median_best_share=d.expected_choice_best_share.median()))
    return pd.DataFrame(rows)


STRATEGIES = ("pyrolysis everywhere", "divert where landfilled", "divert and capture where landfilled", "central-case choice",
              "central parameters, facts uncertain", "expected-value choice", "perfect information on facts",
              "perfect information on everything")


def strategies(n_p=100, n_f=100, seed=11, carbon_values=(100.0, 320.0), arrays=None):
    """Expected outcome across the plants of eight ways of choosing among the costed interventions, evaluated on
    the same joint draws: a technology-first rule (pyrolysis at every plant), a destination-first rule (diversion
    wherever the country landfills), a conservative planning rule (divert what farmland can take and capture gas from
    the rest, wherever the country landfills: no new treatment units), the choice at central values, the choice that maximises expected net benefit,
    the choice that maximises expected net benefit over the fact draws at central parameter values (which isolates the
    effect of treating the facts as uncertain from that of parameter uncertainty), and the choices made knowing the plant
    facts, or everything, in advance. Regret is the expected net benefit
    forgone relative to perfect information on everything; all quantities are totals over plants, per year."""
    df, S, K, X = _benefits(n_p, n_f, seed) if arrays is None else arrays
    _, S0, K0, _ = _benefits(0, S.shape[2], seed)             # central parameters, same fact draws
    iP = DEC.index(frozenset("P")); iV = DEC.index(frozenset("V")); iVG = DEC.index(frozenset("VG")); i0 = DEC.index(frozenset())
    rows = []
    for cv in carbon_values:
        pc = plant_choice(carbon_values=(int(cv),), documented=True).set_index("waste_id")
        tot = {k: dict(saving_kt=0.0, cost_musd=0.0, benefit_musd=0.0, regret_musd=0.0) for k in STRATEGIES}
        for i, r in enumerate(df.itertuples(index=False)):
            Si, Ki = S[i].astype(np.float64), K[i].astype(np.float64)
            v = cv * 1000.0 * Si - Ki
            mean = v.mean(axis=(0, 1))
            by_fact = v.mean(axis=0)
            v0 = cv * 1000.0 * S0[i, 0].astype(np.float64) - K0[i, 0].astype(np.float64)   # (n_f, dec) at central parameters
            pick = {"pyrolysis everywhere": iP,
                    "divert where landfilled": iV if (Si[:, :, iV].mean() > 1e-9) else i0,
                    "divert and capture where landfilled": iVG if (Si[:, :, iV].mean() > 1e-9) else i0,
                    "central-case choice": DEC.index(frozenset(pc.loc[r.waste_id, f"state_{int(cv)}"].replace("-", ""))),
                    "central parameters, facts uncertain": int(v0.mean(axis=0).argmax()),
                    "expected-value choice": int(mean.argmax())}
            best_all = v.max(axis=2).mean()
            for k, j in pick.items():
                tot[k]["saving_kt"] += Si[:, :, j].mean(); tot[k]["cost_musd"] += Ki[:, :, j].mean() / 1e6
                tot[k]["benefit_musd"] += mean[j] / 1e6; tot[k]["regret_musd"] += (best_all - mean[j]) / 1e6
            jf = by_fact.argmax(axis=1)                                   # choice per fact draw
            sf = Si.mean(axis=0)[np.arange(len(jf)), jf].mean(); kf = Ki.mean(axis=0)[np.arange(len(jf)), jf].mean()
            bf = by_fact.max(axis=1).mean()
            tot["perfect information on facts"]["saving_kt"] += sf; tot["perfect information on facts"]["cost_musd"] += kf / 1e6
            tot["perfect information on facts"]["benefit_musd"] += bf / 1e6
            tot["perfect information on facts"]["regret_musd"] += (best_all - bf) / 1e6
            ja = v.argmax(axis=2)
            tot["perfect information on everything"]["saving_kt"] += np.take_along_axis(Si, ja[..., None], 2).mean()
            tot["perfect information on everything"]["cost_musd"] += np.take_along_axis(Ki, ja[..., None], 2).mean() / 1e6
            tot["perfect information on everything"]["benefit_musd"] += best_all / 1e6
        for k in STRATEGIES:
            rows.append(dict(carbon_value=cv, strategy=k, **tot[k]))
    return pd.DataFrame(rows)


SURVEYS = {
    "disposal_2": ("disposal", 2), "disposal_5": ("disposal", 5), "digestion": ("digestion", 2),
    "cod_2": ("cod", 2), "cod_5": ("cod", 5), "land_2": ("land", 2), "land_5": ("land", 5),
}


def survey_value(n_p=100, n_f=100, carbon_value=100.0, seed=11, arrays=None):
    """Expected value of imperfect information per plant (US$/yr): what a survey that places a fact into k
    classes is worth before deciding (k = 2: above or below the median of its range; k = 5: quintiles; exact for
    digestion status), and the value of two combined surveys, a national disposal inventory (2 classes) plus a
    digester registry. The same estimator as plant_voi, with coarser bins; k classes of a continuous fact are a
    lower bound on learning it exactly."""
    df, S, K, X = _benefits(n_p, n_f, seed) if arrays is None else arrays
    out = []
    def binned(v_by_fact, bins, mean):
        g = pd.DataFrame(v_by_fact).groupby(bins)
        m, w = g.mean(), g.size()
        return max(float((m.max(axis=1) * w).sum() / w.sum() - mean.max()), 0.0)
    for i, r in enumerate(df.itertuples(index=False)):
        v = carbon_value * 1000.0 * S[i].astype(np.float64) - K[i].astype(np.float64)
        mean = v.mean(axis=(0, 1)); by_fact = v.mean(axis=0)
        row = dict(waste_id=r.waste_id, iso=r.iso, country=r.country, expected_benefit_usd_yr=mean.max())
        B = {}
        for name, (fact, k) in SURVEYS.items():
            B[name] = np.asarray(_bins(X, fact, i, k))
            row[f"value_{name}_usd_yr"] = binned(by_fact, B[name], mean)
        row["value_disposal_2_plus_digestion_usd_yr"] = binned(by_fact, B["disposal_2"] * 2 + B["digestion"], mean)
        row["value_disposal_5_plus_digestion_usd_yr"] = binned(by_fact, B["disposal_5"] * 2 + B["digestion"], mean)
        row["value_all_facts_usd_yr"] = float(by_fact.max(axis=1).mean() - mean.max())
        out.append(row)
    return pd.DataFrame(out)


def crossfit(n_p=100, n_f=100, carbon_value=100.0, seed=11, arrays=None):
    """Out-of-sample check of the decision quantities: parameter and fact draws are each split in two; the
    choice (and, for the value of information, the choice conditional on each fact class) is made on the first
    halves and valued on the second, so the maximisation and the valuation never share a draw. Returns totals
    across plants for the in-sample and cross-fitted versions."""
    df, S, K, X = _benefits(n_p, n_f, seed) if arrays is None else arrays
    hp, hf = S.shape[1] // 2, S.shape[2] // 2
    tot = dict(benefit_in=0.0, benefit_cf=0.0, evpi_facts_in=0.0, evpi_facts_cf=0.0, evpi_facts_cf_exact=0.0,
               **{f"evpi_{f}_in": 0.0 for f in FACTS}, **{f"evpi_{f}_cf": 0.0 for f in FACTS})
    for i in range(len(df)):
        bins = {f: np.asarray(_bins(X, f, i, 5)) for f in FACTS}
        two = {f: (np.asarray(_bins(X, f, i, 2)) if f in ("digestion", "disposal") else (bins[f] >= 3).astype(int)) for f in FACTS}
        v = carbon_value * 1000.0 * S[i].astype(np.float64) - K[i].astype(np.float64)
        A, B = v[:hp, :hf], v[hp:, hf:]                       # (params, facts, dec)
        mA, mB = A.mean(axis=(0, 1)), B.mean(axis=(0, 1))
        jA = int(mA.argmax())
        tot["benefit_in"] += mA.max(); tot["benefit_cf"] += mB[jA]
        fA, fB = A.mean(axis=0), B.mean(axis=0)               # E_params[v | fact draw]: (facts, dec)
        tot["evpi_facts_in"] += fA.max(axis=1).mean() - mA.max()
        # exact facts, held out over parameters only: the choice at each fact draw is made on the first half of the
        # parameter draws and valued on the second (the facts need no binning, so this is the direct check of the
        # joint value of perfect information on the facts)
        PA, PB = v[:hp], v[hp:]                                # (params, all facts, dec)
        gA, gB = PA.mean(axis=0), PB.mean(axis=0)
        jp = gA.argmax(axis=1)
        tot["evpi_facts_cf_exact"] += gB[np.arange(len(jp)), jp].mean() - gB.mean(axis=0)[int(gA.mean(axis=0).argmax())]
        # cross-fitted joint value: choice per fact class on A, valued on B, with classes from all four facts
        for f in FACTS:
            bA, bB = bins[f][:hf], bins[f][hf:]
            gA = pd.DataFrame(fA).groupby(bA).mean(); gB = pd.DataFrame(fB).groupby(bB)
            wB = gB.size(); mBg = gB.mean()
            wA = pd.Series(bA).value_counts().sort_index()
            tot[f"evpi_{f}_in"] += max(float((gA.max(axis=1) * wA).sum() / wA.sum() - mA.max()), 0.0)
            pick = gA.idxmax(axis=1)                          # choice per class, from A
            val = sum(mBg.loc[c, pick.get(c, jA)] * wB.loc[c] for c in mBg.index) / wB.sum()
            tot[f"evpi_{f}_cf"] += float(val - mB[jA])                # unclipped: noisy but unbiased
        # joint value of all four facts, cross-fitted on a 2 x 2 x 2 x 2 grid of fact classes (finer cells are
        # too sparse in half the draws): choice per cell from A, valued on B
        cA = sum(two[f][:hf].astype(int) << k for k, f in enumerate(FACTS))
        cB = sum(two[f][hf:].astype(int) << k for k, f in enumerate(FACTS))
        gA = pd.DataFrame(fA).groupby(cA).mean(); gB = pd.DataFrame(fB).groupby(cB); wB = gB.size(); mBg = gB.mean()
        pick = gA.idxmax(axis=1)
        val = sum(mBg.loc[c, pick.get(c, jA)] * wB.loc[c] for c in mBg.index) / wB.sum()
        tot["evpi_facts_cf"] += float(val - mB[jA])
    return {k: v / 1e6 for k, v in tot.items()}
