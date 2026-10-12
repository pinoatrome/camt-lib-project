"""Build and parse ISO 20022 camt.029.001.14 (ResolutionOfInvestigation): the answer to a recall.

The payee's PSP answers a camt.056 (`camt.camt056`) when it doesn't send the
money back: refused (RJCR), with a reason — the customer refused (CUST), didn't
answer (NOAS), the money is already returned (ARDT), the account is closed
(AC04) or has no funds (AM04), a legal decision (LEGL), no such payment (NOOR)
— or still being looked at (PDCR). A recall it accepts is answered with the
pacs.004 PaymentReturn (reason FOCR) sending the money back instead.

`Sts/Conf` holds the outcome of the whole case; each `CxlDtls/TxInfAndSts` the
outcome for one payment asked back (`TxCxlSts`), with its reason. Parsing
matches elements by local name, so any camt.029 version reads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from lxml import etree

from ._investigation import (
    CaseAssignment,
    agent,
    build_amount,
    build_assignment,
    build_original_references,
    build_reason,
    check_amount,
    check_assignment,
    check_code,
    check_id,
    check_info,
    read_amount,
    read_assignment,
    read_reason,
    read_root,
    required,
)
from .builder import sub
from .enums import iso20022_namespace
from .exceptions import CamtError, CamtParseError
from .parser import _child, _children, _path, _text

_NAMESPACE = iso20022_namespace("camt.029", "001.14")

# The case's outcome (Sts/Conf, ExternalInvestigationExecutionConfirmation1Code).
CANCELLED = "CNCL"
REJECTED = "RJCR"
PENDING = "PDCR"

# One payment's outcome (TxCxlSts, CancellationIndividualStatus1Code).
ACCEPTED_REQUEST = "ACCR"
REJECTED_REQUEST = "RJCR"
PENDING_REQUEST = "PDCR"
_PAYMENT_STATUSES = {ACCEPTED_REQUEST, REJECTED_REQUEST, PENDING_REQUEST, "PACR"}

# Common reasons for refusing (CancellationStatusReason3Choice/Cd).
CUSTOMER_REFUSED = "CUST"
NO_ANSWER_FROM_CUSTOMER = "NOAS"
ALREADY_RETURNED = "ARDT"
CLOSED_ACCOUNT = "AC04"
INSUFFICIENT_FUNDS = "AM04"
LEGAL_DECISION = "LEGL"
NO_ORIGINAL_TRANSACTION = "NOOR"


@dataclass
class RecallAnswer:
    """One `CxlDtls/TxInfAndSts`: what became of one payment asked back."""

    original_message_id: str
    original_end_to_end_id: str
    status: str  # TxCxlSts: RJCR, PDCR, ACCR (PACR: partly accepted)
    reason_code: str | None = None
    additional_info: str | None = None
    original_message_name_id: str = "pacs.008.001.08"
    cancellation_status_id: str | None = None
    original_instruction_id: str | None = None
    original_transaction_id: str | None = None
    original_amount: Decimal | None = None
    currency: str = "EUR"

    @property
    def rejected(self) -> bool:
        return self.status == REJECTED_REQUEST

    @property
    def pending(self) -> bool:
        return self.status == PENDING_REQUEST


@dataclass
class ResolutionOfInvestigation:
    """A camt.029 message: the assignment, the case it resolves, its outcome and each payment's."""

    assignment: CaseAssignment
    status: str  # Sts/Conf: RJCR, PDCR, CNCL, ...
    answers: list[RecallAnswer] = field(default_factory=list)
    resolved_case_id: str | None = None
    resolved_case_creator_bic: str | None = None


def _check(resolution: ResolutionOfInvestigation) -> None:
    check_assignment(resolution.assignment)
    check_code("The case's status (Sts/Conf)", resolution.status)
    check_id("The resolved case id", resolution.resolved_case_id, required=False)
    if resolution.resolved_case_id and not resolution.resolved_case_creator_bic:
        raise CamtError("A resolved case needs its creator's BIC (RslvdCase/Cretr).")
    for answer in resolution.answers:
        check_id("The original MsgId", answer.original_message_id)
        check_id("The original EndToEndId", answer.original_end_to_end_id)
        check_id("The cancellation status id", answer.cancellation_status_id, required=False)
        check_id("The original InstrId", answer.original_instruction_id, required=False)
        check_id("The original TxId", answer.original_transaction_id, required=False)
        if answer.status not in _PAYMENT_STATUSES:
            raise CamtError(f"A payment's status must be one of {sorted(_PAYMENT_STATUSES)}: {answer.status!r}")
        if answer.rejected and not answer.reason_code:
            raise CamtError(f"Refusing {answer.original_end_to_end_id} needs a reason.")
        if answer.reason_code is not None:
            check_code("The reason", answer.reason_code)
        check_info(answer.additional_info)
        check_amount(f"The original amount of {answer.original_end_to_end_id}", answer.original_amount, answer.currency)


def build_resolution_element(resolution: ResolutionOfInvestigation) -> etree._Element:
    """The `<Document>` tree of a camt.029.001.14. Raises `CamtError` if it isn't valid."""
    _check(resolution)
    root = etree.Element("Document", nsmap={None: _NAMESPACE})
    resolution_element = sub(root, "RsltnOfInvstgtn")
    build_assignment(resolution_element, resolution.assignment)
    if resolution.resolved_case_id:
        case = sub(resolution_element, "RslvdCase")
        sub(case, "Id", resolution.resolved_case_id)
        agent(case, "Cretr", resolution.resolved_case_creator_bic)
    sub(sub(resolution_element, "Sts"), "Conf", resolution.status)

    if resolution.answers:
        details = sub(resolution_element, "CxlDtls")
        for answer in resolution.answers:
            info = sub(details, "TxInfAndSts")
            if answer.cancellation_status_id:
                sub(info, "CxlStsId", answer.cancellation_status_id)
            build_original_references(
                info,
                message_id=answer.original_message_id,
                message_name_id=answer.original_message_name_id,
                instruction_id=answer.original_instruction_id,
                end_to_end_id=answer.original_end_to_end_id,
                transaction_id=answer.original_transaction_id,
            )
            sub(info, "TxCxlSts", answer.status)
            build_reason(info, "CxlStsRsnInf", answer.reason_code, answer.additional_info)
            build_amount(info, "OrgnlIntrBkSttlmAmt", answer.original_amount, answer.currency)
    return root


def build_resolution_bytes(resolution: ResolutionOfInvestigation, *, pretty_print: bool = True) -> bytes:
    """The camt.029.001.14 XML of `resolution`, as bytes."""
    return etree.tostring(
        build_resolution_element(resolution), xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print,
    )


def build_resolution_string(resolution: ResolutionOfInvestigation, *, pretty_print: bool = True) -> str:
    """The camt.029.001.14 XML of `resolution`, as a string."""
    return build_resolution_bytes(resolution, pretty_print=pretty_print).decode("utf-8")


def parse_camt029(xml_bytes: bytes) -> ResolutionOfInvestigation:
    """Read a camt.029 (any version). Raises `CamtParseError` if it isn't a readable one."""
    resolution = read_root(xml_bytes, "camt.029", "RsltnOfInvstgtn")
    status = _text(_path(resolution, "Sts", "Conf"))
    if status is None:
        raise CamtParseError("Missing Sts/Conf: the case's outcome.")
    answers = []
    for details in _children(resolution, "CxlDtls"):
        for info in _children(details, "TxInfAndSts"):
            amount, currency = read_amount(info, "OrgnlIntrBkSttlmAmt")
            reason_code, additional_info = read_reason(_child(info, "CxlStsRsnInf"))
            answers.append(RecallAnswer(
                original_message_id=required(info, "OrgnlGrpInf", "OrgnlMsgId"),
                original_message_name_id=_text(_path(info, "OrgnlGrpInf", "OrgnlMsgNmId")) or "",
                cancellation_status_id=_text(_child(info, "CxlStsId")),
                original_instruction_id=_text(_child(info, "OrgnlInstrId")),
                original_end_to_end_id=required(info, "OrgnlEndToEndId"),
                original_transaction_id=_text(_child(info, "OrgnlTxId")),
                status=required(info, "TxCxlSts"),
                reason_code=reason_code,
                additional_info=additional_info,
                original_amount=amount,
                currency=currency or "EUR",
            ))
    return ResolutionOfInvestigation(
        assignment=read_assignment(resolution),
        status=status,
        answers=answers,
        resolved_case_id=_text(_path(resolution, "RslvdCase", "Id")),
        resolved_case_creator_bic=_text(_path(resolution, "RslvdCase", "Cretr", "Agt", "FinInstnId", "BICFI")),
    )
