"""Auto-sizing rules in engine/defaults.py — RDSO family proportions, deterministic rounding."""

from engine.defaults import (
    MIN_MEMBER_THICKNESS_MM,
    auto_slab_thickness_mm,
    auto_wall_thickness_mm,
    round_up_to_step,
)


def test_round_up_to_step_rounds_up_to_the_next_50_mm():
    assert round_up_to_step(301.0) == 350.0
    assert round_up_to_step(333.3) == 350.0
    assert round_up_to_step(666.7) == 700.0


def test_round_up_to_step_keeps_exact_multiples_unchanged():
    assert round_up_to_step(400.0) == 400.0
    assert round_up_to_step(300.0) == 300.0


def test_slab_thickness_is_span_over_ten_rounded_up():
    assert auto_slab_thickness_mm(4.0) == 400.0
    assert auto_slab_thickness_mm(8.0) == 800.0
    assert auto_slab_thickness_mm(5.5) == 550.0


def test_slab_thickness_never_drops_below_the_300_mm_floor():
    assert MIN_MEMBER_THICKNESS_MM == 300.0
    assert auto_slab_thickness_mm(1.0) == 300.0
    assert auto_slab_thickness_mm(2.9) == 300.0


def test_wall_thickness_uses_the_governing_opening_over_twelve():
    assert auto_wall_thickness_mm(4.0, 3.0) == 350.0
    assert auto_wall_thickness_mm(1.0, 6.0) == 500.0  # height governs a tall narrow box
    assert auto_wall_thickness_mm(8.0, 1.0) == 700.0  # span governs a wide flat box


def test_wall_thickness_never_drops_below_the_300_mm_floor():
    assert auto_wall_thickness_mm(1.0, 1.0) == 300.0
