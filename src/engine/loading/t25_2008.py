"""IRS Bridge Rules 25t Loading-2008 — transcribed EUDL tables + CDA rules (BG, single track).

TRANSCRIPTION FOR DEMO — verify each value against the cited source PDF before
demo day (IR engineer pre-review required per spec).

Provenance and confidence, row by row:

- Rows with ``needs_verification=False`` (loaded length <= 2.0 m) equal exactly
  2 x the 245.25 kN (25.0 t) axle load — the published-table convention for a
  single governing axle (EUDL for BM = 8*M_max/L, EUDL for shear = 2*V_max) —
  and are independent of any wagon-geometry assumption.
- Rows with ``needs_verification=True`` were derived by exact influence-line
  moving-load analysis of the governing 25t-axle wagon train (axle 245.25 kN;
  CASNUB bogie wheelbase 2.000 m; bogie centres 6.524 m; wagon length over
  couplers 10.713 m -> trailing intensity ~91.6 kN/m), NOT read digit-for-digit
  from the published appendix. They satisfy the published tables' engineering
  invariants (monotone non-decreasing; bounded below by the governing axle
  group; asymptote to train-load intensity x length) but MUST be checked
  against the source PDF before demo day.
- The CDA formula and its fill reduction are encoded from the Bridge Rules
  clauses cited below; the fill-reduction clause number itself is flagged for
  verification.
"""

from engine.loading.base import (
    EudlRow,
    LoadingStandard,
    interpolate_eudl,
    register_loading_standard,
    validate_eudl_table,
)

AXLE_LOAD_KN = 245.25  # 25.0 t x 9.81 m/s^2 — the standard's namesake axle load

SOURCE_DOCUMENT = (
    "IRS Bridge Rules — Rules Specifying the Loads for Design of Super-Structure and "
    "Sub-Structure of Bridges and for Assessment of the Strength of Existing Bridges, "
    "Government of India, Ministry of Railways (official PDF: iricen.gov.in / RDSO)"
)
SOURCE_TABLE = (
    "IRS Bridge Rules Appendix for 25t Loading-2008 — 'EUDL in kN (t) on each track "
    "and CDA values', Broad Gauge, single track"
)
SOURCE_PAGES = (
    "appendix pages for the 25t Loading-2008 EUDL/CDA tables — page numbers not yet "
    "verified against the source PDF (see per-row needs_verification flags)"
)
ACS_LEVEL = (
    "ACS (Advance Correction Slip) level: Bridge Rules reprint incorporating the "
    "correction slip that annexed the 25t Loading-2008 appendices (c. 2009, believed "
    "ACS No. 47 — slip number pending verification)"
)
CITATION_CDA_FORMULA = (
    "IRS Bridge Rules Cl. 2.4.1.1 — CDA = 0.15 + 8/(6+L), subject to a maximum of "
    "1.0 (BG, single track; L = loaded length in m)"
)
CITATION_CDA_FILL = (
    "IRS Bridge Rules Cl. 2.4.4 (clause number pending verification) — CDA for pipe "
    "culverts, arch bridges, concrete slabs and concrete girders with fill: full CDA "
    "for fill depth d < 0.9 m; for d >= 0.9 m multiply the CDA by (2 - d)/2, not "
    "less than zero (no dynamic augment at d >= 2.0 m). Fill depth taken as the "
    "cushion above the top slab — conservative, as the ballast below sleeper level "
    "is not counted towards the reduction"
)
VERIFY_BANNER = (
    "TRANSCRIPTION FOR DEMO — verify each value against the cited source PDF before "
    "demo day (IR engineer pre-review required per spec)"
)

# CDA constants per Cl. 2.4.1.1 and the fill-reduction clause above.
CDA_BASE = 0.15
CDA_NUMERATOR = 8.0
CDA_LENGTH_OFFSET_M = 6.0
CDA_MAX = 1.0
CDA_FILL_REDUCTION_FROM_M = 0.9
CDA_FILL_NO_AUGMENT_M = 2.0

# EUDL for bending moment, kN per track (BG), against loaded length L (m).
EUDL_BM_TABLE = validate_eudl_table(
    (
        EudlRow(1.0, 490.5, False),
        EudlRow(1.5, 490.5, False),
        EudlRow(2.0, 490.5, False),
        EudlRow(2.5, 490.5, True),
        EudlRow(3.0, 490.5, True),
        EudlRow(3.5, 500.5, True),
        EudlRow(4.0, 551.8, True),
        EudlRow(4.5, 593.4, True),
        EudlRow(5.0, 649.9, True),
        EudlRow(5.5, 724.5, True),
        EudlRow(6.0, 786.8, True),
        EudlRow(6.5, 839.4, True),
        EudlRow(7.0, 884.6, True),
        EudlRow(7.5, 923.7, True),
        EudlRow(8.0, 971.4, True),
        EudlRow(8.5, 1027.6, True),
        EudlRow(9.0, 1077.8, True),
        EudlRow(9.5, 1122.9, True),
        EudlRow(10.0, 1163.6, True),
        EudlRow(11.0, 1234.3, True),
        EudlRow(12.0, 1293.4, True),
        EudlRow(13.0, 1343.7, True),
        EudlRow(14.0, 1410.6, True),
        EudlRow(15.0, 1479.9, True),
        EudlRow(16.0, 1543.0, True),
        EudlRow(17.0, 1623.4, True),
        EudlRow(18.0, 1695.0, True),
        EudlRow(19.0, 1784.7, True),
        EudlRow(20.0, 1872.3, True),
        EudlRow(21.0, 1967.7, True),
        EudlRow(22.0, 2054.7, True),
        EudlRow(23.0, 2135.5, True),
        EudlRow(24.0, 2230.2, True),
        EudlRow(25.0, 2321.1, True),
        EudlRow(26.0, 2419.9, True),
        EudlRow(27.0, 2518.8, True),
        EudlRow(28.0, 2621.5, True),
        EudlRow(29.0, 2717.2, True),
        EudlRow(30.0, 2817.4, True),
    ),
    table_label="25t-2008 EUDL for bending moment",
)

# EUDL for shear (end shear), kN per track (BG), against loaded length L (m).
EUDL_SHEAR_TABLE = validate_eudl_table(
    (
        EudlRow(1.0, 490.5, False),
        EudlRow(1.5, 490.5, False),
        EudlRow(2.0, 490.5, False),
        EudlRow(2.5, 588.6, True),
        EudlRow(3.0, 654.0, True),
        EudlRow(3.5, 700.7, True),
        EudlRow(4.0, 735.8, True),
        EudlRow(4.5, 796.9, True),
        EudlRow(5.0, 864.4, True),
        EudlRow(5.5, 919.6, True),
        EudlRow(6.0, 965.5, True),
        EudlRow(6.5, 1027.9, True),
        EudlRow(7.0, 1094.7, True),
        EudlRow(7.5, 1152.5, True),
        EudlRow(8.0, 1203.1, True),
        EudlRow(8.5, 1247.7, True),
        EudlRow(9.0, 1287.4, True),
        EudlRow(9.5, 1322.9, True),
        EudlRow(10.0, 1354.9, True),
        EudlRow(11.0, 1422.9, True),
        EudlRow(12.0, 1508.7, True),
        EudlRow(13.0, 1592.1, True),
        EudlRow(14.0, 1688.6, True),
        EudlRow(15.0, 1775.4, True),
        EudlRow(16.0, 1879.0, True),
        EudlRow(17.0, 1973.3, True),
        EudlRow(18.0, 2081.7, True),
        EudlRow(19.0, 2178.6, True),
        EudlRow(20.0, 2265.9, True),
        EudlRow(21.0, 2344.9, True),
        EudlRow(22.0, 2429.4, True),
        EudlRow(23.0, 2515.8, True),
        EudlRow(24.0, 2606.6, True),
        EudlRow(25.0, 2698.5, True),
        EudlRow(26.0, 2790.7, True),
        EudlRow(27.0, 2887.1, True),
        EudlRow(28.0, 2983.5, True),
        EudlRow(29.0, 3083.6, True),
        EudlRow(30.0, 3177.0, True),
    ),
    table_label="25t-2008 EUDL for shear",
)


class T25Loading2008(LoadingStandard):
    """25t Loading-2008 (BG, single track) — the POC loading standard."""

    name = "25t-2008"

    def eudl_bm_kn(self, loaded_length_m: float) -> float:
        return interpolate_eudl(
            EUDL_BM_TABLE,
            loaded_length_m,
            table_label="EUDL for bending moment",
            standard_name=self.name,
        )

    def eudl_shear_kn(self, loaded_length_m: float) -> float:
        return interpolate_eudl(
            EUDL_SHEAR_TABLE,
            loaded_length_m,
            table_label="EUDL for shear",
            standard_name=self.name,
        )

    def eudl_bm_table(self) -> tuple[EudlRow, ...]:
        return EUDL_BM_TABLE

    def eudl_shear_table(self) -> tuple[EudlRow, ...]:
        return EUDL_SHEAR_TABLE

    def cda(self, loaded_length_m: float, cushion_m: float = 0.0) -> float:
        """CDA per Cl. 2.4.1.1 with the fill/cushion reduction of CITATION_CDA_FILL applied."""
        if not loaded_length_m > 0:
            raise ValueError(
                f"loaded length must be positive for CDA, got {loaded_length_m!r} m"
            )
        if not cushion_m >= 0:
            raise ValueError(f"cushion depth cannot be negative, got {cushion_m!r} m")
        full_cda = min(
            CDA_BASE + CDA_NUMERATOR / (CDA_LENGTH_OFFSET_M + loaded_length_m), CDA_MAX
        )
        return full_cda * self.cushion_reduction_factor(cushion_m)

    def cushion_reduction_factor(self, cushion_m: float) -> float:
        """The bare fill-reduction multiplier of CITATION_CDA_FILL — exposed so a
        proof-checker can verify the encoded rule in isolation."""
        if not cushion_m >= 0:
            raise ValueError(f"cushion depth cannot be negative, got {cushion_m!r} m")
        if cushion_m < CDA_FILL_REDUCTION_FROM_M:
            return 1.0
        return max((CDA_FILL_NO_AUGMENT_M - cushion_m) / CDA_FILL_NO_AUGMENT_M, 0.0)

    @property
    def citation(self) -> str:
        return (
            f"{SOURCE_TABLE}; {SOURCE_PAGES}; {CITATION_CDA_FORMULA}; "
            f"{CITATION_CDA_FILL}; transcribed at {ACS_LEVEL}. "
            f"Source: {SOURCE_DOCUMENT}. {VERIFY_BANNER}."
        )

    @property
    def eudl_citation(self) -> str:
        return f"{SOURCE_TABLE}; {SOURCE_PAGES}; transcribed at {ACS_LEVEL}"

    @property
    def cda_citation(self) -> str:
        return f"{CITATION_CDA_FORMULA}; {CITATION_CDA_FILL}"

    @property
    def acs_level(self) -> str:
        return ACS_LEVEL

    @property
    def source_document(self) -> str:
        return SOURCE_DOCUMENT

    @property
    def source_pages(self) -> str:
        return SOURCE_PAGES


T25_LOADING_2008 = register_loading_standard(T25Loading2008())
