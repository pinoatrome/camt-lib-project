from datetime import datetime

from lxml import etree

from camt.camt046 import (
    build_get_reservation_request_bytes,
    build_get_reservation_request_string,
)

_NS = {"n": "urn:iso:std:iso:20022:tech:xsd:camt.046.001.08"}


def test_build_get_reservation_request_is_well_formed_and_uses_camt046_namespace():
    xml = build_get_reservation_request_bytes(
        "IT60X0542811101000000123456",
        "MSGID-1",
        creation_datetime=datetime(2026, 9, 25, 8, 0, 0),
    )

    root = etree.fromstring(xml)
    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:camt.046.001.08}Document"


def test_build_get_reservation_request_carries_msg_id_and_iban():
    xml = build_get_reservation_request_bytes("IT60X0542811101000000123456", "MSGID-1")
    root = etree.fromstring(xml)

    msg_id = root.find(".//n:MsgHdr/n:MsgId", namespaces=_NS)
    iban = root.find(".//n:SchCrit/n:AcctId/n:IBAN", namespaces=_NS)

    assert msg_id.text == "MSGID-1"
    assert iban.text == "IT60X0542811101000000123456"


def test_build_get_reservation_request_encodes_proprietary_account_id():
    xml = build_get_reservation_request_bytes(
        "EU4900000000000001", "MSGID-1", id_type="DEAN"
    )
    root = etree.fromstring(xml)

    othr_id = root.find(".//n:SchCrit/n:AcctId/n:Othr/n:Id", namespaces=_NS)
    scheme = root.find(".//n:SchCrit/n:AcctId/n:Othr/n:SchmeNm/n:Prtry", namespaces=_NS)

    assert othr_id.text == "EU4900000000000001"
    assert scheme.text == "DEAN"


def test_build_get_reservation_request_without_type_omits_rsvatn_tp():
    xml = build_get_reservation_request_bytes("IT60X0542811101000000123456", "MSGID-1")
    root = etree.fromstring(xml)

    assert root.find(".//n:CurRsvatnTp", namespaces=_NS) is None


def test_build_get_reservation_request_applies_reservation_type_filter():
    xml = build_get_reservation_request_bytes(
        "IT60X0542811101000000123456", "MSGID-1", reservation_type="MMR"
    )
    root = etree.fromstring(xml)

    rsvatn_tp = root.find(".//n:SchCrit/n:CurRsvatnTp/n:Cd", namespaces=_NS)
    assert rsvatn_tp.text == "MMR"


def test_build_get_reservation_request_string_matches_bytes_decoded():
    kwargs = dict(
        reservation_type="MMR",
        creation_datetime=datetime(2026, 9, 25, 8, 0, 0),
    )
    xml_string = build_get_reservation_request_string(
        "IT60X0542811101000000123456", "MSGID-1", **kwargs
    )
    xml_bytes = build_get_reservation_request_bytes(
        "IT60X0542811101000000123456", "MSGID-1", **kwargs
    )

    assert xml_string == xml_bytes.decode("utf-8")


def test_build_get_reservation_request_names_a_longer_type_as_proprietary():
    root = etree.fromstring(build_get_reservation_request_bytes("IT60X0542811101000000123456", "REQ-9", reservation_type="MINRESERVE"))

    assert root.findtext(".//n:SchCrit/n:CurRsvatnTp/n:Prtry", namespaces=_NS) == "MINRESERVE"


def test_build_get_reservation_request_puts_the_type_before_the_account():
    root = etree.fromstring(build_get_reservation_request_bytes("IT60X0542811101000000123456", "REQ-9", reservation_type="UPAR"))

    assert [etree.QName(child).localname for child in root.find(".//n:SchCrit", namespaces=_NS)] == ["CurRsvatnTp", "AcctId"]
