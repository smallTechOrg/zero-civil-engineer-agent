"""Deterministic catalogue selection (the three normative doc cases)."""

from components.m00004_box_culvert import catalog


def test_catalog_has_fifteen_configs_each_with_full_bar_schedule():
    configs = catalog.all_configs()
    assert len(configs) == 15
    for c in configs:
        assert set(c["bars"]) == {
            "a1", "a2", "b", "c", "d", "e", "f1", "f2", "g1", "g2", "g3", "h"
        }
        for bar in c["bars"].values():
            assert bar["dia_mm"] > 0 and bar["spacing_mm"] > 0


def test_meta_marks_the_subset_provisional():
    meta = catalog.meta()
    assert meta["status"] == "PROVISIONAL"
    # the bar schedule is explicitly flagged as a demonstration set, not transcribed
    assert "PROVISIONAL" in meta["bars_status"]


def test_exact_hit_selects_f2_4x4_with_no_flags():
    config, flags = catalog.select_config(4.0, 4.0, 2.0, 0.0)
    assert config["id"] == "F2_4x4"
    assert config["thickness_cm"] == 50  # PROVISIONAL catalogue thickness
    assert config["haunch_mm"] == 450
    assert flags == []


def test_nearest_config_note_for_non_standard_box():
    # 3.5x3.5, fill 1.2 -> enclosing 2 m fill tier + 4x4 box = F2_4x4, nearest note
    config, flags = catalog.select_config(3.5, 3.5, 1.2, 0.0)
    assert config["id"] == "F2_4x4"
    assert any("nearest standard config F2_4x4" in f for f in flags)  # PROVISIONAL note
    # fill 1.2 <= 2 so NO fill-exceeds flag
    assert not any("exceeds digitized range (0-2 m)" in f for f in flags)


def test_out_of_catalogue_carries_fill_box_and_surcharge_flags():
    config, flags = catalog.select_config(7.0, 7.0, 3.0, 10.0)
    assert config["id"] == "F2_6x6"  # 6x6 / 2 m tier
    text = " || ".join(flags)
    assert "fill 3 m exceeds digitized range (0-2 m)" in text          # PROVISIONAL fill
    assert "box 7x7 m exceeds digitized range (<=6x6 m)" in text       # PROVISIONAL box
    assert "surcharge 10 kN/m^2 not covered" in text                   # PROVISIONAL surcharge


def test_fill_tier_is_enclosing_conservative():
    # cushion 0.4 -> smallest tier >= 0.4 is 1 m
    config, _ = catalog.select_config(2.0, 2.0, 0.4, 0.0)
    assert config["fill_m"] == 1.0
