"""Database -> report check for specification limits, across EVERY linked
(customer, chemical, location) in the real database -- not just the few
customers the golden pairs cover.

For each one, builds the panel a report would print (in memory, no Excel)
through the same service lookups the real pipeline uses, and asserts every
limit in the database lands on its own element's row and no other row
prints one. Catches code-path bugs (wrong key or site, a symbol the panel
doesn't list so the limit silently never prints). It does NOT check that
the database values themselves are right -- only tests/golden can, against
real legacy reports.

Skips when the real database isn't reachable.
"""

from __future__ import annotations

import warnings
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from infrastructure.database import make_engine

from slim_report_engine.reporting import chemical_water_report_builder as generic
from slim_report_engine.reporting import sx5_non_routine_report_builder as sx5
from slim_report_engine.reporting.presets import analyte_presets, ion_presets
from slim_report_engine.reporting.section_builders import (
    analyte_list_section_builder,
    silicon_section_builder,
    titrations_section_builder,
)
from slim_report_engine.reporting.submission_report_builder import SX5_CUSTOMER_NAME, _sx5_spec_data

# Limits on file that no generic report prints, listed so the test stays
# exact; the stale-entry check below forces removing any that start
# printing. (customer name, chemical name, symbol)
KNOWN_UNPRINTED_GENERIC: frozenset[tuple[str, str, str]] = frozenset()


@pytest.fixture(scope="module")
def services():
    try:
        from slim_report_engine.cli import build_services

        return build_services(None)
    except Exception as exc:  # pragma: no cover -- environment-dependent
        pytest.skip(f"could not reach the real DB in this environment: {exc}")


def _groups(services, where: str) -> list[tuple[int, int, str]]:
    with make_engine(None).connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(text(
                "SELECT DISTINCT customer_id, chemical_id, location FROM specifications "
                "WHERE kind = 'specification' AND customer_id IS NOT NULL AND chemical_id IS NOT NULL AND " + where
            ))
        ]


def _printed_limits(sections) -> dict[str, list[float]]:
    printed: dict[str, list[float]] = {}
    for section in sections:
        for row in section.rows:
            limit, symbol = row.get_value(1), row.get_value(3)
            if isinstance(limit, (int, float)) and not isinstance(limit, bool) and isinstance(symbol, str):
                printed.setdefault(symbol, []).append(float(limit))
    return printed


def _compare(label: str, expected: dict[str, float], printed: dict[str, list[float]]) -> list[str]:
    problems = []
    for symbol in sorted(set(expected) | set(printed)):
        want = expected.get(symbol)
        got = printed.get(symbol, [])
        if want is None:
            problems.append(f"{label}: {symbol} prints {got} but has no limit on file")
        elif got != [float(want)]:
            problems.append(f"{label}: {symbol} on file {want}, printed {got or 'nothing'}")
    return problems


def _generic_probe_sections(services):
    """One of every panel a generic report can carry a limit on: the
    largest metals panel, both silicon rows, the full anion and cation
    lists, and the Assay section."""
    return [
        analyte_list_section_builder.build_metals_panel(
            "67 Elements", analyte_presets.trace_elements_67(), "67 Tr.Elts", services.element_svc
        ),
        silicon_section_builder.build_silicon("Silicon", True, True),
        generic._ion_panel("Anions", "Anion", ion_presets.anions_master(), None),
        generic._ion_panel("Cations", "Cation", ion_presets.cations_master(), None),
        titrations_section_builder.build_assay("Assay"),
    ]


def test_every_generic_limit_prints_where_its_analyte_appears(services):
    """Runs the real apply_limits over one of every panel, for both limit
    kinds (specification and warning limit), and checks each row carrying
    a limit: it must be the limit on file, of that kind, for the analyte
    in that row's column 2 or 3 (case-insensitive, as the legacy macro);
    and every limit on file must land on at least one row."""
    problems, unprinted = [], set()
    with make_engine(None).connect() as conn:
        groups = conn.execute(text(
            "SELECT DISTINCT customer_id, chemical_id FROM specifications WHERE customer_id IS NOT NULL "
            "AND chemical_id IS NOT NULL AND location = '' AND kind IN ('specification', 'warning_limit')"
        )).fetchall()
    for customer_id, chemical_id in groups:
        limits_by_kind = {
            "specification": services.specification_svc.get_specs(customer_id, chemical_id),
            "warning_limit": services.specification_svc.get_warning_limits(customer_id, chemical_id),
        }
        customer = services.customer_svc.load_customer(customer_id)
        chemical = services.chemical_svc.load_chemical(chemical_id)
        cust_name = customer.name if customer else str(customer_id)
        chem_name = chemical.name if chemical else str(chemical_id)
        sections = _generic_probe_sections(services)
        generic.apply_limits(sections, limits_by_kind)

        landed: set[tuple[str, str]] = set()
        for section in sections:
            for row in section.rows:
                keys = [row.get_value(c).upper() for c in (2, 3) if isinstance(row.get_value(c), str)]
                for kind, value in row.limits.items():
                    by_key = {k.upper(): (k, float(v)) for k, v in limits_by_kind[kind].items()}
                    matched = [by_key[k] for k in keys if k in by_key]
                    if not matched:
                        problems.append(f"{cust_name} / {chem_name}: row {keys} has {kind} {value} with none on file")
                    elif float(value) != matched[-1][1]:
                        problems.append(f"{cust_name} / {chem_name}: {kind} {matched[-1][0]} on file "
                                        f"{matched[-1][1]}, row has {value}")
                    else:
                        landed.add((kind, matched[-1][0]))
        unprinted.update(
            (cust_name, chem_name, f"{kind}:{k}" if kind != "specification" else k)
            for kind, limits in limits_by_kind.items() for k in limits if (kind, k) not in landed
        )

    new_unprinted = sorted(unprinted - KNOWN_UNPRINTED_GENERIC)
    stale = sorted(KNOWN_UNPRINTED_GENERIC - unprinted)
    problems += [f"limit on file that no report prints: {u}" for u in new_unprinted]
    problems += [f"KNOWN_UNPRINTED_GENERIC entry now prints or is gone, remove it: {s}" for s in stale]
    assert not problems, "\n".join(problems)


def test_every_sx5_limit_prints_on_its_row(services):
    customer = next((c for c in services.customer_svc.all_customers() if c.name == SX5_CUSTOMER_NAME), None)
    if customer is None:
        pytest.skip("no SX5 customer in this database (e.g. the public fork's demo data)")
    problems, checked = [], 0
    for customer_id, chemical_id, location in _groups(services, "location <> ''"):
        chemical = services.chemical_svc.load_chemical(chemical_id)
        name = chemical.name if chemical else str(chemical_id)
        if not sx5.is_supported_chemical(name):
            continue  # a SX5 chemical with no non-routine sheet (e.g. Acetone) -- never printed by this path
        canonical = sx5._canonicalize_chemical_name(name)
        if sx5._get_category(canonical) == "Element" and canonical not in sx5._ELEMENT_CHEMICALS_BY_LOCATION[location]:
            continue  # this site's template has no sheet for it (North SurfClean)
        data = _sx5_spec_data(customer, SimpleNamespace(chemical_id=chemical_id), location, services.specification_svc)
        # Request anions so a composite sheet prints its anion limits too.
        result = sx5.build_non_routine_report(
            name, location, date(2026, 1, 1), "S-1", services.element_svc,
            frozenset({"4 Anions"}), spec_data=data,
        )
        problems += _compare(f"{location} / {name}", data.specs, _printed_limits(result.sections))
        checked += 1
    assert checked, "no SX5 sheets were checked -- is the SX5 data linked (location column)?"
    assert not problems, "\n".join(problems)


def test_report_unlinked_spec_rows(services):
    """Not a failure: lists spec rows that no report can use because their
    customer or chemical never matched the catalog, so they're visible."""
    with make_engine(None).connect() as conn:
        rows = conn.execute(text(
            "SELECT customer_name_raw FROM specifications WHERE customer_id IS NULL OR chemical_id IS NULL"
        )).scalars().all()
    if rows:
        names = ", ".join(sorted(set(rows)))
        warnings.warn(f"{len(rows)} spec rows are unlinked and never used by any report; customers: {names}")
