"""Determinism — two runs over the same record produce byte-identical artefacts."""

from proofcheck import COMPLIANCE_FILENAME, run_checklist


def test_two_runs_write_byte_identical_compliance_json(canonical_chain, tmp_path):
    chain = canonical_chain
    outputs = []
    for name in ("first", "second"):
        out_dir = tmp_path / name
        result = run_checklist(
            params=chain.params,
            geometry=chain.geometry,
            analysis=chain.analysis,
            checks=chain.checks,
            fe=chain.fe,
            ga_dxf_path=chain.ga["ga_dxf"],
            out_dir=out_dir,
        )
        outputs.append((result, (out_dir / COMPLIANCE_FILENAME).read_bytes()))

    (first_result, first_bytes), (second_result, second_bytes) = outputs
    assert first_bytes == second_bytes
    assert first_result == second_result
    # and both replays match the session-fixture original
    assert first_bytes == (chain.out_dir / COMPLIANCE_FILENAME).read_bytes()
