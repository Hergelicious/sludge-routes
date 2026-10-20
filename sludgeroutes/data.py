"""Input data shipped with the model (data/*.csv) and the primary-capture fraction.

plants.csv     364 HydroWASTE plants (>= 100,000 m3/d, outside the World Bank high-income group); HydroWASTE v1.0,
               Ehalt Macedo et al. 2022, Earth Syst. Sci. Data 14, 559-577 (CC BY 4.0).
countries.csv  grid carbon intensity (Ember 2025, via Our World in Data; Indonesia and Nicaragua 2024), retail diesel
               price and business electricity price (GlobalPetrolPrices.com).
disposal.csv   reported shares of sludge to land, landfill, incineration and other uses, with sources.
plant_screening.csv
               public-source screening of inventory entries (Supplementary Table 7): verdict (real / smaller /
               phantom / outfall / duplicate / industrial / unresolved), documented flow, digester status, sludge
               destination and, where it is not activated sludge with primary settling, the treatment process.

The analytical population is the screened inventory: entries that the screening shows are not a treatment plant of
>= 100,000 m3/d (no plant found, a documented plant below the threshold, preliminary treatment only, or a duplicate of
another entry) are removed. POPULATION = "all" restores the unscreened 364 entries for comparison.
"""
import contextlib
import os

import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CAPTURE = 0.59      # share of influent COD captured in primary settling: Gabal El-Asfar 2016, 56.6 of 138.0 t COD/d
                    # passed primary settling (Elawwad et al. 2017)

_c = pd.read_csv(os.path.join(DATA, "countries.csv"))
COUNTRY_INPUTS = {r.iso: (r.country, float(r.grid_tco2_per_mwh), float(r.diesel_usd_l), r.diesel_price_date)
                  for r in _c.itertuples(index=False)}
ELEC_PRICE = {r.iso: float(r.elec_price_usd_kwh) for r in _c.itertuples(index=False)}
LEAN = {r.iso: r.disposal_lean for r in _c.itertuples(index=False) if isinstance(r.disposal_lean, str) and r.disposal_lean}
DISPOSAL = {r.key: dict(land=r.land, landfill=r.landfill, incin=r.incin, other=r.other, src=r.source)
            for r in pd.read_csv(os.path.join(DATA, "disposal.csv")).itertuples(index=False)}


SCREENING = pd.read_csv(os.path.join(DATA, "plant_screening.csv"))
EXCLUDED = ("phantom", "outfall", "duplicate", "smaller", "industrial")          # verdicts that remove an entry from the population
POPULATION = "screened"                                            # "screened" (default) or "all"


def excluded_ids():
    """Inventory entries the screening removes (Supplementary Table 7)."""
    return set(SCREENING.loc[SCREENING.verdict.isin(EXCLUDED), "waste_id"].astype(int))


def load_plants(population=None):
    df = pd.read_csv(os.path.join(DATA, "plants.csv"))
    if (population or POPULATION) == "screened":
        df = df[~df.waste_id.isin(excluded_ids())].reset_index(drop=True)
    return df


@contextlib.contextmanager
def population(name):
    """Run a block on another population: with population("all"): ..."""
    global POPULATION
    old, POPULATION = POPULATION, name
    try:
        yield
    finally:
        POPULATION = old


def documented():
    """Per-plant documented facts for the documented-practice scenario: flow, digester status and destination
    where the screening found them (NaN elsewhere), indexed by waste_id."""
    d = SCREENING.set_index("waste_id")
    return d[["documented_flow_m3d", "digesting", "fate"]]
