"""Shared proof-check fixtures — the REAL full chain, no fakes anywhere.

Every fixture runs size_culvert -> analyse_frame -> run_checks -> generate_ga
-> cross_check (anaStruct) -> run_checklist, exactly as the production graph
will. Session-scoped because the FE re-solve is the expensive step and the
chains are read-only for the assertions.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from domain.culvert import CulvertParams
from drawing.ga import generate_ga
from engine import size_culvert
from engine.analysis import analyse_frame
from engine.checks import run_checks
from engine.fe_check import cross_check
from proofcheck import run_checklist

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}


def run_full_chain(out_dir: Path, **overrides) -> SimpleNamespace:
    """The production pipeline, end to end, into one artefact directory."""
    params = CulvertParams(**{**CANONICAL, **overrides})
    sizing = size_culvert(params)
    geometry = sizing.geometry
    analysis = analyse_frame(params, geometry)
    checks = run_checks(analysis, geometry, params)
    ga = generate_ga(geometry, params, out_dir)
    fe = cross_check(params, geometry, analysis, out_dir)
    result = run_checklist(
        params=params,
        geometry=geometry,
        analysis=analysis,
        checks=checks,
        fe=fe,
        ga_dxf_path=ga["ga_dxf"],
        out_dir=out_dir,
    )
    return SimpleNamespace(
        params=params,
        sizing=sizing,
        geometry=geometry,
        analysis=analysis,
        checks=checks,
        ga=ga,
        fe=fe,
        out_dir=out_dir,
        result=result,
    )


@pytest.fixture(scope="session")
def canonical_chain(tmp_path_factory) -> SimpleNamespace:
    """The canonical 4 m x 3 m x 2.5 m box through the whole real chain."""
    return run_full_chain(tmp_path_factory.mktemp("proofcheck-canonical"))


@pytest.fixture(scope="session")
def under_design_chain(tmp_path_factory) -> SimpleNamespace:
    """The demo money-shot: deliberately thin 200 mm top slab, same real chain."""
    return run_full_chain(
        tmp_path_factory.mktemp("proofcheck-under"), top_slab_thickness_mm=200
    )
