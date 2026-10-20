// sludgeroutes model, JavaScript port of sludgeroutes/routes.py, econ.py and interventions.py (v1.0.0).
// Same parameters, same equations; checked against the Python code on the test vectors in tool/parity.json.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.SludgeModel = factory();
})(typeof self !== "undefined" ? self : this, function () {
  const KWH_PER_GJ = 277.78, CH4_KG_PER_NM3 = 0.716;
  const N_IN_UREA = 0.46, P_IN_TSP = 0.46 * 62 / 142, MMBTU_PER_KWH = 0.003412;
  const ROUTES = ["raw landfill", "raw land", "AD-CHP land", "AD-CHP landfill", "AD-biomethane land",
    "AD-CHP solar-dry incin", "AD-CHP thermal-dry incin", "AD-CHP solar-dry pyro", "AD-CHP thermal-dry pyro",
    "raw solar-dry pyro", "raw thermal-dry pyro", "raw incin"];
  let CAPTURE = 0.59;
  let PTABLE = null;

  function init(params) { CAPTURE = params.CAPTURE; PTABLE = params.P; }
  function central() { const c = {}; for (const k in PTABLE) c[k] = PTABLE[k][0]; return c; }

  function mix(p) {
    if (p._mixed) return p;
    const q = Object.assign({}, p, { _mixed: true, prim_vs_frac: p.vs_frac_raw, prim_cod_per_vs: p.cod_per_vs, primary_share: 1.0 });
    if (!(p.with_secondary === undefined ? 1 : p.with_secondary)) return q;
    const ds_p = CAPTURE / (p.cod_per_vs * p.vs_frac_raw);
    const ds_w = (1 - CAPTURE) * p.was_yield_per_cod;
    const f = ds_w / (ds_p + ds_w);
    const vs_p = (1 - f) * p.vs_frac_raw, vs_w = f * p.was_vs_frac, vs = vs_p + vs_w;
    q.vs_frac_raw = vs; q.primary_share = 1 - f;
    q.cod_per_vs = (vs_p * p.cod_per_vs + vs_w * p.was_cod_per_vs) / vs;
    q.vs_destruction = (vs_p * p.vs_destruction + vs_w * p.was_vs_destruction) / vs;
    q.n_frac_ds = (1 - f) * p.n_frac_ds + f * p.was_n_frac_ds;
    q.p_frac_ds = (1 - f) * p.p_frac_ds + f * p.was_p_frac_ds;
    return q;
  }

  const water = (ds, f0, f1) => f1 <= f0 ? 0 : ds * ((1 - f0) / f0 - (1 - f1) / f1);

  function route(name, ef, p0) {
    const p = mix(Object.assign({}, p0 || central()));
    const solar_ds = p.solar_ds;
    const r = { route: name, elec_mwh: 0, heat_surplus_gj: 0, ghg: {}, n_avail_kg: 0, p_total_kg: 0, p_avail_kg: 0, char_t: 0, oil_t: 0 };
    const vs0 = p.vs_frac_raw, n0 = p.n_frac_ds * 1000, p0k = p.p_frac_ds * 1000, cake = p.cake_ds;
    const digested = name.startsWith("AD");
    let ch4 = 0, ds = 1.0, vs = vs0, n_cake = n0;
    if (digested) {
      const vs_d = p.vs_destruction * vs0;
      ch4 = p.ch4_nm3_per_kg_cod * vs_d * p.cod_per_vs * 1000;
      ds = 1 - vs_d; vs = vs0 - vs_d; n_cake = n0 * p.n_to_cake_digested;
    }
    if (name.startsWith("AD-CHP")) {
      const gj = ch4 * p.ch4_mj_per_nm3 / 1000;
      r.ghg["CH4 losses"] = ch4 * CH4_KG_PER_NM3 / 1000 * p.ch4_loss * p.gwp_ch4;
      r.elec_mwh += gj * (1 - p.ch4_loss) * p.chp_elec / 3.6;
    } else if (name === "AD-biomethane land") {
      const kg = ch4 * CH4_KG_PER_NM3;
      r.ghg["CH4 losses"] = kg * (p.ch4_loss + (1 - p.ch4_loss) * p.ch4_slip) * p.gwp_ch4 / 1000;
      r.elec_mwh -= kg * (1 - p.ch4_loss) * p.upgrade_kwh_per_kg_ch4 / 1000;
      const mj = ch4 * (1 - p.ch4_loss) * (1 - p.ch4_slip) * p.ch4_mj_per_nm3;
      r.ghg["diesel displaced"] = -mj / p.cng_energy_penalty * p.diesel_kgco2e_per_mj / 1000;
    }
    const land = () => {
      const n2o_n = n_cake * (p.ef1_n2o + p.frac_gasm * p.ef4_n2o + p.frac_leach * p.ef5_n2o);
      r.ghg["land N2O"] = n2o_n * 44 / 28 * p.gwp_n2o / 1000;
      r.n_avail_kg = n_cake * p.n_fert_equiv; r.p_total_kg = p0k; r.p_avail_kg = p0k * p.p_avail_sludge;
      r.ghg["fertiliser offset"] = -(r.n_avail_kg * p.n_fert_kgco2e_per_kg + r.p_avail_kg * p.p_fert_kgco2e_per_kg) / 1000;
    };
    const stockpile = () => {
      const mcf = digested ? p.dry_mcf_dig : p.dry_mcf_raw;
      r.ghg["open-drying CH4"] = vs * p.cod_per_vs * mcf * p.bo_kg_ch4_per_kg_cod * p.gwp_ch4;
      r.ghg["stockpile N2O"] = p.stockpile_n2o_t;
    };
    const solar = (w) => { r.elec_mwh -= w * p.solar_kwh_per_t_water / 1000; };
    const dry = (w, heat, isSolar) => {
      if (isSolar || w <= 0) return heat;
      const need = w * p.dryer_kwh_per_t_water / KWH_PER_GJ, used = Math.min(need, heat);
      const gas_kwh = (need - used) * KWH_PER_GJ / p.boiler_eff;
      r.ghg["drying fuel"] = gas_kwh * p.fuel_kgco2_per_kwh / 1000;
      return heat - used;
    };
    if (name.endsWith("land") && !name.includes("pyro")) {
      land(); stockpile(); solar(water(ds, cake, p.solar_ds));
      if (p.soil_c_retained) r.ghg["soil carbon"] = -vs * p.c_in_vs * p.soil_c_retained * 44 / 12;
    } else if (name.endsWith("landfill")) {
      const doc = p.c_in_vs * vs;                       // carbon in the VS that reach the landfill
      const m = doc * p.docf * p.mcf * p.f_ch4_lfg * 16 / 12 * (1 - p.lfg_capture) * (1 - p.ox);
      r.ghg["landfill CH4"] = m * p.gwp_ch4; r.p_total_kg = 0;
    } else if (name.includes("incin")) {
      const isSolar = name.includes("solar");
      const feed_ds = Math.max(p.incin_feed_ds, isSolar ? solar_ds : 0);
      const lhv = p.lhv_per_vs * vs, wf = ds * (1 - feed_ds) / feed_ds;
      const net = lhv - wf * p.latent_gj_per_t_water;
      r.elec_mwh += Math.max(net, 0) * p.incin_elec / 3.6;
      let heat = Math.max(net, 0) * p.incin_heat;
      if (isSolar) { stockpile(); solar(water(ds, cake, feed_ds)); } else heat = dry(water(ds, cake, feed_ds), heat, false);
      r.heat_surplus_gj = heat;
      r.ghg["incineration N2O"] = ds * p.incin_n2o_kg_per_t_ds * p.gwp_n2o / 1000;   // per t dry matter burned
      r.p_total_kg = p0k; r.p_avail_kg = p0k * p.p_avail_ash;
      r.ghg["fertiliser offset"] = -r.p_avail_kg * p.p_fert_kgco2e_per_kg / 1000;
    } else if (name.includes("pyro")) {
      const isSolar = name.includes("solar");
      const ash = ds - vs, org = p.char_vs_retained * vs, char = ash + org, c_char = org * p.c_in_char_organics;
      let volatiles = p.lhv_per_vs * vs - org * p.char_org_lhv_gj_per_t;
      let oil = Math.min(p.oil_frac_of_vs * vs, Math.max(volatiles, 0) / p.oil_lhv_gj_per_t);
      volatiles -= oil * p.oil_lhv_gj_per_t; r.oil_t = oil;
      if (oil) r.ghg["fuel oil displaced"] = -oil * p.oil_lhv_gj_per_t * p.fuel_oil_tco2_per_gj;
      const residual = ds * (1 - p.pyro_feed_ds) / p.pyro_feed_ds;
      let heat = p.pyro_heat_recovery * volatiles - p.pyro_process_gj_per_t_ds * ds - residual * p.latent_gj_per_t_water;
      const start = isSolar ? solar_ds : cake;
      if (isSolar) { stockpile(); solar(water(ds, cake, solar_ds)); }
      r.elec_mwh -= ds * p.pyro_elec_kwh_per_t_ds / 1000;
      heat = dry(water(ds, start, p.pyro_feed_ds), Math.max(heat, 0), false);
      r.heat_surplus_gj = heat; r.char_t = char;
      r.ghg["biochar storage"] = -c_char * p.char_perm * 44 / 12;
      r.p_total_kg = p0k; r.p_avail_kg = p0k * p.p_avail_char;
      r.ghg["fertiliser offset"] = -r.p_avail_kg * p.p_fert_kgco2e_per_kg / 1000;
    }
    r.ghg["electricity"] = -r.elec_mwh * ef;
    r.total = Object.values(r.ghg).reduce((a, b) => a + b, 0);
    return r;
  }

  function value(name, ef, p0, carbon) {
    const p = mix(Object.assign({}, p0 || central()));
    carbon = carbon === undefined || carbon === null ? p.cdr_usd_t : carbon;
    const r = route(name, ef, p);
    const v = { electricity: r.elec_mwh * 1000 * p.elec_price_usd_kwh };
    if ("diesel displaced" in r.ghg) v.diesel = -r.ghg["diesel displaced"] * 1000 / p.diesel_kgco2e_per_mj / p.diesel_mj_per_l * p.diesel_usd_l;
    v.fertiliser = r.n_avail_kg * p.urea_usd_t / 1000 / N_IN_UREA + r.p_avail_kg * p.tsp_usd_t / 1000 / P_IN_TSP;
    if ("drying fuel" in r.ghg) v["drying gas"] = -(r.ghg["drying fuel"] * 1000 / p.fuel_kgco2_per_kwh) * MMBTU_PER_KWH * p.gas_usd_mmbtu;
    if (r.oil_t) v["bio-oil"] = r.oil_t * p.oil_price_usd_t;
    if ("biochar storage" in r.ghg) v["CDR credits"] = -r.ghg["biochar storage"] * carbon;
    const market = Object.values(v).reduce((a, b) => a + b, 0);
    return { market, social: market - (r.total - (r.ghg["biochar storage"] || 0)) * carbon, parts: v, r };
  }

  function pyroCostPerTFeed(feed_kt_yr, p) {
    p = p || central();
    const q = Math.min(Math.max(feed_kt_yr, 2), 50) / p.pyro_ref_kt_ds;
    return p.pyro_cost_usd_t_feed * (p.capex_mult * p.pyro_cap_share * Math.pow(q, p.scale_exp - 1) + (1 - p.pyro_cap_share));
  }

  // ---- interventions on a plant described by `site`:
  // {ef, digesting, warm, fate:{land, landfill, incin}, lam (share of landfilled sludge farmland can take)}
  const STATES = ["", "V", "G", "P", "VG", "VP", "GP", "VGP"];
  const has = (s, i) => s.includes(i);

  function stateGhg(s, site, p) {
    const dig = site.digesting || has(s, "A");
    const pre = dig ? "AD-CHP " : "raw ";
    if (has(s, "P")) {
      const opts = [pre + "thermal-dry pyro"].concat(site.warm ? [pre + "solar-dry pyro"] : []);
      return Math.min(...opts.map(o => route(o, site.ef, p).total));
    }
    const f = site.fate;
    const land = route(pre + "land", site.ef, p).total;
    const q = has(s, "G") ? Object.assign({}, p, { lfg_capture: Math.max(p.lfg_capture, p.lfg_capture_upgrade) }) : p;
    let landfill = route(pre + "landfill", site.ef, q).total;
    const incin = route(dig ? "AD-CHP thermal-dry incin" : "raw incin", site.ef, p).total;
    if (has(s, "V")) {
      const haul = (1 / p.cake_ds) * p.extra_haul_km * p.truck_kgco2_per_tkm / 1000;
      const lam = site.lam === undefined ? 1 : site.lam;
      landfill = lam * (land + haul) + (1 - lam) * landfill;
    }
    return f.land * land + f.landfill * landfill + f.incin * incin;
  }

  function stateCostParts(s, site, p) {
    const m = mix(Object.assign({}, p));
    const dig = site.digesting;
    const pre = dig ? "AD-CHP " : "raw ";
    const f = site.fate, ef = site.ef;
    const inc = dig ? "AD-CHP thermal-dry incin" : "raw incin";
    const val = (n) => value(n, ef, p, 0).market;
    const v_cur = f.land * val(pre + "land") + f.landfill * val(pre + "landfill") + f.incin * val(inc);
    const wet = 1 / p.cake_ds, fee = f.landfill * wet * p.tip_usd_t;
    if (has(s, "P")) {
      const opts = [pre + "thermal-dry pyro"].concat(site.warm ? [pre + "solar-dry pyro"] : []);
      let best = opts[0], bt = Infinity;
      for (const o of opts) { const t = route(o, ef, p).total; if (t < bt) { bt = t; best = o; } }
      const feed = 1 - (dig ? m.vs_destruction * m.vs_frac_raw : 0);
      return { other: -(val(best) - v_cur) - fee, feed };
    }
    let v_new = f.land * val(pre + "land") + f.incin * val(inc), cost = 0;
    const lam = has(s, "V") ? (site.lam === undefined ? 1 : site.lam) : 0;
    if (lam) {
      v_new += lam * f.landfill * val(pre + "land");
      cost += lam * (f.landfill * wet * (p.extra_haul_km * p.haul_usd_tkm + p.spread_usd_t) - fee);
    }
    if (lam < 1) {
      v_new += (1 - lam) * f.landfill * val(pre + "landfill");
      if (has(s, "G")) {
        const avoided = stateGhg(s.replace("G", ""), site, p) - stateGhg(s, site, p);
        cost += p.lfg_usd_tco2e * avoided;
      }
    }
    return { other: cost - (v_new - v_cur), feed: 0 };
  }

  // Evaluate every combination of V, G, P for a plant: emissions, net cost per t DS, per-tonne costs, best choice.
  function evaluate(site, p, ds_kt_yr, carbonValues) {
    p = p || central();
    const states = STATES.filter(s => site.landOk === false ? !has(s, "V") : true);
    const e = {}, cost = {};
    for (const s of states) {
      e[s] = stateGhg(s, site, p);
      const c = stateCostParts(s, site, p);
      cost[s] = c.other + (c.feed ? pyroCostPerTFeed(ds_kt_yr * c.feed, p) * c.feed : 0);
    }
    const base = e[""];
    const perT = {};
    for (const i of ["V", "G", "P"]) if (i in e && base - e[i] > 1e-6) perT[i] = cost[i] / (base - e[i]);
    if ("V" in e && "P" in e && e.V - e.P > 1e-6) perT.P_after_V = (cost.P - cost.V) / (e.V - e.P);
    if ("G" in e && "P" in e && e.G - e.P > 1e-6) perT.P_after_G = (cost.P - cost.G) / (e.G - e.P);
    const choice = {};
    for (const cv of carbonValues) {
      let best = "", bv = -Infinity;
      for (const s of states) { const v = cv * (base - e[s]) - cost[s]; if (v > bv + 1e-9) { bv = v; best = s; } }
      choice[cv] = { state: best || "-", save_t_per_t: base - e[best], cost_usd_per_t: cost[best], net_usd_per_t: bv };
    }
    return { emissions: e, cost, base, perT, choice, states };
  }

  // Triangular draws over the parameter ranges (as uncertainty.draws), with a small deterministic PRNG for repeatability.
  function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function triangular(u, lo, mode, hi) {
    const c = (mode - lo) / (hi - lo);
    return u < c ? lo + Math.sqrt(u * (hi - lo) * (mode - lo)) : hi - Math.sqrt((1 - u) * (hi - lo) * (hi - mode));
  }
  function draw(rand) {
    const d = {};
    for (const k in PTABLE) { const [c, lo, hi] = PTABLE[k]; d[k] = hi === lo ? c : triangular(rand(), lo, Math.min(Math.max(c, lo), hi), hi); }
    return d;
  }

  return { init, central, mix, route, value, pyroCostPerTFeed, stateGhg, stateCostParts, evaluate, draw, mulberry32, ROUTES, STATES };
});
