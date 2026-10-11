from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

from camt.camt056 import (
    CaseAssignment,
    DUPLICATE,
    PaymentCancellationRequest,
    RecalledPayment,
    build_cancellation_request_bytes,
    build_cancellation_request_string,
    parse_camt056,
)
from camt.exceptions import CamtError, CamtParseError

FIXTURES = Path(__file__).parent / "fixtures"
_NS = {"n": "urn:iso:std:iso:20022:tech:xsd:camt.056.001.08"}


def _request(**changes) -> PaymentCancellationRequest:
    payment = {
        "original_message_id": "PSPPAY-0001",
        "original_end_to_end_id": "E2E-PAY-0001",
        "reason_code": DUPLICATE,
        "original_amount": Decimal("100.00"),
        "cancellation_id": "CXL-0001",
        "additional_info": "Paid twice",
        **changes.pop("payment", {}),
    }
    return PaymentCancellationRequest(**{
        "assignment": CaseAssignment("RCL-0001", "UNCRITM1XXX", "BCITITMMXXX", datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)),
        "case_id": "CASE-0001",
        "payments": [RecalledPayment(**payment)],
        **changes,
    })


def test_build_asks_the_payment_back_with_its_reason():
    root = etree.fromstring(build_cancellation_request_bytes(_request()))

    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:camt.056.001.08}Document"
    assignment = root.find("n:FIToFIPmtCxlReq/n:Assgnmt", _NS)
    assert assignment.findtext("n:Id", namespaces=_NS) == "RCL-0001"
    assert assignment.findtext("n:Assgnr/n:Agt/n:FinInstnId/n:BICFI", namespaces=_NS) == "UNCRITM1XXX"
    assert assignment.findtext("n:Assgne/n:Agt/n:FinInstnId/n:BICFI", namespaces=_NS) == "BCITITMMXXX"
    assert root.findtext("n:FIToFIPmtCxlReq/n:Case/n:Cretr/n:Agt/n:FinInstnId/n:BICFI", namespaces=_NS) == "UNCRITM1XXX"
    info = root.find("n:FIToFIPmtCxlReq/n:Undrlyg/n:TxInf", _NS)
    assert [etree.QName(child).localname for child in info] == [
        "CxlId", "OrgnlGrpInf", "OrgnlEndToEndId", "OrgnlIntrBkSttlmAmt", "CxlRsnInf",
    ]
    assert info.findtext("n:CxlRsnInf/n:Rsn/n:Cd", namespaces=_NS) == "DUPL"
    assert info.find("n:OrgnlIntrBkSttlmAmt", _NS).get("Ccy") == "EUR"


def test_round_trip():
    original = _request()

    assert parse_camt056(build_cancellation_request_bytes(original)) == original
    assert build_cancellation_request_string(original).startswith("<?xml")


def test_parse_reads_every_payment_asked_back():
    request = parse_camt056((FIXTURES / "camt056_recall_sample.xml").read_bytes())

    assert (request.assignment.id, request.assignment.assigner_bic, request.assignment.assignee_bic) == (
        "RCL-0001", "BCITITMMXXX", "UNCRITM1XXX",
    )
    assert request.assignment.creation_datetime == datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)
    assert request.case_id == "CASE-0001"
    duplicate, fraud = request.payments
    assert (duplicate.original_end_to_end_id, duplicate.original_amount, duplicate.reason_code) == (
        "E2E-DEUR-0420", Decimal("80.00"), "DUPL",
    )
    assert (duplicate.cancellation_id, duplicate.additional_info) == ("CXL-0001", "Paid twice")
    assert (fraud.original_instruction_id, fraud.original_transaction_id, fraud.reason_code) == (
        "INSTR-0430", "TX-0430", "FRAD",
    )
    assert fraud.original_amount is None


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"assignment": CaseAssignment("", "UNCRITM1XXX", "BCITITMMXXX", datetime(2026, 10, 11))}, "assignment id"),
        ({"assignment": CaseAssignment("A", "NOTABIC", "BCITITMMXXX", datetime(2026, 10, 11))}, "assigner must be a BIC"),
        ({"payments": []}, "at least one payment"),
        ({"payment": {"reason_code": "dupl"}}, "cancellation reason"),
        ({"payment": {"original_end_to_end_id": "E" * 36}}, "EndToEndId must be 1 to 35"),
        ({"payment": {"original_amount": Decimal("-1.00")}}, "must be positive"),
        ({"payment": {"additional_info": "x" * 106}}, "over 105"),
    ],
    ids=["no-assignment-id", "bad-bic", "no-payment", "lowercase-reason", "long-e2e", "negative-amount", "long-info"],
)
def test_invalid_requests_arent_built(changes, error):
    with pytest.raises(CamtError, match=error):
        build_cancellation_request_bytes(_request(**changes))


@pytest.mark.parametrize(
    "change, error",
    [
        ((b"<Rsn><Cd>FRAD</Cd></Rsn>", b""), "Missing TxInf/CxlRsnInf/Rsn"),
        ((b"<OrgnlEndToEndId>E2E-DEUR-0430</OrgnlEndToEndId>", b""), "Missing OrgnlEndToEndId"),
        ((b"<Id>RCL-0001</Id>", b""), "Missing Id"),
        ((b"camt.056.001.08", b"camt.029.001.09"), "Not a camt.056 Document"),
        ((b"<Document", b"<Docum"), "Malformed XML"),
    ],
    ids=["no-reason", "no-e2e", "no-assignment-id", "other-message", "malformed"],
)
def test_unreadable_requests_are_refused(change, error):
    xml = (FIXTURES / "camt056_recall_sample.xml").read_bytes().replace(*change)

    with pytest.raises(CamtParseError, match=error):
        parse_camt056(xml)
