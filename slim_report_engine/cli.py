"""Entry point: reads a filled-in Testing Request workbook, builds report
content for every sample, writes the output workbook.

Two callers:
  - run(), called directly by the Slim-LIMS API server -- the real
    production path. The technician's Excel button (vba/
    modReportEngineHook.bas) POSTs to that server over HTTP; the server
    calls run() and maps its exceptions to HTTP responses (a
    ReportEngineError subclass -> 422 with the message shown to the
    technician; anything else -> 500). See README.md's "Invocation from
    VBA" section.
  - main(), this module's command line -- for development, tests, and
    one-off manual runs. Reports via exit code plus a message on
    stdout/stderr. --result-file additionally writes "<code>\\n<message>"
    to a file; it was built for a hidden-window exe launch that was never
    deployed, and is kept only because it's harmless and tested.

EXIT CODES (main() only):
  0  success -- output workbook written, its path is the message
  1  a recognized, actionable error (unresolved customer/chemical,
     unsupported analysis/SX5 chemical, empty submission, bad input
     file) -- the message is meant to be shown to the technician
     directly, e.g. via MsgBox
  2  an unexpected error (a real bug, not a data problem) -- the
     message is a full traceback, not meant for a technician to
     action
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback
import zipfile
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from infrastructure.database import make_engine, make_session
from infrastructure.network_paths import resolve_mapped_drive
from slim_domain.domain.analysis.analysis_service import AnalysisService
from slim_domain.domain.chemical.chemical_service import ChemicalService
from slim_domain.domain.customer.customer_service import CustomerService
from slim_domain.domain.element.element_service import ElementService
from slim_domain.domain.report_folder.report_folder_service import (
    ReportFolderService,
    UnresolvedReportFolderError,
)
from slim_domain.domain.report_log.report_log_service import ReportGenerationLogService
from slim_domain.domain.specification.specification_service import SpecificationService
from slim_domain.domain.tr.tr_form_input_resolver import (
    TRFormInputResolver,
    UnresolvedChemicalError,
    UnresolvedCustomerError,
)
from slim_domain.domain.tr.tr_submission_service import TRSubmissionService

from slim_report_engine.lab_identity import LAB_HEADER_LINES
from slim_report_engine.report_filename import report_filename
from slim_report_engine.reporting import report_writer
from slim_report_engine.reporting.submission_report_builder import (
    SX5_CUSTOMER_NAME,
    build_submission_sheets,
    sx5_location_from_filename,
)


logger = logging.getLogger(__name__)

# For the ISO 17025 traceability ask: every run() invocation logs this
# alongside the customer/filename/output, so a given historical report's
# log line can be tied back to a known, described version (see
# CHANGELOG.md). Read once at import time, not per-call. Falls back to
# "unknown" rather than raising -- a dev checkout that skipped `pip
# install -e .` shouldn't crash report generation over a log field.
#
# Both packages, not just this one: a bug can live in either
# slim-report-engine's own code or in slim-domain (the shared
# customer/chemical/report-folder layer it depends on) -- logging only
# one of the two versions would leave half the stack untraceable.
try:
    _VERSION = _pkg_version("slim-report-engine")
except PackageNotFoundError:
    _VERSION = "unknown"
try:
    _DOMAIN_VERSION = _pkg_version("slim-domain")
except PackageNotFoundError:
    _DOMAIN_VERSION = "unknown"


def _set_info(info: dict | None, **kwargs) -> None:
    """Populate run()'s optional `info` out-param in place, a no-op when
    it's None (the default, every existing caller) -- see run()'s own
    docstring for what gets set and why."""
    if info is not None:
        info.update(kwargs)


class ReportEngineError(Exception):
    """A recognized, actionable failure. Message is safe to show a technician directly."""


class UnresolvedCustomerReportError(ReportEngineError):
    """A customer/address combination on the form has no match in the database.

    Carries the raw form fields (not just a message) so a caller like the
    API server can offer real resolution -- e.g. a page to map this form
    text to an existing customer, or add a new one -- instead of just
    showing an error and stopping."""

    def __init__(self, form_customer: str, form_address: str, form_address2: str) -> None:
        self.form_customer = form_customer
        self.form_address = form_address
        self.form_address2 = form_address2
        if not form_customer.strip():
            # Confirmed real gap (2026-09-29 failure-path audit): a truly
            # blank customer field routed through the same "Unresolved
            # customer: '' / ... -- this needs to be added to the
            # database" wording as a real, typo'd/unmapped name -- which
            # reads as "add a blank customer to the database," not "you
            # left this blank." Distinguished here since it's the one
            # place with both the raw form value and the final technician-
            # facing message.
            super().__init__(
                "No customer information was entered on this Testing Request -- fill in the "
                "customer section before generating a report."
            )
        else:
            super().__init__(
                f"Unresolved customer: {form_customer!r} / {form_address!r} / {form_address2!r} "
                "-- this needs to be added to the database before a report can be generated for it."
            )


class ReportAlreadyExistsError(ReportEngineError):
    """The auto-computed destination (see run()'s output_path is None path)
    already has a file at it. Only raised for that auto-computed path --
    never for an explicit --output/output_path, which is the CLI/test
    entry point and has always allowed overwriting on purpose (e.g. Sam
    the report writer regenerating during development).

    Refusing outright, rather than picking a "-2" suffix or similar, is
    deliberate: the old manual workflow's Save-As dialog made a
    technician confirm an overwrite by hand every time; the new
    auto-save flow has no such prompt, so the closest equivalent is to
    stop and say so rather than silently guess what the technician
    wanted. A real collision means either the same Testing Request is
    being reprocessed (the existing file may already have a
    technician's hand-entered results on it) or two different
    submissions happened to compute the same destination name -- both
    need a person to look, not an automatic pick."""

    def __init__(self, existing_path: Path) -> None:
        self.existing_path = existing_path
        super().__init__(
            f"A report already exists at {existing_path} -- refusing to overwrite it "
            "automatically, since it may already have results entered on it. If this report "
            "needs to be regenerated from scratch, move or rename the existing file first."
        )


class UnresolvedChemicalReportError(ReportEngineError):
    """A chemical name on the form has no match in the database. See
    UnresolvedCustomerReportError -- same idea, for chemicals."""

    def __init__(self, form_name: str) -> None:
        self.form_name = form_name
        if not form_name.strip():
            # See the matching guard in UnresolvedCustomerReportError --
            # same fix, same reasoning. Confirmed real gap: this is the
            # exact scenario Jamie originally flagged from the legacy VBA
            # macro (a Testing Request with no chemical matrix entered
            # produces no output and no notice) -- the Python pipeline
            # already fails loudly for it (never silent), but the message
            # used to read "Unresolved chemical: '' -- this needs to be
            # added to the database," which is nonsensical for a cell the
            # customer just left empty.
            super().__init__(
                "No chemical matrix was entered on this Testing Request row -- add one before "
                "generating a report."
            )
            return
        super().__init__(
            f"Unresolved chemical: {form_name!r} -- this needs to be added to the database "
            "before a report can be generated for it."
        )


class UnresolvedReportFolderReportError(ReportEngineError):
    """The resolved customer has no known (or no longer real) Reports
    destination folder. See UnresolvedCustomerReportError -- same idea,
    for the save-location mapping instead of customer identity. Only
    raised when run() is asked to pick its own output_path (see run()'s
    docstring); an explicit output_path always bypasses this."""

    def __init__(self, customer_id: int, customer_name: str, location: str = "", reason: str = "") -> None:
        self.customer_id = customer_id
        self.customer_name = customer_name
        self.location = location
        self.reason = reason
        where = f" ({location})" if location else ""
        if reason:
            # Confirmed real gap (2026-09-29 failure-path audit): a
            # currently-unreachable mapped folder (network share offline)
            # previously raised a raw, unwrapped OSError from inside
            # ReportFolderService.resolve_folder()'s is_dir() check --
            # never reaching this class at all, so it always got the
            # generic "needs to be set" wording below, which is actively
            # wrong for a mapping that already exists but is temporarily
            # unreachable. See ReportFolderService.resolve_folder()'s own
            # docstring update for where `reason` comes from.
            super().__init__(
                f"Could not use the report folder mapped for customer {customer_name!r}{where} "
                f"({customer_id}) -- {reason}"
            )
            return
        super().__init__(
            f"No usable report folder mapped for customer {customer_name!r}{where} ({customer_id}) "
            "-- this needs to be set before a report can be saved for it."
        )


@dataclass
class ReportEngineServices:
    """The 7 read-mostly, cache-backed services -- expensive to build (each
    one loads its whole table from Postgres into memory, confirmed via
    timing to be ~0.34s combined), cheap to reuse. Safe to share across
    many run() calls: each service's cache is a plain in-memory dict built
    once at construction, never touched again by a read (see e.g.
    ChemicalService/ChemicalCache).

    Reads never need a live session/engine after construction -- but
    WRITES (a new customer/chemical, a form-text mapping, a folder
    resolution) do, and confirmed real (2026-09-24, a live stress test
    against the deployed Slim-LIMS service): sharing the one `session`
    passed in below across concurrent write requests crashed with
    sqlalchemy.exc.InvalidRequestError('Session is already flushing') --
    FastAPI runs sync routes like /generate-report and /resolve/* on a
    real threadpool, so concurrent access to that one shared Session was
    always possible, not hypothetical. Each write-capable service below
    also takes `engine=engine` so its repository can open a short-lived
    session per write instead (see CustomerRepository._write_session's
    docstring for the mechanism) -- reads are unaffected, this only
    changes how writes get their session."""

    chemical_svc: ChemicalService
    analysis_svc: AnalysisService
    element_svc: ElementService
    customer_svc: CustomerService
    specification_svc: SpecificationService
    report_folder_svc: ReportFolderService
    report_log_svc: ReportGenerationLogService


def build_services(db_url: str | None = None) -> ReportEngineServices:
    """Build a fresh ReportEngineServices bundle -- this is the ~0.34s-per-call
    cost a persistent server should pay ONCE (at startup, and again only via
    an explicit refresh), not on every request. The CLI still calls this
    fresh every run(), which is correct for a one-shot-per-report process."""
    engine = make_engine(db_url)
    session = make_session(engine)
    # REPORT_FOLDER_TEST_ROOT (.env, unset by default -- real production
    # behavior): when set, confines every report-folder mapping under that
    # directory and auto-creates it on demand, so the whole resolution +
    # save + swap flow can be exercised for real (by Jamie or Quality)
    # with zero possibility of a write landing in a real customer's real
    # S:\Reports folder. See ReportFolderService.set_folder().
    #
    # resolve_mapped_drive(): both roots below can be (and in practice,
    # test_root routinely now is, per Quality's Macro Validation folder)
    # a drive-letter path on the shared network drive -- a Windows
    # Service doesn't see that mapping regardless of which account runs
    # it, the same way S:\Testing_Requests never worked on the input
    # side until this same translation was applied there. See
    # network_paths.py's docstring.
    test_root = resolve_mapped_drive(os.environ["REPORT_FOLDER_TEST_ROOT"]) if os.environ.get("REPORT_FOLDER_TEST_ROOT") else None
    # REPORT_FOLDER_ROOT (.env, defaults to the real Reports share):
    # confirmed real gap (direct user question) -- without this,
    # /resolve/folder (reachable via a one-time token, NOT the API key)
    # could set a customer's report destination to ANY existing absolute
    # directory the server can see, not just somewhere under the real
    # Reports tree. Ignored when test_root is set (test mode takes
    # precedence -- see ReportFolderService.set_folder()).
    production_root = resolve_mapped_drive(os.environ.get("REPORT_FOLDER_ROOT") or r"S:\Reports")
    services = ReportEngineServices(
        chemical_svc=ChemicalService(session, engine=engine),
        analysis_svc=AnalysisService(session, engine=engine),
        element_svc=ElementService(session),
        customer_svc=CustomerService(session, engine=engine),
        specification_svc=SpecificationService(session),
        report_folder_svc=ReportFolderService(
            session, test_root=test_root, production_root=production_root, engine=engine
        ),
        report_log_svc=ReportGenerationLogService(session, engine=engine),
    )
    # Each service's constructor just did a one-time read to build its cache
    # (see ReportEngineServices' docstring -- nothing downstream needs a
    # live session after this point), but nothing ever ended that read's
    # transaction. Confirmed real via a live Postgres session sitting
    # "idle in transaction" for ~16 hours in production, from exactly this
    # startup read -- harmless until it blocks something that needs a real
    # lock (it blocked a schema migration), but bad Postgres hygiene
    # either way (holds locks indefinitely, works against autovacuum) for
    # a long-lived server that can go long stretches without a write.
    # Committing here (nothing to roll back -- these were all reads) closes
    # it out; every write path already commits itself afterward, so this
    # is the only gap.
    session.commit()
    return services


def run(
    input_path: Path,
    output_path: Path | None = None,
    db_url: str | None = None,
    *,
    services: ReportEngineServices | None = None,
    info: dict | None = None,
) -> Path:
    """When output_path is given explicitly (the CLI's only path, and
    every existing test), it's used as-is -- unchanged behavior, no folder
    resolution involved. When it's None (the API server's path, once a
    customer's Reports folder can be looked up), run() picks its own
    destination: the customer's mapped report folder (see
    ReportFolderService) plus a filename computed by report_filename()
    from the input's own filename -- raising UnresolvedReportFolderReportError
    if that customer has no known (or no longer real) folder mapping yet.

    info: optional, additive (2026-09-29, direct user request for a richer
    VBA-side log without changing run()'s return type -- "the big gates
    the code successfully clears"). When given, populated in place with
    customer_name/request_type/sample_count/parse_seconds (once parsing
    succeeds), sheet_count/build_seconds (once sections are built),
    write_seconds (once the workbook is written+saved), and
    engine_version/domain_version (always, from the top). Every existing
    caller passes nothing here and is completely unaffected -- default
    None means "don't bother," checked once per field via _set_info."""
    # Phase timing -- added to find out WHERE time actually goes before
    # optimizing anything, rather than guessing. Logged via the standard
    # `logging` module (INFO level) so both the CLI (a fresh process per
    # report, where this mostly doesn't matter) and the server (a
    # long-lived process handling many requests, where it does) can
    # observe it without changing this function's return type/contract.
    #
    # `services`: when None (the CLI's only path -- unchanged
    # behavior), builds a fresh ReportEngineServices exactly as before.
    # When given (the API server's path, once it caches services at
    # startup), skips rebuilding the caches entirely.
    t0 = time.perf_counter()
    logger.info("run(): processing %s (slim-report-engine v%s)", input_path.name, _VERSION)
    _set_info(info, engine_version=_VERSION, domain_version=_DOMAIN_VERSION)

    if services is None:
        services = build_services(db_url)
        t1 = time.perf_counter()
        logger.info("run(): service/cache construction took %.3fs", t1 - t0)
    else:
        t1 = time.perf_counter()
        logger.info("run(): reused pre-built service caches (%.3fs)", t1 - t0)

    chemical_svc = services.chemical_svc
    analysis_svc = services.analysis_svc
    element_svc = services.element_svc
    customer_svc = services.customer_svc
    specification_svc = services.specification_svc
    resolver = TRFormInputResolver(customer_svc, chemical_svc)
    submission_svc = TRSubmissionService(chemical_svc, analysis_svc, element_svc, resolver)

    # Load the workbook ONCE, writable, and parse directly from this same
    # worksheet -- reused later for writing the output too. Measured: an
    # openpyxl read-only load (what TRSubmissionService.build_from_file
    # uses internally) parses in ~0.02s, but this parser's row-by-row
    # `ws.cell(row, col)` access pattern then takes ~250ms against a
    # read-only sheet (read-only mode is optimized for sequential
    # iteration, not repeated random access) versus ~0.3ms against a
    # writable one -- a ~600x difference for the parse step alone, and it
    # also avoids a second full file load later. TRSubmissionService still
    # offers build_from_file() as a convenience for other callers; this is
    # the one hot path worth bypassing it for.
    try:
        wb = openpyxl.load_workbook(input_path)
    except PermissionError as e:
        # Confirmed real gap (2026-09-29 failure-path audit): this call
        # was completely unwrapped -- a file still open (and thus locked)
        # in Excel on the technician's own machine, the single most
        # plausible real-world trigger, fell all the way through to
        # main()'s generic `except Exception` and showed a raw Python
        # traceback instead of a message a technician could act on.
        raise ReportEngineError(
            f"could not open {input_path.name} -- it looks like the file is open in Excel (or "
            "another program) on this computer. Close it and try again."
        ) from e
    except (zipfile.BadZipFile, InvalidFileException) as e:
        # Same audit finding, same unwrapped call -- a corrupted download,
        # a password-protected workbook (openpyxl has no decryption
        # support at all), or a file that just isn't really an .xlsx
        # (wrong extension, HTML/CSV saved with an .xlsx name) all reach
        # here rather than a ValueError, so this needs its own explicit
        # catch, separate from the ValueError-based ones further down.
        raise ReportEngineError(
            f"could not open {input_path.name} -- it doesn't look like a valid, readable .xlsx "
            "workbook (it may be corrupted, password-protected, or a different file type). "
            "Check the file and try again."
        ) from e
    form_ws = _find_form_sheet(wb)
    if form_ws is None:
        raise ReportEngineError(f"No Testing Request Form sheet found in {input_path.name}")
    download_date = datetime.fromtimestamp(input_path.stat().st_mtime)

    try:
        submission = submission_svc.build_from_worksheet(
            form_ws, download_date=download_date, filename=input_path.name
        )
    except UnresolvedCustomerError as e:
        raise UnresolvedCustomerReportError(e.name, e.address, e.address2) from e
    except UnresolvedChemicalError as e:
        raise UnresolvedChemicalReportError(e.form_name) from e
    except ValueError as e:
        # Confirmed real (an offline scan across every customer's most
        # recent submission): every ValueError reaching here so far has
        # been a required current-template field that's missing or
        # unrecognized (blank "date received", blank/unrecognized
        # "processing time") on an OLD, pre-current-template form --
        # current policy is to assume every incoming submission uses the
        # current template and not attempt to support older ones, but
        # flag them clearly rather than a bare "could not read" message
        # that doesn't explain why.
        raise ReportEngineError(
            f"could not read {input_path.name}: {e} -- this looks like a legacy/older Testing "
            "Request form (a required field on the current template is missing or unrecognized). "
            "Legacy forms aren't currently supported by this pipeline."
        ) from e

    t2 = time.perf_counter()
    logger.info("run(): parsing input workbook took %.3fs", t2 - t1)
    _set_info(
        info,
        request_type=submission.request_type.name,
        sample_count=len(submission.samples),
        parse_seconds=round(t2 - t1, 3),
    )

    customer = customer_svc.load_customer(submission.customer_id)
    if customer is None:
        raise ReportEngineError(
            f"customer_id {submission.customer_id} was resolved during parsing but no longer loads "
            "-- this indicates a real bug, not a data problem."
        )
    _set_info(info, customer_name=customer.name)

    if output_path is None:
        # SX5 is a single customer record (shared for invoicing) whose real
        # reports split across two real folders depending on the TR
        # filename -- see sx5_location_from_filename's own docstring for
        # why this can't come from the customer record. Mirrors the exact
        # same computation build_submission_sheets does for report content.
        location = ""
        if customer.name == SX5_CUSTOMER_NAME:
            try:
                location = sx5_location_from_filename(input_path.name)
            except ValueError as e:
                raise ReportEngineError(str(e)) from e

        report_folder_svc = services.report_folder_svc
        try:
            folder = report_folder_svc.resolve_folder(customer.id, customer.name, location=location)
        except UnresolvedReportFolderError as e:
            raise UnresolvedReportFolderReportError(
                e.customer_id, e.customer_name, e.location, reason=e.reason
            ) from e
        output_path = folder / report_filename(input_path.name)
        if output_path.exists():
            raise ReportAlreadyExistsError(output_path)
    assert output_path is not None

    try:
        sheets = build_submission_sheets(
            submission, customer, chemical_svc, analysis_svc, element_svc, specification_svc
        )
    except ValueError as e:
        raise ReportEngineError(str(e)) from e

    if not sheets:
        raise ReportEngineError(f"no samples found in {input_path.name} -- nothing to write.")

    t3 = time.perf_counter()
    logger.info("run(): building report sections took %.3fs", t3 - t2)
    _set_info(info, sheet_count=len(sheets), build_seconds=round(t3 - t2, 3))

    # Confirmed real (every completed report checked): the filled-in
    # Testing Request form itself is appended as the LAST tab of the
    # output workbook. Building on the SAME workbook object already
    # loaded above (rather than a fresh one) keeps that sheet's real
    # formatting, formulas, and dropdowns exactly as submitted -- no
    # manual cell-by-cell copy needed, which openpyxl has no built-in
    # support for across two separate workbook objects anyway, and no
    # second file load.
    for sheet in sheets:
        ws = wb.create_sheet(sheet.name)
        report_writer.apply_zoom(ws, sheet.zoom)
        report_writer.apply_column_widths(ws, sheet.column_widths, sheet.limit_columns)
        report_writer.write_sections(ws, list(sheet.sections), start_row=1, limit_columns=sheet.limit_columns)
        report_writer.apply_header_footer(
            ws,
            center_header=sheet.header_title,
            customer_name=customer.name,
            customer_address_line1=customer.street_address,
            customer_address_line2=customer.city,
            lab_header_lines=LAB_HEADER_LINES,
        )
        for cell_address, value in sheet.extra_cell_stamps:
            report_writer.apply_plain_cell_stamp(ws, cell_address, value)
        if sheet.title_cell_stamp is not None:
            report_writer.apply_title_cell(ws, *sheet.title_cell_stamp)
        if sheet.processing_time_stamp is not None:
            # Moves right with the content when a sheet has extra limit
            # columns (legacy Customer 168: "D1" becomes "E1").
            address, *rest = sheet.processing_time_stamp
            report_writer.apply_processing_time_stamp(
                ws, report_writer.shift_cell_address(address, sheet.limit_columns), *rest
            )

    wb.move_sheet(form_ws.title, offset=len(wb.sheetnames))

    # Confirmed real gap (2026-09-29, direct user report -- opened the
    # output and saw both the first report tab AND the original form tab
    # highlighted as "selected"): every newly created sheet defaults to
    # sheet_view.tabSelected = None (falsy), but form_ws keeps whatever
    # tabSelected state it already had in the technician's own template
    # (confirmed real: the current Chemical intake template's one sheet
    # has tabSelected=True). wb.active only tracks which sheet is the
    # ACTIVE one -- it does NOT clear tabSelected on any other sheet --
    # so once form_ws moves to the end it sits there still marked
    # "selected" alongside the new active sheet, and Excel renders both
    # as a confusing multi-sheet selection (echoed on every save/reopen,
    # confirmed via a real round-trip) instead of just the one that
    # should be. Explicitly set exactly one sheet (the first report
    # sheet) as both tabSelected and active, and clear tabSelected
    # everywhere else -- including form_ws itself, wherever it landed.
    first_report_ws = wb[sheets[0].name]
    for ws in wb.worksheets:
        ws.sheet_view.tabSelected = ws is first_report_ws
    wb.active = first_report_ws

    t3c = time.perf_counter()
    logger.info("run(): per-sheet writing loop took %.3fs", t3c - t3)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # Confirmed real gap (2026-09-29 failure-path audit): unwrapped --
        # an offline/unreachable Reports network share (or a genuine
        # permissions problem) raised a raw OSError here, falling through
        # to main()'s generic `except Exception` and showing a traceback
        # instead of a message a technician could act on.
        raise ReportEngineError(
            f"could not create the output folder {output_path.parent} -- the network drive may "
            "be offline or unreachable, or there's a permissions problem. Check the connection "
            "and try again."
        ) from e

    try:
        wb.save(output_path)
    except PermissionError as e:
        # Same audit finding as the mkdir guard above -- the most likely
        # real trigger here is the destination report already open in
        # Excel (e.g. a re-run while someone's reviewing the prior save).
        raise ReportEngineError(
            f"could not save the report to {output_path} -- it may already be open in Excel (or "
            "another program). Close it and try again."
        ) from e
    except OSError as e:
        raise ReportEngineError(
            f"could not save the report to {output_path} -- the destination drive may be "
            "offline, unreachable, or full. Check it and try again."
        ) from e
    logger.info("run(): wb.save() took %.3fs", time.perf_counter() - t3c)

    # Traceability log (2026-09-25, direct user request): who/what/when a
    # report was generated -- see ReportGenerationLogService's docstring
    # for what this can and can't tell you (it's create-only; a report
    # being deleted afterward, on the file share, produces no event here).
    # Best-effort: a log write failure shouldn't turn an otherwise-
    # successful report generation into a hard failure -- the real
    # deliverable (the report file) already exists on disk at this point.
    try:
        services.report_log_svc.record_generation(
            input_path=str(input_path),
            output_path=str(output_path),
            customer_name=customer.name,
            request_type=submission.request_type.name,
            technician_initials=submission.technician_initials,
        )
    except Exception:
        logger.warning("run(): failed to write report-generation log entry", exc_info=True)

    t4 = time.perf_counter()
    logger.info("run(): writing output workbook took %.3fs", t4 - t3)
    _set_info(info, write_seconds=round(t4 - t3, 3))
    logger.info("run(): TOTAL %.3fs", t4 - t0)
    logger.info(
        "run(): SUCCESS customer=%r input=%s output=%s (slim-report-engine v%s, slim-domain v%s)",
        customer.name, input_path.name, output_path, _VERSION, _DOMAIN_VERSION,
    )

    return output_path


def _find_form_sheet(wb: openpyxl.Workbook):
    """Same detection rule as slim-domain's TRSubmissionService.build_from_file
    (the first sheet whose D3 cell contains "Testing Request Form") --
    reimplemented here rather than imported since that one is a private
    module-level helper, not part of TRSubmissionService's public API."""
    for ws in wb.worksheets:
        if "Testing Request Form" in str(ws["D3"].value or ""):
            return ws
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a blank lab report workbook from a Testing Request workbook."
    )
    parser.add_argument("input", type=Path, help="path to the filled-in Testing Request .xlsx")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="output .xlsx path (default: <input>_report.xlsx, next to the input file)",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="DB_URL override (default: .env's DB_URL, or sqlite:///report_engine.db)",
    )
    parser.add_argument(
        "--result-file", type=Path, default=None,
        help="also write '<exit code>\\n<message>' to this file, for scripted callers "
             "that can't read stdout/stderr",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        return _finish(1, f"input file not found: {args.input}", args.result_file)

    output_path = args.output or args.input.with_name(args.input.stem + "_report.xlsx")

    try:
        result_path = run(args.input, output_path, args.db)
    except ReportEngineError as e:
        return _finish(1, str(e), args.result_file)
    except Exception:
        return _finish(2, traceback.format_exc(), args.result_file)

    return _finish(0, str(result_path), args.result_file)


def _finish(code: int, message: str, result_file: Path | None) -> int:
    """Reports (code, message) on stdout/stderr (guarded: a --windowed-style
    frozen build with no console attached has sys.stdout/sys.stderr as None,
    though the real deployed build keeps a console -- just a hidden one) and,
    if given, writes it to result_file for the hidden-launch VBA hook to read.
    Written via a same-directory temp file + os.replace (atomic on Windows)
    so a concurrent reader never observes a partially-written file.
    """
    stream = sys.stdout if code == 0 else sys.stderr
    if stream is not None:
        print(message, file=stream)
    if result_file is not None:
        tmp = result_file.with_name(result_file.name + ".tmp")
        tmp.write_text(f"{code}\n{message}", encoding="utf-8")
        tmp.replace(result_file)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
