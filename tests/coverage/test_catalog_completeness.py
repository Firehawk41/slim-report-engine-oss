"""Tier 1: catalog completeness. Checks the real analysis catalog
DIRECTLY -- not "has any real customer selected this yet" (that's Tier
2's job, tests/coverage/test_known_shapes_still_generate.py) but "does
every real catalog analysis even have a dispatch case at all." Catches
gaps that haven't been hit by any real customer's most-recent
submission yet, but exist in the catalog and could be selected any day
-- a form of coverage Tier 2's scan can't see, since it only samples
whatever customers have actually done recently.

Needs a live DB_URL -- skips gracefully when unreachable, same pattern
as the other tiers.
"""

from __future__ import annotations

import pytest

from slim_report_engine.reporting import chemical_water_report_builder

# Real catalog analyses confirmed to belong to a DIFFERENT dispatch path
# entirely (SX5's clsChemicalName-based routing, Wafer's element-count/
# reporting-units-based routing -- see submission_report_builder.py's
# module docstring) rather than chemical_water_report_builder's own
# elif chain, so their absence from _UNCONDITIONALLY_SUPPORTED is
# expected, not a gap. Add to this set only with a real, checked reason
# -- never just to silence a failure.
_HANDLED_BY_A_DIFFERENT_BUILDER: frozenset[str] = frozenset()

# Confirmed real (2026-09-28, this test's own first run) catalog
# analyses with NO dispatch case anywhere. Deliberately kept as an
# explicit, auditable "known gap" list rather than silently passing --
# each one is a REAL thing a customer could select today and get a
# "not yet supported" error for. Most match chemical_water_report_
# builder's own module docstring ("Organic-matrix / ICP-OES / microwave-
# digestion / 'with reported replicates' element-panel variants, GC-MS,
# Mixed Acid Assay, UV-Vis ... deliberately last priority"); a few are
# NEW findings this test surfaced that the docstring didn't mention --
# flagged to Jamie, not silently built:
#   - "Additional Element" (+ its ICP-OES/Microwave Digestion/Organic
#     Matrix variants): unclear whether this is a real selectable
#     analysis distinct from the existing additional_element_ids
#     mechanism (_resolve_additional_element_names), or a vestigial/
#     form-checkbox-only catalog row that's already implicitly handled
#     via that separate field -- needs a real example to tell apart,
#     not guessed here.
#   - "10 Elements (ICP-OES)"/"26 Elements (ICP-OES)": the ICP-OES
#     variant pattern extended to panel sizes the docstring's own list
#     didn't call out (it only mentioned generic "ICP-OES ... element-
#     panel variants" without enumerating which sizes).
#   - "Anions + MS Confirmation", "Anions + Organic Anions", "Anions +
#     Organic Anions + MS Confirmation": broader anion combos beyond the
#     4/5/7-specific "+ MS Confirmation" variants added 2026-09-28.
#     Bare "Organic Anions" is no longer deferred -- see
#     chemical_water_report_builder.py's own dispatch case (2026-09-28,
#     direct user instruction: GBP + Acetate/Formate); "Anions + Organic
#     Anions" (WITH the core inorganic anions merged in too, per the
#     catalog's own "organic and inorganic" description) is still
#     deferred, a distinct, not-yet-confirmed combination.
#   - "H2O2 Testing", "TIC": no existing section builder at all.
_DEFERRED_ANALYSES: frozenset[str] = frozenset(
    {
        "10 Elements (ICP-OES)", "26 Elements (ICP-OES)", "36 Elements (ICP-OES)",
        "36 Elements (Microwave Digestion)", "36 Elements (Organic Matrix)",
        "36 Elements (with reported replicates)",
        "Additional Element", "Additional Element (ICP-OES)",
        "Additional Element (Microwave Digestion)", "Additional Element (Organic Matrix)",
        "Anions + MS Confirmation", "Anions + Organic Anions", "Anions + Organic Anions + MS Confirmation",
        "GC-MS", "Mixed Acid Assay", "UV-Vis",
        "H2O2 Testing", "TIC",
    }
)


def test_every_catalog_analysis_has_a_dispatch_case():
    try:
        from slim_report_engine.cli import build_services
        services = build_services(None)
    except Exception as exc:
        pytest.skip(f"could not reach the real DB in this environment: {exc}")

    catalog_names = {a.name for a in services.analysis_svc.all_analyses()}
    supported = chemical_water_report_builder._UNCONDITIONALLY_SUPPORTED

    missing = catalog_names - supported - _HANDLED_BY_A_DIFFERENT_BUILDER - _DEFERRED_ANALYSES
    if missing:
        pytest.fail(
            f"{len(missing)} real catalog analysis name(s) have NO dispatch case anywhere, and "
            f"aren't in this test's own tracked _DEFERRED_ANALYSES/_HANDLED_BY_A_DIFFERENT_BUILDER "
            f"lists either -- a genuinely NEW, previously-unknown gap: {sorted(missing)}\n"
            f"Either add a real section-builder case for each, or -- if confirmed deliberately out "
            f"of scope for now -- add it to _DEFERRED_ANALYSES here with a comment saying why."
        )
