"""Proof-check capability — 12-item deterministic checklist, compliance matrix, memo.

Pinned public API (the graph-wiring slice builds against exactly this):

    from proofcheck import run_checklist, ProofCheckResult
    from proofcheck import memo_facts, render_memo, validate_narration
"""

from proofcheck.checklist import (
    COMPLIANCE_FILENAME,
    VERDICT_APPROVAL,
    VERDICT_REVISION,
    ChecklistItem,
    ProofCheckResult,
    run_checklist,
)
from proofcheck.memo import (
    PROOF_MEMO_FILENAME,
    memo_facts,
    render_memo,
    validate_narration,
)

__all__ = [
    "COMPLIANCE_FILENAME",
    "PROOF_MEMO_FILENAME",
    "VERDICT_APPROVAL",
    "VERDICT_REVISION",
    "ChecklistItem",
    "ProofCheckResult",
    "memo_facts",
    "render_memo",
    "run_checklist",
    "validate_narration",
]
