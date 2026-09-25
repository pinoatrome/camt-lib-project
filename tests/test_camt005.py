from datetime import datetime

from lxml import etree

from camt.camt005 import (
    build_get_transaction_delta_request_bytes,
    build_get_transaction_delta_request_string,
    build_get_transaction_request_bytes,
    build_get_transaction_request_string,
)

_NS = {"n": "urn:iso:std:iso:20022:tech:xsd:camt.005.001.06"}


def test_build_get_transaction_request_is_well_formed_and_uses_camt005_namespace():
    xml = build_get_transaction_request_bytes(
        "IT60X0542811101000000123456",
        "MSGID-1",
        creation_datetime=datetime(2026, 9, 2, 10, 0, 0),
    )

    root = etree.fromstring(xml)
    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:camt.005.001.06}Document"


def test_build_get_transaction_request_carries_msg_id_and_iban():
    xml = build_get_transaction_request_bytes("IT60X0542811101000000123456", "MSGID-1")
    root = etree.fromstring(xml)

    msg_id = root.find(".//n:MsgHdr/n:MsgId", namespaces=_NS)
    iban = root.find(".//n:NewCrit/n:SchCrit/n:AcctId/n:EQ/n:Id/n:IBAN", namespaces=_NS)

    assert msg_id.text == "MSGID-1"
    assert iban.text == "IT60X0542811101000000123456"


def test_build_get_transaction_request_encodes_proprietary_account_id():
    xml = build_get_transaction_request_bytes(
        "DEAN-IT-0001-ALPHA", "MSGID-1", id_type="DEAN"
    )
    root = etree.fromstring(xml)

    othr_id = root.find(".//n:AcctId/n:EQ/n:Id/n:Othr/n:Id", namespaces=_NS)
    scheme = root.find(".//n:AcctId/n:EQ/n:Id/n:Othr/n:SchmeNm/n:Prtry", namespaces=_NS)

    assert othr_id.text == "DEAN-IT-0001-ALPHA"
    assert scheme.text == "DEAN"


def test_build_get_transaction_request_applies_optional_filters():
    xml = build_get_transaction_request_bytes(
        "IT60X0542811101000000123456",
        "MSGID-1",
        from_datetime=datetime(2026, 9, 1, 0, 0, 0),
        to_datetime=datetime(2026, 9, 2, 0, 0, 0),
        entry_status="BOOK",
    )
    root = etree.fromstring(xml)

    fr_dt = root.find(".//n:SchCrit/n:FrToDt/n:FrDtTm", namespaces=_NS)
    to_dt = root.find(".//n:SchCrit/n:FrToDt/n:ToDtTm", namespaces=_NS)
    status = root.find(".//n:SchCrit/n:EntrySts/n:Cd", namespaces=_NS)

    assert fr_dt.text == "2026-09-01T00:00:00"
    assert to_dt.text == "2026-09-02T00:00:00"
    assert status.text == "BOOK"


def test_build_get_transaction_request_without_filters_omits_them():
    xml = build_get_transaction_request_bytes("IT60X0542811101000000123456", "MSGID-1")
    root = etree.fromstring(xml)

    assert root.find(".//n:FrToDt", namespaces=_NS) is None
    assert root.find(".//n:EntrySts", namespaces=_NS) is None
    assert root.find(".//n:NewQryNm", namespaces=_NS) is None


def test_build_get_transaction_request_registers_new_query_name():
    xml = build_get_transaction_request_bytes(
        "IT60X0542811101000000123456", "MSGID-1", new_query_name="DAILY-RECON"
    )
    root = etree.fromstring(xml)

    new_qry_nm = root.find(".//n:NewCrit/n:NewQryNm", namespaces=_NS)
    assert new_qry_nm.text == "DAILY-RECON"


def test_build_get_transaction_request_string_matches_bytes_decoded():
    kwargs = dict(creation_datetime=datetime(2026, 9, 2, 10, 0, 0))
    xml_string = build_get_transaction_request_string(
        "IT60X0542811101000000123456", "MSGID-1", **kwargs
    )
    xml_bytes = build_get_transaction_request_bytes(
        "IT60X0542811101000000123456", "MSGID-1", **kwargs
    )

    assert xml_string == xml_bytes.decode("utf-8")


def test_build_get_transaction_delta_request_references_query_name_only():
    xml = build_get_transaction_delta_request_bytes(
        "DAILY-RECON", "MSGID-2", creation_datetime=datetime(2026, 9, 3, 10, 0, 0)
    )
    root = etree.fromstring(xml)

    qry_nm = root.find(".//n:TxCrit/n:SchCrit/n:QryNm", namespaces=_NS)
    msg_id = root.find(".//n:MsgHdr/n:MsgId", namespaces=_NS)

    assert qry_nm.text == "DAILY-RECON"
    assert msg_id.text == "MSGID-2"
    # A delta follow-up carries no NewCrit/search criteria of its own.
    assert root.find(".//n:NewCrit", namespaces=_NS) is None
    assert root.find(".//n:AcctId", namespaces=_NS) is None


def test_build_get_transaction_delta_request_string_matches_bytes_decoded():
    kwargs = dict(creation_datetime=datetime(2026, 9, 3, 10, 0, 0))
    xml_string = build_get_transaction_delta_request_string(
        "DAILY-RECON", "MSGID-2", **kwargs
    )
    xml_bytes = build_get_transaction_delta_request_bytes(
        "DAILY-RECON", "MSGID-2", **kwargs
    )

    assert xml_string == xml_bytes.decode("utf-8")
