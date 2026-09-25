from datetime import datetime

from lxml import etree

from camt.camt048 import (
    build_modify_reservation_request_bytes,
    build_modify_reservation_request_string,
)

_NS = {"n": "urn:iso:std:iso:20022:tech:xsd:camt.048.001.05"}


def test_build_modify_reservation_request_is_well_formed_and_uses_camt048_namespace():
    xml = build_modify_reservation_request_bytes(
        "IT60X0542811101000000123456",
        "MMR",
        75000.0,
        msg_id="MOD-1",
        creation_datetime=datetime(2026, 9, 25, 9, 0, 0),
    )
    root = etree.fromstring(xml)
    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:camt.048.001.05}Document"


def test_build_modify_reservation_request_encodes_iban_account():
    xml = build_modify_reservation_request_bytes(
        "IT60X0542811101000000123456", "MMR", 75000.0, msg_id="MOD-1"
    )
    root = etree.fromstring(xml)
    iban = root.find(".//n:RsvatnModfyInstr/n:AcctId/n:Id/n:IBAN", namespaces=_NS)
    assert iban.text == "IT60X0542811101000000123456"


def test_build_modify_reservation_request_encodes_proprietary_account():
    xml = build_modify_reservation_request_bytes(
        "DEAN-IT-0001-ALPHA", "MMR", 75000.0, id_type="DEAN", msg_id="MOD-1"
    )
    root = etree.fromstring(xml)
    othr_id = root.find(".//n:AcctId/n:Id/n:Othr/n:Id", namespaces=_NS)
    scheme = root.find(".//n:AcctId/n:Id/n:Othr/n:SchmeNm/n:Prtry", namespaces=_NS)
    assert othr_id.text == "DEAN-IT-0001-ALPHA"
    assert scheme.text == "DEAN"


def test_build_modify_reservation_request_carries_type_and_new_amount():
    xml = build_modify_reservation_request_bytes(
        "IT60X0542811101000000123456",
        "MMR",
        75000.0,
        currency="USD",
        msg_id="MOD-1",
    )
    root = etree.fromstring(xml)
    rsvatn_tp = root.find(".//n:RsvatnModfyInstr/n:RsvatnTp/n:Cd", namespaces=_NS)
    new_amt = root.find(".//n:RsvatnModfyInstr/n:NewRsvatnAmt", namespaces=_NS)
    msg_id = root.find(".//n:MsgHdr/n:MsgId", namespaces=_NS)

    assert rsvatn_tp.text == "MMR"
    assert new_amt.text == "75000.00"
    assert new_amt.get("Ccy") == "USD"
    assert msg_id.text == "MOD-1"


def test_build_modify_reservation_request_auto_generates_msg_id_when_omitted():
    xml = build_modify_reservation_request_bytes(
        "IT60X0542811101000000123456", "MMR", 75000.0
    )
    root = etree.fromstring(xml)
    msg_id = root.find(".//n:MsgHdr/n:MsgId", namespaces=_NS).text
    assert msg_id.startswith("MODRSV-")


def test_build_modify_reservation_request_string_matches_bytes_decoded():
    kwargs = dict(msg_id="MOD-2", creation_datetime=datetime(2026, 9, 25, 9, 0, 0))
    xml_string = build_modify_reservation_request_string(
        "IT60X0542811101000000123456", "MMR", 75000.0, **kwargs
    )
    xml_bytes = build_modify_reservation_request_bytes(
        "IT60X0542811101000000123456", "MMR", 75000.0, **kwargs
    )
    assert xml_string == xml_bytes.decode("utf-8")
