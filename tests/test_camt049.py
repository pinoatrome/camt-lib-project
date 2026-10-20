from datetime import datetime

from lxml import etree

from camt.camt049 import (
    build_delete_reservation_request_bytes,
    build_delete_reservation_request_string,
)

_NS = {"n": "urn:iso:std:iso:20022:tech:xsd:camt.049.001.07"}


def test_build_delete_reservation_request_is_well_formed_and_uses_camt049_namespace():
    xml = build_delete_reservation_request_bytes(
        "IT60X0542811101000000123456",
        "MMR",
        msg_id="DEL-1",
        creation_datetime=datetime(2026, 9, 25, 9, 0, 0),
    )
    root = etree.fromstring(xml)
    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:camt.049.001.07}Document"


def test_build_delete_reservation_request_encodes_iban_account():
    xml = build_delete_reservation_request_bytes(
        "IT60X0542811101000000123456", "MMR", msg_id="DEL-1"
    )
    root = etree.fromstring(xml)
    iban = root.find("n:DelRsvatn/n:CurRsvatn/n:AcctId/n:IBAN", namespaces=_NS)
    assert iban.text == "IT60X0542811101000000123456"


def test_build_delete_reservation_request_encodes_proprietary_account():
    xml = build_delete_reservation_request_bytes(
        "EU4900000000000001", "MMR", id_type="DEAN", msg_id="DEL-1"
    )
    root = etree.fromstring(xml)
    othr_id = root.find("n:DelRsvatn/n:CurRsvatn/n:AcctId/n:Othr/n:Id", namespaces=_NS)
    scheme = root.find("n:DelRsvatn/n:CurRsvatn/n:AcctId/n:Othr/n:SchmeNm/n:Prtry", namespaces=_NS)
    assert othr_id.text == "EU4900000000000001"
    assert scheme.text == "DEAN"


def test_build_delete_reservation_request_carries_reservation_type_and_msg_id():
    xml = build_delete_reservation_request_bytes(
        "IT60X0542811101000000123456", "MMR", msg_id="DEL-1"
    )
    root = etree.fromstring(xml)
    rsvatn_tp = root.find("n:DelRsvatn/n:CurRsvatn/n:Tp/n:Cd", namespaces=_NS)
    msg_id = root.find(".//n:MsgHdr/n:MsgId", namespaces=_NS)

    assert rsvatn_tp.text == "MMR"
    assert msg_id.text == "DEL-1"


def test_build_delete_reservation_request_has_no_amount():
    xml = build_delete_reservation_request_bytes(
        "IT60X0542811101000000123456", "MMR", msg_id="DEL-1"
    )
    root = etree.fromstring(xml)
    assert root.find(".//n:NewRsvatnValSet", namespaces=_NS) is None


def test_build_delete_reservation_request_auto_generates_msg_id_when_omitted():
    xml = build_delete_reservation_request_bytes("IT60X0542811101000000123456", "MMR")
    root = etree.fromstring(xml)
    msg_id = root.find(".//n:MsgHdr/n:MsgId", namespaces=_NS).text
    assert msg_id.startswith("DELRSV-")


def test_build_delete_reservation_request_string_matches_bytes_decoded():
    kwargs = dict(msg_id="DEL-2", creation_datetime=datetime(2026, 9, 25, 9, 0, 0))
    xml_string = build_delete_reservation_request_string(
        "IT60X0542811101000000123456", "MMR", **kwargs
    )
    xml_bytes = build_delete_reservation_request_bytes(
        "IT60X0542811101000000123456", "MMR", **kwargs
    )
    assert xml_string == xml_bytes.decode("utf-8")
