"""Central results quoted in the paper (fast; no Monte Carlo)."""
import pytest

from sludgeroutes.interventions import grid_tipping, plant_choice, plant_table
from sludgeroutes.plants import plant_totals
from sludgeroutes.routes import gabal_ds_t_d, route

EF_EGY = 0.563


def test_gabal_routes():
    assert route("raw landfill", EF_EGY).total() == pytest.approx(2.84, abs=0.005)
    assert route("AD-CHP land", EF_EGY).total() == pytest.approx(0.017, abs=0.002)
    assert route("AD-CHP solar-dry pyro", EF_EGY).total() == pytest.approx(-0.359, abs=0.002)
    assert route("AD-CHP thermal-dry pyro", EF_EGY).total() == pytest.approx(-0.286, abs=0.002)
    assert route("AD-CHP thermal-dry incin", EF_EGY).total() == pytest.approx(-0.232, abs=0.002)
    assert gabal_ds_t_d() == pytest.approx(104.2, abs=0.1)


def test_global_totals():
    d = plant_totals()
    assert len(d) == 278
    assert d.ds_kt_yr.sum() / 1e3 == pytest.approx(4.52, abs=0.01)
    assert d.saving_kt.sum() / 1e3 == pytest.approx(4.05, abs=0.01)
    assert d.step_lf_kt.sum() / 1e3 == pytest.approx(2.52, abs=0.01)


def test_interventions():
    t = plant_table()
    assert t.alone_V_kt.sum() / 1e3 == pytest.approx(2.52, abs=0.01)
    assert t.alone_G_kt.sum() / 1e3 == pytest.approx(1.49, abs=0.01)
    assert t.alone_P_kt.sum() / 1e3 == pytest.approx(4.01, abs=0.01)
    pc = plant_choice(carbon_values=(100, 320))
    assert pc.save_100_kt.sum() / 1e3 == pytest.approx(2.52, abs=0.01)
    assert pc.save_320_kt.sum() / 1e3 == pytest.approx(3.10, abs=0.01)


def test_grid_tipping():
    assert grid_tipping(warm=True)["current_neutral"] == pytest.approx(0.591, abs=0.002)
    assert grid_tipping(warm=True)["digester_pays"] == pytest.approx(0.364, abs=0.002)


def test_value_of_information_runs():
    from sludgeroutes.decisions import plant_voi
    d = plant_voi(n_p=4, n_f=4, carbon_value=100.0)
    from sludgeroutes.data import load_plants
    assert len(d) == len(load_plants()) and (d.evpi_all_usd_yr >= -1e-6).all() and (d.evpi_facts_usd_yr >= -1e-6).all()


def test_unscreened_inventory():
    from sludgeroutes.data import population
    with population("all"):
        d = plant_totals()
    assert len(d) == 364 and d.saving_kt.sum() / 1e3 == pytest.approx(5.56, abs=0.01)
