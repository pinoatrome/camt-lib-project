"""Build and parse ISO 20022 camt.056.001.08 (FIToFIPaymentCancellationRequest): a recall.

The payer's PSP asks the payee's PSP to send back payments it made (pacs.008),
with a reason: a duplicate (DUPL), a fraud (FRAD), a technical problem (TECH),
the customer's request (CUST), a wrong amount (AM09) or account (AC03), an
undue payment (UPAY). The payee's PSP answers with a pacs.004 PaymentReturn
(reason FOCR) when it sends the money back, or with a camt.029
ResolutionOfInvestigation (`camt.camt029`) when it doesn't, or not yet.

Like the account query and liquidity transfer messages, it's built and parsed
here directly rather than through `camt.builder`/`camt.parser`. Parsing matches
elements by local name, so any camt.056 version reads.
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

_NAMESPACE = iso20022_namespace("camt.056", "001.08")

# Common cancellation reasons (ExternalCancellationReason1Code).
DUPLICATE = "DUPL"
FRAUD = "FRAD"
TECHNICAL_PROBLEM = "TECH"
REQUESTED_BY_CUSTOMER = "CUST"
WRONG_AMOUNT = "AM09"
WRONG_ACCOUNT = "AC03"
UNDUE_PAYMENT = "UPAY"


@dataclass
class RecalledPayment:
    """One `Undrlyg/TxInf`: a payment asked back, by its original references."""

    original_message_id: str
    original_end_to_end_id: str
    reason_code: str
    original_amount: Decimal | None = None
    currency: str = "EUR"
    original_message_name_id: str = "pacs.008.001.08"
    cancellation_id: str | None = None
    original_instruction_id: str | None = None
    original_transaction_id: str | None = None
    additional_info: str | None = None


@dataclass
class PaymentCancellationRequest:
    """A camt.056 message: the assignment, the case it opens, the payments asked back."""

    assignment: CaseAssignment
    payments: list[RecalledPayment] = field(default_factory=list)
    case_id: str | None = None


def _check(request: PaymentCancellationRequest) -> None:
    check_assignment(request.assignment)
    check_id("The case id", request.case_id, required=False)
    if not request.payments:
        raise CamtError("A camt.056 asks back at least one payment.")
    for payment in request.payments:
        check_id("The original MsgId", payment.original_message_id)
        check_id("The original EndToEndId", payment.original_end_to_end_id)
        check_id("The cancellation id", payment.cancellation_id, required=False)
        check_id("The original InstrId", payment.original_instruction_id, required=False)
        check_id("The original TxId", payment.original_transaction_id, required=False)
        check_code("The cancellation reason", payment.reason_code)
        check_info(payment.additional_info)
        check_amount(f"The original amount of {payment.original_end_to_end_id}", payment.original_amount,
                     payment.currency)


def build_cancellation_request_element(request: PaymentCancellationRequest) -> etree._Element:
    """The `<Document>` tree of a camt.056.001.08. Raises `CamtError` if it isn't valid."""
    _check(request)
    root = etree.Element("Document", nsmap={None: _NAMESPACE})
    cancellation = sub(root, "FIToFIPmtCxlReq")
    build_assignment(cancellation, request.assignment)
    if request.case_id:
        case = sub(cancellation, "Case")
        sub(case, "Id", request.case_id)
        agent(case, "Cretr", request.assignment.assigner_bic)

    underlying = sub(cancellation, "Undrlyg")
    for payment in request.payments:
        info = sub(underlying, "TxInf")
        if payment.cancellation_id:
            sub(info, "CxlId", payment.cancellation_id)
        build_original_references(
            info,
            message_id=payment.original_message_id,
            message_name_id=payment.original_message_name_id,
            instruction_id=payment.original_instruction_id,
            end_to_end_id=payment.original_end_to_end_id,
            transaction_id=payment.original_transaction_id,
        )
        build_amount(info, "OrgnlIntrBkSttlmAmt", payment.original_amount, payment.currency)
        build_reason(info, "CxlRsnInf", payment.reason_code, payment.additional_info)
    return root


def build_cancellation_request_bytes(request: PaymentCancellationRequest, *, pretty_print: bool = True) -> bytes:
    """The camt.056.001.08 XML of `request`, as bytes."""
    return etree.tostring(
        build_cancellation_request_element(request), xml_declaration=True, encoding="UTF-8",
        pretty_print=pretty_print,
    )


def build_cancellation_request_string(request: PaymentCancellationRequest, *, pretty_print: bool = True) -> str:
    """The camt.056.001.08 XML of `request`, as a string."""
    return build_cancellation_request_bytes(request, pretty_print=pretty_print).decode("utf-8")


def parse_camt056(xml_bytes: bytes) -> PaymentCancellationRequest:
    """Read a camt.056 (any version). Raises `CamtParseError` if it isn't a readable one."""
    cancellation = read_root(xml_bytes, "camt.056", "FIToFIPmtCxlReq")
    payments = []
    for underlying in _children(cancellation, "Undrlyg"):
        for info in _children(underlying, "TxInf"):
            amount, currency = read_amount(info, "OrgnlIntrBkSttlmAmt")
            reason_code, additional_info = read_reason(_child(info, "CxlRsnInf"))
            if reason_code is None:
                raise CamtParseError("Missing TxInf/CxlRsnInf/Rsn: why the payment is asked back.")
            payments.append(RecalledPayment(
                original_message_id=required(info, "OrgnlGrpInf", "OrgnlMsgId"),
                original_message_name_id=_text(_path(info, "OrgnlGrpInf", "OrgnlMsgNmId")) or "",
                cancellation_id=_text(_child(info, "CxlId")),
                original_instruction_id=_text(_child(info, "OrgnlInstrId")),
                original_end_to_end_id=required(info, "OrgnlEndToEndId"),
                original_transaction_id=_text(_child(info, "OrgnlTxId")),
                original_amount=amount,
                currency=currency or "EUR",
                reason_code=reason_code,
                additional_info=additional_info,
            ))
    if not payments:
        raise CamtParseError("No Undrlyg/TxInf in the camt.056: no payment asked back.")
    return PaymentCancellationRequest(
        assignment=read_assignment(cancellation),
        case_id=_text(_path(cancellation, "Case", "Id")),
        payments=payments,
    )
