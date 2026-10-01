"""Unit coverage for cli.py's technician-facing error message wrappers --
pure construction logic, no DB or real workbook needed. Added 2026-09-29
(failure-path audit): confirms the blank-vs-unresolved wording split for
customer/chemical, and the reason-aware wording for a report folder
that's mapped but currently unreachable (vs. never mapped at all).
"""

from slim_report_engine.cli import (
    UnresolvedChemicalReportError,
    UnresolvedCustomerReportError,
    UnresolvedReportFolderReportError,
)


def test_blank_customer_gets_a_blank_specific_message():
    e = UnresolvedCustomerReportError("", "", "")
    assert "No customer information was entered" in str(e)
    assert "Unresolved customer" not in str(e)


def test_whitespace_only_customer_name_counts_as_blank():
    e = UnresolvedCustomerReportError("   ", "123 Main St", "")
    assert "No customer information was entered" in str(e)


def test_real_unresolved_customer_keeps_the_original_wording():
    e = UnresolvedCustomerReportError("Totally Unknown Customer", "1 St", "Springfield, IL")
    assert "Unresolved customer: 'Totally Unknown Customer'" in str(e)
    assert "needs to be added to the database" in str(e)


def test_blank_chemical_gets_a_blank_specific_message():
    e = UnresolvedChemicalReportError("")
    assert "No chemical matrix was entered" in str(e)
    assert "Unresolved chemical" not in str(e)


def test_whitespace_only_chemical_counts_as_blank():
    e = UnresolvedChemicalReportError("   ")
    assert "No chemical matrix was entered" in str(e)


def test_real_unresolved_chemical_keeps_the_original_wording():
    e = UnresolvedChemicalReportError("Totally Unknown Acid")
    assert "Unresolved chemical: 'Totally Unknown Acid'" in str(e)
    assert "needs to be added to the database" in str(e)


def test_report_folder_error_default_wording_when_never_mapped():
    e = UnresolvedReportFolderReportError(1, "Customer 130")
    assert "needs to be set before a report can be saved" in str(e)


def test_report_folder_error_reason_wording_when_mapped_but_unreachable():
    e = UnresolvedReportFolderReportError(
        1, "Customer 130", reason="the mapped folder (\\\\share\\Acme) could not be reached -- offline."
    )
    assert "Could not use the report folder mapped for customer" in str(e)
    assert "could not be reached -- offline." in str(e)
    assert "needs to be set before a report can be saved" not in str(e)
