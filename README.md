# sludgeroutes

Climate and cost of sewage-sludge routes and interventions at the large wastewater treatment plants (HydroWASTE entries
treating at least 100,000 m³ d⁻¹) outside high-income economies. The 364 inventory entries are screened against public
sources (`data/plant_screening.csv`): entries with no plant of that size behind them (no plant found, a documented plant
below the threshold, preliminary treatment only, or a duplicate) are removed, and the screened population is the one
every result is computed on; `python run_all.py --population all` restores the unscreened 364 entries.


## What the model does

- **12 routes** per tonne of raw sludge dry solids (primary sludge, blended with waste activated sludge at plants with
  secondary treatment): dumping, land application, digestion with CHP, biomethane, incineration and pyrolysis, with
  solar or thermal drying. Consequential accounting, GWP100 (IPCC AR6); biochar carbon credited with
  IPCC 2019 permanence (`sludgeroutes/routes.py`).
- **Current practice** per country from reported disposal mixes, bounded where none is reported
  (`sludgeroutes/plants.py`, `data/disposal.csv`).
- **Four interventions** on top of current practice, alone and in all 16 combinations: diversion from landfill to
  farmland, landfill gas capture, digestion and pyrolysis; savings alone, added last and as Shapley values; net costs
  and cost-effective potential against a carbon value (`sludgeroutes/interventions.py`).
- **Economics** of pyrolysis scaled to each plant, with each country's electricity and diesel prices
  (`sludgeroutes/econ.py`).
- **Uncertainty**: triangular Monte Carlo over all parameters, one-at-a-time swings, and variance attribution to
  unreported plant conditions (`sludgeroutes/uncertainty.py`).
- **Value of information**: which unreported plant fact (digestion, disposal, influent strength, land capacity)
  would change the choice of intervention at each plant, and what learning it is worth (`sludgeroutes/decisions.py`).
- **Grid decarbonisation**: current practice and the technical potential with every country's grid factor scaled
  towards zero (`run_all.py`).


## Data

| File | Content | Source |
|---|---|---|
| `data/plants.csv` | 364 inventory entries: location, flow, treatment level | HydroWASTE v1.0 (Ehalt Macedo et al. 2022, CC BY 4.0) |
| `data/plant_screening.csv` | screening verdict per entry (real / smaller / phantom / outfall / duplicate / industrial / unresolved), documented flow, digester status and sludge destination where found | public sources listed in Supplementary Table 7 |
| `data/inventory_screening_table7.csv` | the full screening record (Supplementary Table 7): what each checked entry is, documented flow, digesters, destination, notes, sources and URLs | public sources, checked 19–20 October 2026 |
| `data/countries.csv` | grid carbon intensity; diesel and electricity prices | Ember 2025 via Our World in Data; GlobalPetrolPrices.com |
| `data/disposal.csv` | reported shares of sludge to land, landfill, incineration, other | sources in the file |

## SludgeRoutes Planner (decision tool)

`tool/index.html` (SludgeRoutes Planner) is a single-file web page that runs the same model in the browser for one plant: enter its flow,
grid, disposal practice, digestion status and prices, mark what is unknown, and it ranks the interventions, gives
their costs and shows how much the choice depends on the unknown facts (expected value of information). The page is
a JavaScript port of `sludgeroutes/` (`tool/model.js`), checked against the Python code on 2,599 test values
(`node tool/parity_check.js`). Rebuild it after changing parameters with `python tool/build_tool.py`. Serve it from
GitHub Pages or open it locally; it needs no server.

## Run

```
pip install -r requirements.txt
python -m pytest tests        # central results quoted in the paper (seconds)
python run_all.py --quick     # all result tables, 10x fewer Monte Carlo draws (minutes)
python run_all.py             # full run as in the paper
```


| Output | In the paper |
|---|---|
| `gabal_routes.csv`, `gabal_grid_sweep.csv`, `gabal_open_drying_sweep.csv` | Fig. 2, Extended Data Fig. 2 |
| `decision_map.csv` | Fig. 3 |
| `plants.csv`, `countries.csv`, `structural_scenarios.csv` | Fig. 1, Supplementary Tables 2–3 |
| `intervention_costs.csv`, `cost_effective_potential.csv`, `land_capacity_sensitivity.csv` | Fig. 4, Supplementary Tables 3–4 |
| `tornado_gabal.csv`, `mc_total_saving.csv`, `attribution.json`, `attribution_draws.csv` | Extended Data Fig. 1 |
| `pyrolysis_breakeven.csv` | Extended Data Fig. 3 |
| `value_of_information_100.csv`, `value_of_information_320.csv` | Extended Data Fig. 4, Supplementary Table 4 |
| `value_of_information_crossfit.csv` | Supplementary Note 4.4 (choices made on one half of the draws, valued on the other) |
| `value_of_information_convergence.csv` | Supplementary Table 5 (100², 200², 300² draws × 3 seeds) |
| `strategies.csv` | Extended Data Fig. 5 (eight decision rules on the same joint draws) |
| `strategies_seeds.csv`, `strategies_beta22.csv` | Supplementary Note 4.6 (the rules on three seeds; with Beta(2, 2) fact distributions) |
| `survey_value_100.csv` | Supplementary Table 6 (value of surveys of stated precision, by plant) |
| `grid_decarbonisation.csv`, `sensitivity_technical_potential.csv`, `sensitivity_diversion_costs.csv`, `sensitivity_process.csv`, `interventions_no_digestion.csv`, `where_beats_how_sweep.csv` | Supplementary Table 3 |
| `parameters.csv` | Supplementary Table 1 |
| `headline.json` | the numbers quoted in the abstract and main text |

Tested with Python 3.13, NumPy 2.5, pandas 3.0 and SciPy 1.18 (SciPy is needed only for the Beta(2, 2) sensitivity of Supplementary Note 4.6).

## Licence

Code: MIT. Data files keep the licences of their sources.
