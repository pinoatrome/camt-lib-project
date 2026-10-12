from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

from camt.camt029 import (
    CaseAssignment,
    CUSTOMER_REFUSED,
    PENDING_REQUEST,
    REJECTED,
    REJECTED_REQUEST,
    RecallAnswer,
    ResolutionOfInvestigation,
    build_resolution_bytes,
    parse_camt029,
)
from camt.exceptions import CamtError, CamtParseError

FIXTURES = Path(__file__).parent / "fixtures"
_NS = {"n": "urn:iso:std:iso:20022:tech:xsd:camt.029.001.14"}


def _resolution(**changes) -> ResolutionOfInvestigation:
    answer = {
        "original_message_id": "PSPPAY-0001",
        "original_end_to_end_id": "E2E-PAY-0001",
        "status": REJECTED_REQUEST,
        "reason_code": CUSTOMER_REFUSED,
        "additional_info": "Goods delivered",
        "original_amount": Decimal("100.00"),
        "cancellation_status_id": "CXLSTS-0001",
        **changes.pop("answer", {}),
    }
    return ResolutionOfInvestigation(**{
        "assignment": CaseAssignment("RES-0001", "BCITITMMXXX", "UNCRITM1XXX", datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)),
        "status": REJECTED,
        "resolved_case_id": "CASE-0001",
        "resolved_case_creator_bic": "UNCRITM1XXX",
        "answers": [RecallAnswer(**answer)],
        **changes,
    })


def test_build_refuses_the_recall_with_its_reason():
    root = etree.fromstring(build_resolution_bytes(_resolution()))

    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:camt.029.001.14}Document"
    resolution = root.find("n:RsltnOfInvstgtn", _NS)
    assert [etree.QName(child).localname for child in resolution] == ["Assgnmt", "RslvdCase", "Sts", "CxlDtls"]
    assert resolution.findtext("n:Sts/n:Conf", namespaces=_NS) == "RJCR"
    info = resolution.find("n:CxlDtls/n:TxInfAndSts", _NS)
    assert [etree.QName(child).localname for child in info] == [
        "CxlStsId", "OrgnlGrpInf", "OrgnlEndToEndId", "TxCxlSts", "CxlStsRsnInf", "OrgnlIntrBkSttlmAmt",
    ]
    assert info.findtext("n:CxlStsRsnInf/n:Rsn/n:Cd", namespaces=_NS) == "CUST"


def test_round_trip():
    original = _resolution()

    assert parse_camt029(build_resolution_bytes(original)) == original


def test_parse_reads_each_payments_outcome():
    resolution = parse_camt029((FIXTURES / "camt029_rejected_sample.xml").read_bytes())

    assert (resolution.status, resolution.resolved_case_id, resolution.resolved_case_creator_bic) == (
        "RJCR", "CASE-0001", "BCITITMMXXX",
    )
    assert resolution.assignment.assigner_bic == "UNCRITM1XXX"
    refused, pending = resolution.answers
    assert refused.rejected and not refused.pending
    assert (refused.reason_code, refused.additional_info, refused.original_amount) == (
        "CUST", "The payee refused: goods delivered", Decimal("80.00"),
    )
    assert pending.pending and pending.status == PENDING_REQUEST
    assert (pending.original_end_to_end_id, pending.reason_code) == ("E2E-DEUR-0430", None)


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"status": "rejected"}, "case's status"),
        ({"answer": {"status": "NOPE"}}, "payment's status must be one of"),
        ({"answer": {"reason_code": None}}, "needs a reason"),
        ({"resolved_case_creator_bic": None}, "creator's BIC"),
        ({"answer": {"original_message_id": ""}}, "original MsgId"),
    ],
    ids=["bad-case-status", "bad-payment-status", "refused-without-reason", "case-without-creator", "no-original"],
)
def test_invalid_resolutions_arent_built(changes, error):
    with pytest.raises(CamtError, match=error):
        build_resolution_bytes(_resolution(**changes))


def test_a_pending_answer_needs_no_reason():
    pending = _resolution(status="PDCR", answer={"status": PENDING_REQUEST, "reason_code": None, "additional_info": None})

    assert parse_camt029(build_resolution_bytes(pending)) == pending


@pytest.mark.parametrize(
    "change, error",
    [
        ((b"<Conf>RJCR</Conf>", b""), "Missing Sts/Conf"),
        ((b"<TxCxlSts>PDCR</TxCxlSts>", b""), "Missing TxCxlSts"),
        ((b"camt.029.001.14", b"camt.056.001.12"), "Not a camt.029 Document"),
    ],
    ids=["no-case-status", "no-payment-status", "other-message"],
)
def test_unreadable_resolutions_are_refused(change, error):
    xml = (FIXTURES / "camt029_rejected_sample.xml").read_bytes().replace(*change)

    with pytest.raises(CamtParseError, match=error):
        parse_camt029(xml)
