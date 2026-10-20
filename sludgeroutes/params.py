"""Parameters of the sludge-route comparison. Every value is (central, low, high, source key).

Values marked ASSUMPTION have no direct published source; they are varied over the stated range.
Basis: one tonne of dry solids (t DS) of raw sludge sent to treatment: primary sludge, blended with waste
activated sludge (WAS) at plants with secondary treatment (see mix()).
"""

P = {
    # --- sludge composition (raw captured sludge)
    "vs_frac_raw": (0.75, 0.65, 0.80, "ASSUMPTION: raw primary/mixed sludge; literature mean over all sludges 0.57 (Bonfiglioli)"),
    "cod_per_vs": (1.5, 1.42, 1.6, "ASSUMPTION: g COD per g VS (1.42 for biomass)"),
    "n_frac_ds": (0.0485, 0.032, 0.083, "Bonfiglioli et al., Fig. 4 (mean, range)"),
    "p_frac_ds": (0.0377, 0.02, 0.05, "Bonfiglioli et al., Fig. 8 (single value); range ASSUMPTION"),
    "lhv_per_vs": (21.0, 19.0, 23.0, "ASSUMPTION: GJ per t VS; gives 12-16 GJ/t DS at 57-75% VS (Bonfiglioli)"),
    # --- secondary (waste activated) sludge, blended with primary sludge by dry mass
    "with_secondary": (1, 1, 1, "plant has secondary (activated sludge) treatment; HydroWASTE LEVEL"),
    "was_yield_per_cod": (0.55, 0.40, 0.70, "Elawwad et al. 2017 (Gabal El-Asfar, 2016): 32.6 t/d DAF float per 56.6 t/d COD passing primary settling = 0.58; range ASSUMPTION"),
    "was_vs_frac": (0.73, 0.65, 0.85, "Elawwad et al. 2017: MLVSS/MLSS 953/1312 at Gabal El-Asfar; range ASSUMPTION"),
    "was_cod_per_vs": (1.42, 1.35, 1.48, "biomass stoichiometry (C5H7NO2: 1.42 g COD per g VSS)"),
    "was_vs_destruction": (0.30, 0.20, 0.40, "ASSUMPTION: WAS digests less than primary sludge; digesters treating mixed sludge reach 30-50% overall (Appels et al. 2008)"),
    "was_n_frac_ds": (0.06, 0.04, 0.08, "ASSUMPTION: biomass ~12% N of VSS (C5H7NO2) diluted by inert solids"),
    "was_p_frac_ds": (0.025, 0.015, 0.04, "ASSUMPTION: 1.5-2.5% P in biomass without enhanced P removal; up to 4% with chemical or biological P removal"),
    "cake_ds": (0.25, 0.23, 0.30, "Ghazy et al. 2009: Gabal El-Asfar cake 23-30% DS"),
    # --- digestion
    "vs_destruction": (0.50, 0.38, 0.60, "38% = US 40 CFR 503.33 minimum; typical upper ASSUMPTION"),
    "ch4_nm3_per_kg_cod": (0.35, 0.35, 0.35, "stoichiometric yield at 0 C, 1 atm (Metcalf & Eddy 2003)"),
    "ch4_mj_per_nm3": (35.8, 35.8, 35.8, "lower heating value 50 MJ/kg x 0.716 kg/Nm3"),
    "chp_elec": (0.395, 0.35, 0.44, "biogas CHP engines; 0.44 = units installed at Gabal El-Asfar in 2024 (INNIO Jenbacher: 14.6 MWe, 65.9% total efficiency)"),
    "ch4_loss": (0.0425, 0.01, 0.075, "Scheutz & Fredenslund 2019 Waste Manage. 97, 38-46 (23 biogas plants)"),
    "n_to_cake_digested": (0.6, 0.5, 0.8, "ASSUMPTION: share of sludge N kept in digested cake (rest to reject water)"),
    # --- biomethane for buses
    "upgrade_kwh_per_kg_ch4": (1.3, 1.2, 1.4, "VALORGAS D5.3 (2012): 1.2-1.4 kWh/kg upgraded and compressed to 250 bar (Kalmari farm)"),
    "ch4_slip": (0.01, 0.001, 0.02, "Persson et al. 2006, IEA Bioenergy Task 37: methane slip of upgrading technologies"),
    "cng_energy_penalty": (1.46, 1.46, 1.46, "CIVITAS: CNG bus uses 46% more energy per km than a diesel bus"),
    "diesel_mj_per_l": (35.78, 35.78, 35.78, "US DOE Alternative Fuels Data Center, fuel properties"),
    "diesel_kgco2e_per_mj": (0.094, 0.094, 0.094, "Directive (EU) 2018/2001 (RED II), Annex V fossil fuel comparator 94 g CO2e/MJ"),
    # --- land application
    "ef1_n2o": (0.010, 0.002, 0.018, "IPCC 2019 Refinement Vol. 4 Ch. 11, Table 11.1"),
    "frac_gasm": (0.21, 0.0, 0.31, "IPCC 2019 Refinement Vol. 4 Ch. 11, Table 11.3: Frac_GASM, organic N volatilised"),
    "ef4_n2o": (0.010, 0.002, 0.018, "IPCC 2019 Refinement Vol. 4 Ch. 11, Table 11.3: EF4"),
    "frac_leach": (0.24, 0.0, 0.73, "IPCC 2019 Refinement Vol. 4 Ch. 11, Table 11.3: Frac_LEACH-(H), wet climates; 0 in dry regions"),
    "ef5_n2o": (0.011, 0.0, 0.020, "IPCC 2019 Refinement Vol. 4 Ch. 11, Table 11.3: EF5"),
    "n_fert_equiv": (0.15, 0.10, 0.30, "Defra RB209 via Taylor (ADAS): digested cake 10-20% of N in first year, ~15% readily available; 0.30 adds residual (ASSUMPTION)"),
    "p_avail_sludge": (0.5, 0.3, 0.8, "ASSUMPTION: plant availability of sludge and digestate P relative to mineral P"),
    "p_avail_char": (0.4, 0.07, 0.66, "Malghani et al. 2025 J. Environ. Qual.: digestate-solids biochar >50% at 400-500 C (66+-8% at 400 C), 6-9% at 600 C"),
    "p_avail_ash": (0.2, 0.05, 0.45, "Romer & Steingrobe 2018 Sustainability 10, 1166: treated ashes 17-49% of TSP (maize); untreated lower"),
    "n_fert_kgco2e_per_kg": (3.0, 1.9, 10.9, "Hoxha & Christensen 2019: urea EU 1.9 to AN China coal 10.9"),
    "p_fert_kgco2e_per_kg": (2.4, 1.75, 2.8, "Ledgard, Boyes & Brentrup 2011 (NZ LCA): SSP 2.4, imported TSP 2.8 kg CO2e/kg P; TSP production only ~1.75"),
    # --- landfill (IPCC 2006 Vol. 5 Ch. 2-3)
    "docf": (0.5, 0.4, 0.6, "IPCC 2006 Vol. 5 Ch. 3, s. 3.2.3 (+-20%)"),
    "f_ch4_lfg": (0.5, 0.5, 0.5, "IPCC 2006 Vol. 5 Ch. 3"),
    "mcf": (0.8, 0.4, 1.0, "IPCC 2006 Vol. 5 Ch. 3, Table 3.1: unmanaged deep 0.8; shallow 0.4; managed 1.0"),
    "ox": (0.0, 0.0, 0.1, "IPCC 2006 Vol. 5 Ch. 3, Table 3.2"),
    "lfg_capture_upgrade": (0.5, 0.3, 0.75, "ASSUMPTION: lifetime gas collection after retrofitting capture at an existing site; 75% upper bound = engineered landfill (Global Methane Initiative LFGE guide Ch. 6)"),
    "extra_haul_km": (20.0, 0.0, 80.0, "ASSUMPTION: extra one-way distance to farmland over the current landfill"),
    "truck_kgco2_per_tkm": (0.10, 0.06, 0.15, "ASSUMPTION: heavy goods vehicle, loaded one way"),
    "haul_usd_tkm": (0.10, 0.05, 0.20, "ASSUMPTION: road freight cost per wet t-km"),
    "spread_usd_t": (5.0, 2.0, 10.0, "ASSUMPTION: loading and spreading per wet t"),
    "tip_usd_t": (10.0, 3.0, 40.0, "World Bank Solid Waste CoP / CCAC 2019: open dumping 2-10, controlled-to-sanitary landfill 10-65 US$/t (low to upper-middle income)"),
    "lfg_usd_tco2e": (30.0, 6.0, 58.0, "USEPA Global Mitigation of Non-CO2 GHGs, Ch. III.1 Landfills: flaring break-even 5-6 (engineered/basic landfill) to 58 (open dump) US$/tCO2e"),
    "lfg_capture": (0.0, 0.0, 0.75, "Global Methane Initiative LFGE guide Ch. 6: max 75-80% engineered"),
    # --- drying
    "solar_ds": (0.60, 0.40, 0.70, "Ghazy et al. 2009: 40-60% DS on beds in 25-40 d; 0.70 greenhouse ASSUMPTION"),
    "solar_kwh_per_t_water": (10.0, 0.0, 40.0, "ASSUMPTION: open beds ~0; greenhouse dryers with turners/fans up to ~40"),
    "c_in_vs": (0.53, 0.50, 0.60, "ASSUMPTION: carbon content of sludge volatile solids (sludge C 30-40% of DS); sets the landfill DOC, 0.39 t C per t mixed raw DS at central values; 0.60 reproduces the IPCC 2006 default DOC of 45% of dry matter"),
    "dry_mcf_raw": (0.05, 0.0, 0.20, "central ASSUMPTION; upper = IPCC 2006 Vol. 5 Table 6.3 shallow anaerobic lagoon 0.2"),
    "dry_mcf_dig": (0.02, 0.0, 0.17, "central ASSUMPTION (cake, 25-40 d); upper = Bai et al. 2023 Water Res. X 19, 100184: open drying pan, 0.17 of sludge COD after 63 wk"),
    "bo_kg_ch4_per_kg_cod": (0.25, 0.25, 0.25, "IPCC 2006 Vol. 5 Ch. 6"),
    "stockpile_n2o_t": (0.003, 0.001, 0.046, "Majumder et al. 2014 J. Environ. Manage. 143, 34-43: stockpiles 12-46 kg CO2e/t dry per year; central ~1 month"),
    "soil_c_retained": (0.0, 0.0, 0.10, "ASSUMPTION: sludge carbon still in soil after 100 yr (no IPCC default; LCAs use ~0.1)"),
    "pyro_elec_kwh_per_t_ds": (120.0, 78.0, 244.0, "Yu et al. 2023 Front. Energy Res. 11, 1123972 (review): 78-244 kWh/t DS"),
    "dryer_kwh_per_t_water": (800.0, 750.0, 900.0, "SUEZ Water Handbook"),
    "fuel_kgco2_per_kwh": (0.202, 0.202, 0.202, "natural gas, IPCC 2006 Vol. 2 default 56.1 t CO2/TJ"),
    "boiler_eff": (0.9, 0.85, 0.95, "ASSUMPTION"),
    "latent_gj_per_t_water": (2.44, 2.44, 2.44, "latent heat of water at 25 C"),
    # --- incineration
    "incin_feed_ds": (0.35, 0.35, 0.45, "Wagner et al. 2020: >=35% DS for autothermal mono-incineration"),
    "incin_elec": (0.20, 0.15, 0.20, "Wagner et al. 2020: ~20% electrical offtake"),
    "incin_heat": (0.70, 0.60, 0.70, "Wagner et al. 2020: ~70% thermal offtake (used first for drying)"),
    "incin_n2o_kg_per_t_ds": (0.99, 0.645, 1.508, "IPCC 2006 Vol. 5 Ch. 5, Tables 5.5-5.6"),
    # --- pyrolysis
    "char_vs_retained": (0.27, 0.16, 0.38, "calibrated so that raw primary sludge (25% ash) gives a char yield of 45% of dry feed; range ASSUMPTION"),
    "c_in_char_organics": (0.75, 0.65, 0.85, "ASSUMPTION: carbon in char organics; raw sludge char then 0.34 C (IPCC 0.35)"),
    "char_org_lhv_gj_per_t": (30.0, 28.0, 32.0, "ASSUMPTION: carbon-rich char organics; raw char then ~13 GJ/t"),
    "char_perm": (0.80, 0.65, 0.89, "IPCC 2019 Refinement, biochar: medium 0.80; low 0.65; high 0.89"),
    "pyro_process_gj_per_t_ds": (1.0, 0.5, 1.5, "ASSUMPTION: reactor heat demand; drying dominates the heat balance"),
    "pyro_feed_ds": (0.90, 0.85, 0.95, "ASSUMPTION: dried feed"),
    "pyro_heat_recovery": (0.70, 0.60, 0.80, "ASSUMPTION: share of volatile energy recoverable as heat"),
    # --- prices (US$)
    "elec_price_usd_kwh": (0.05, 0.03, 0.10, "Egypt, business tariff (GlobalPetrolPrices.com); plants use their country price"),
    "diesel_usd_l": (0.39, 0.39, 1.56, "GlobalPetrolPrices.com: Egypt retail 2026-03-09; world average 1.56 (10 Aug 2026)"),
    "urea_usd_t": (422.7, 407.5, 600.0, "World Bank Pink Sheet Oct 2026: urea 2025 average 422.7, Sep 2026 407.5; high ASSUMPTION"),
    "tsp_usd_t": (577.6, 450.0, 690.0, "World Bank Pink Sheet Oct 2026: TSP 2025 average 577.6, Sep 2026 690.0; low ASSUMPTION"),
    "gas_usd_mmbtu": (6.0, 3.53, 11.96, "World Bank Pink Sheet Oct 2026: Henry Hub 3.53, TTF 11.96 (2025 averages); central ASSUMPTION"),
    "cdr_usd_t": (150.0, 0.0, 320.0, "biochar credits ~US$150 (S&P via carboncredits.com); CDR.fyi 2024 weighted average US$320"),
    "oil_frac_of_vs": (0.0, 0.0, 0.25, "central: all vapours burned for heat (commercial sludge units); high: TCR bio-oil 12-13 wt% of dry digestate (Zimmer et al. 2022, Table 2) ~0.2-0.25 of VS"),
    "oil_lhv_gj_per_t": (35.0, 34.1, 36.3, "Zimmer et al. 2022, Table 2: bio-oil 34.1-36.3 MJ/kg"),
    "fuel_oil_tco2_per_gj": (0.0741, 0.0741, 0.0741, "IPCC 2006 Vol. 2 Table 2.2: gas/diesel oil 74.1 t CO2/TJ"),
    "oil_price_usd_t": (856.0, 514.0, 1198.0, "Zimmer et al. 2022, Table 6: 778 (467-1089) EUR/t x 1.1"),
    "pyro_cap_share": (0.755, 0.70, 0.80, "Zimmer et al. 2022, Table 3: capital 1.079 of 1.429 MEUR/yr (solar configuration)"),
    "pyro_ref_kt_ds": (8.05, 8.05, 8.05, "Zimmer et al. 2022: 3,577 t char/yr at ~44% char yield (2,000 t char = 4,500 t DS)"),
    "scale_exp": (0.7, 0.6, 0.8, "ASSUMPTION: capital cost scaling exponent (six-tenths to 0.8 rule)"),
    "capex_mult": (1.0, 0.7, 1.3, "ASSUMPTION: regional capital-cost multiplier (local vs imported equipment)"),
    "pyro_cost_usd_t_feed": (170.0, 120.0, 250.0, "Zimmer et al. 2022 Energies 15, 2272 (Chile, 8 kt DS/yr): capital+labour 153 (belt) to 178 (solar greenhouse) EUR/t dry feed; x1.1 USD; range ASSUMPTION for scale and country"),
    # --- climate metrics
    "gwp_ch4": (27.0, 27.0, 27.0, "IPCC AR6 WGI Table 7.15: non-fossil CH4"),
    "gwp_n2o": (273.0, 273.0, 273.0, "IPCC AR6 WGI Table 7.15"),
}


def central():
    return {k: v[0] for k, v in P.items()}


def mix(p):
    """Sludge sent to treatment. Primary sludge captures CAPTURE of the influent COD; with secondary treatment,
    WAS is produced from the COD that passes primary settling and is blended with it by dry mass, so the
    functional unit becomes 1 t of mixed raw DS. Idempotent."""
    if p.get("_mixed"):
        return p
    from .data import CAPTURE
    q = dict(p, _mixed=True, prim_vs_frac=p["vs_frac_raw"], prim_cod_per_vs=p["cod_per_vs"], primary_share=1.0)
    if not p.get("with_secondary", 1):
        return q
    ds_p = CAPTURE / (p["cod_per_vs"] * p["vs_frac_raw"])        # t DS per t influent COD
    ds_w = (1.0 - CAPTURE) * p["was_yield_per_cod"]
    f = ds_w / (ds_p + ds_w)
    vs_p, vs_w = (1 - f) * p["vs_frac_raw"], f * p["was_vs_frac"]
    vs = vs_p + vs_w
    q.update(vs_frac_raw=vs, primary_share=1 - f,
             cod_per_vs=(vs_p * p["cod_per_vs"] + vs_w * p["was_cod_per_vs"]) / vs,
             vs_destruction=(vs_p * p["vs_destruction"] + vs_w * p["was_vs_destruction"]) / vs,
             n_frac_ds=(1 - f) * p["n_frac_ds"] + f * p["was_n_frac_ds"],
             p_frac_ds=(1 - f) * p["p_frac_ds"] + f * p["was_p_frac_ds"])
    return q
