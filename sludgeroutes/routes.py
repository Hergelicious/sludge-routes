"""Energy, greenhouse-gas, carbon-storage and nutrient balance of sludge routes.

Basis: one tonne of dry solids of raw captured sludge (t DS). Emissions are t CO2-eq per t DS, positive = emitted,
negative = avoided. Biogenic CO2 from sludge carbon is not counted (IPCC convention); carbon kept in biochar is
reported separately as storage.
"""
from dataclasses import dataclass, field

from .params import central, mix

KWH_PER_GJ = 277.78
CH4_KG_PER_NM3 = 0.716


@dataclass
class Result:
    route: str
    elec_mwh: float = 0.0                 # net electricity exported (+) or imported (-)
    heat_surplus_gj: float = 0.0          # recovered heat left after on-site use (no credit given)
    ghg: dict = field(default_factory=dict)
    n_avail_kg: float = 0.0               # mineral-N equivalent returned to soil
    p_total_kg: float = 0.0               # P leaving in a product that reaches land
    p_avail_kg: float = 0.0               # plant-available P returned
    char_t: float = 0.0
    oil_t: float = 0.0
    notes: str = ""

    def total(self):
        return sum(self.ghg.values())


# ---------------------------------------------------------------- building blocks
def _digest(p, ds=1.0):
    """Anaerobic digestion of raw sludge. Returns methane produced (Nm3), digestate DS and VS (t)."""
    vs = p["vs_frac_raw"] * ds
    vs_d = p["vs_destruction"] * vs
    ch4 = p["ch4_nm3_per_kg_cod"] * vs_d * p["cod_per_vs"] * 1000.0
    return ch4, ds - vs_d, vs - vs_d


def _ch4_t(nm3):
    return nm3 * CH4_KG_PER_NM3 / 1000.0


def _water(ds_t, frac_from, frac_to):
    """Water evaporated (t) to take ds_t of solids from one dry-solids fraction to another."""
    if frac_to <= frac_from:
        return 0.0
    return ds_t * ((1 - frac_from) / frac_from - (1 - frac_to) / frac_to)


def _land(p, r, ds, vs, n_kg, p_kg, p_avail):
    """Land application of cake, digestate or char: direct N2O and fertiliser offsets."""
    n2o_n = n_kg * (p["ef1_n2o"] + p["frac_gasm"] * p["ef4_n2o"] + p["frac_leach"] * p["ef5_n2o"])
    r.ghg["land N2O"] = n2o_n * 44 / 28 * p["gwp_n2o"] / 1000.0    # direct + indirect (IPCC 2019, Ch. 11)
    r.n_avail_kg = n_kg * p["n_fert_equiv"]
    r.p_total_kg = p_kg
    r.p_avail_kg = p_kg * p_avail
    r.ghg["fertiliser offset"] = -(r.n_avail_kg * p["n_fert_kgco2e_per_kg"]
                                   + r.p_avail_kg * p["p_fert_kgco2e_per_kg"]) / 1000.0


def _landfill(p, r, ds, vs, vs_raw):
    """IPCC 2006 first-order-decay, ultimate yield. Degradable organic carbon = the carbon in the volatile solids
    that reach the landfill (consistent with the sludge carbon used elsewhere; the IPCC default of 40-50% of dry
    matter corresponds to the upper end of the carbon-content range)."""
    doc = p["c_in_vs"] * vs
    ch4 = doc * p["docf"] * p["mcf"] * p["f_ch4_lfg"] * 16 / 12 * (1 - p["lfg_capture"]) * (1 - p["ox"])
    r.ghg["landfill CH4"] = ch4 * p["gwp_ch4"]


def _dry(p, r, water_t, heat_avail_gj, solar):
    """Thermal drying, fed first by recovered heat and then by natural gas. Solar drying uses no fuel."""
    if solar or water_t <= 0:
        return heat_avail_gj
    need = water_t * p["dryer_kwh_per_t_water"] / KWH_PER_GJ
    used = min(need, heat_avail_gj)
    gas_kwh = (need - used) * KWH_PER_GJ / p["boiler_eff"]
    r.ghg["drying fuel"] = gas_kwh * p["fuel_kgco2_per_kwh"] / 1000.0
    return heat_avail_gj - used


def _stockpile(p, r, vs, digested):
    """Methane from stacking or air-drying cake (Gabal El-Asfar stacks cake to 40-60% DS before farm use)."""
    mcf = p["dry_mcf_dig"] if digested else p["dry_mcf_raw"]
    cod_t = vs * p["cod_per_vs"]
    r.ghg["open-drying CH4"] = cod_t * mcf * p["bo_kg_ch4_per_kg_cod"] * p["gwp_ch4"]
    r.ghg["stockpile N2O"] = p["stockpile_n2o_t"]


def _solar(p, r, water_t):
    r.elec_mwh -= water_t * p["solar_kwh_per_t_water"] / 1000.0


def _chp(p, r, ch4_nm3, ef):
    gj = ch4_nm3 * p["ch4_mj_per_nm3"] / 1000.0
    r.ghg["CH4 losses"] = _ch4_t(ch4_nm3) * p["ch4_loss"] * p["gwp_ch4"]
    e = gj * (1 - p["ch4_loss"]) * p["chp_elec"] / 3.6
    r.elec_mwh += e
    return e


def _grid(r, ef):
    r.ghg["electricity"] = -r.elec_mwh * ef


# ---------------------------------------------------------------- routes
def route(name, ef, p=None, solar_ds=None):
    p = mix(dict(central() if p is None else p))
    solar_ds = p.get("solar_ds", 0.60) if solar_ds is None else solar_ds
    r = Result(name)
    ds0, vs0 = 1.0, p["vs_frac_raw"]
    n0, p0 = p["n_frac_ds"] * 1000.0, p["p_frac_ds"] * 1000.0
    cake = p["cake_ds"]

    digested = name.startswith("AD")
    if digested:
        ch4, ds, vs = _digest(p)
        n_cake = n0 * p["n_to_cake_digested"]
    else:
        ch4, ds, vs = 0.0, ds0, vs0
        n_cake = n0

    if name.startswith("AD-CHP"):
        _chp(p, r, ch4, ef)
    elif name == "AD-biomethane land":
        kg_ch4 = _ch4_t(ch4) * 1000.0
        r.ghg["CH4 losses"] = kg_ch4 * (p["ch4_loss"] + (1 - p["ch4_loss"]) * p["ch4_slip"]) * p["gwp_ch4"] / 1000.0
        r.elec_mwh -= kg_ch4 * (1 - p["ch4_loss"]) * p["upgrade_kwh_per_kg_ch4"] / 1000.0
        mj = ch4 * (1 - p["ch4_loss"]) * (1 - p["ch4_slip"]) * p["ch4_mj_per_nm3"]
        r.ghg["diesel displaced"] = -mj / p["cng_energy_penalty"] * p["diesel_kgco2e_per_mj"] / 1000.0

    # ---------------- end of pipe
    if name.endswith("land") and "pyro" not in name:
        _land(p, r, ds, vs, n_cake, p0, p["p_avail_sludge"])
        _stockpile(p, r, vs, digested)
        _solar(p, r, _water(ds, cake, p["solar_ds"]))
        if p["soil_c_retained"]:
            r.ghg["soil carbon"] = -vs * p["c_in_vs"] * p["soil_c_retained"] * 44 / 12
        if not digested:
            r.notes = "raw sludge: not stabilised; restricted or banned for farm use in most rules"
    elif name.endswith("landfill"):
        _landfill(p, r, ds, vs, vs0)
        r.p_total_kg = 0.0
    elif "incin" in name:
        solar = "solar" in name
        feed_ds = max(p["incin_feed_ds"], solar_ds if solar else 0.0)
        lhv = p["lhv_per_vs"] * vs
        water_feed = ds * (1 - feed_ds) / feed_ds
        net = lhv - water_feed * p["latent_gj_per_t_water"]
        e = max(net, 0.0) * p["incin_elec"] / 3.6
        heat = max(net, 0.0) * p["incin_heat"]
        r.elec_mwh += e
        if solar:
            _stockpile(p, r, vs, digested)
            _solar(p, r, _water(ds, cake, feed_ds))
        else:
            heat = _dry(p, r, _water(ds, cake, feed_ds), heat, solar=False)
        r.heat_surplus_gj = heat
        r.ghg["incineration N2O"] = ds * p["incin_n2o_kg_per_t_ds"] * p["gwp_n2o"] / 1000.0   # per t dry matter burned
        r.p_total_kg = p0
        r.p_avail_kg = p0 * p["p_avail_ash"]
        r.ghg["fertiliser offset"] = -r.p_avail_kg * p["p_fert_kgco2e_per_kg"] / 1000.0
    elif "pyro" in name:
        solar = "solar" in name
        ash = ds - vs
        org_char = p["char_vs_retained"] * vs
        char = ash + org_char
        c_char = org_char * p["c_in_char_organics"]
        lhv = p["lhv_per_vs"] * vs
        volatiles = lhv - org_char * p["char_org_lhv_gj_per_t"]
        oil_t = p["oil_frac_of_vs"] * vs                       # condensed bio-oil sold as heating-oil substitute
        oil_t = min(oil_t, max(volatiles, 0.0) / p["oil_lhv_gj_per_t"])
        volatiles -= oil_t * p["oil_lhv_gj_per_t"]
        r.oil_t = oil_t
        if oil_t:
            r.ghg["fuel oil displaced"] = -oil_t * p["oil_lhv_gj_per_t"] * p["fuel_oil_tco2_per_gj"]
        residual_water = ds * (1 - p["pyro_feed_ds"]) / p["pyro_feed_ds"]
        heat = (p["pyro_heat_recovery"] * volatiles - p["pyro_process_gj_per_t_ds"] * ds
                - residual_water * p["latent_gj_per_t_water"])
        start = solar_ds if solar else cake
        if solar:
            _stockpile(p, r, vs, digested)
            _solar(p, r, _water(ds, cake, solar_ds))
        r.elec_mwh -= ds * p["pyro_elec_kwh_per_t_ds"] / 1000.0
        heat = _dry(p, r, _water(ds, start, p["pyro_feed_ds"]), max(heat, 0.0), solar=False)
        r.heat_surplus_gj = heat
        r.char_t = char
        r.ghg["biochar storage"] = -c_char * p["char_perm"] * 44 / 12
        r.p_total_kg = p0
        r.p_avail_kg = p0 * p["p_avail_char"]
        r.ghg["fertiliser offset"] = -r.p_avail_kg * p["p_fert_kgco2e_per_kg"] / 1000.0
        r.notes = f"char C content {c_char / char:.2f} (IPCC biosolids default 0.35)"

    _grid(r, ef)
    return r


GABAL_FLOW_M3D = 500_000.0     # the line with a published sludge balance (Elawwad et al. 2017)
GABAL_COD_MG_L = 278.0         # influent COD of the central case (275 mg/L in the 2016 balance)


def raw_ds_t_d(p=None):
    """Raw primary-sludge dry solids (t d-1) at Gabal El-Asfar."""
    from .data import CAPTURE
    p = central() if p is None else p
    cod_kg_d = CAPTURE * GABAL_FLOW_M3D * GABAL_COD_MG_L / 1000.0
    return cod_kg_d / (p.get("prim_cod_per_vs", p["cod_per_vs"]) * p.get("prim_vs_frac", p["vs_frac_raw"])) / 1000.0


def gabal_ds_t_d(p=None):
    """Raw dry solids (t d-1) at Gabal El-Asfar, primary plus secondary sludge."""
    p = mix(central() if p is None else p)
    return raw_ds_t_d(p) / p["primary_share"]


ROUTES = [
    "raw landfill",
    "raw land",
    "AD-CHP land",
    "AD-CHP landfill",
    "AD-biomethane land",
    "AD-CHP solar-dry incin",
    "AD-CHP thermal-dry incin",
    "AD-CHP solar-dry pyro",
    "AD-CHP thermal-dry pyro",
    "raw solar-dry pyro",
    "raw thermal-dry pyro",
    "raw incin",
]
