from datetime import datetime

from lxml import etree

from camt.camt003 import (
    build_get_account_request_bytes,
    build_get_account_request_string,
)

_NS = {"n": "urn:iso:std:iso:20022:tech:xsd:camt.003.001.02"}


def test_build_get_account_request_bytes_is_well_formed_and_uses_camt003_namespace():
    xml = build_get_account_request_bytes(
        "IT60X0542811101000000123456",
        "MSGID-1",
        creation_datetime=datetime(2026, 9, 2, 10, 0, 0),
    )

    root = etree.fromstring(xml)
    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:camt.003.001.02}Document"


def test_build_get_account_request_carries_msg_id_and_iban():
    xml = build_get_account_request_bytes("IT60X0542811101000000123456", "MSGID-1")
    root = etree.fromstring(xml)

    msg_id = root.find(".//n:MsgHdr/n:MsgId", namespaces=_NS)
    iban = root.find(".//n:AcctId/n:EQ/n:Id/n:IBAN", namespaces=_NS)

    assert msg_id.text == "MSGID-1"
    assert iban.text == "IT60X0542811101000000123456"


def test_build_get_account_request_defaults_creation_datetime_to_now():
    xml = build_get_account_request_bytes("IT60X0542811101000000123456", "MSGID-1")
    root = etree.fromstring(xml)

    cre_dt_tm = root.find(".//n:MsgHdr/n:CreDtTm", namespaces=_NS)
    assert cre_dt_tm.text  # non-empty, parseable ISO datetime
    datetime.fromisoformat(cre_dt_tm.text)


def test_build_get_account_request_string_matches_bytes_decoded():
    kwargs = dict(creation_datetime=datetime(2026, 9, 2, 10, 0, 0))
    xml_string = build_get_account_request_string(
        "IT60X0542811101000000123456", "MSGID-1", **kwargs
    )
    xml_bytes = build_get_account_request_bytes(
        "IT60X0542811101000000123456", "MSGID-1", **kwargs
    )

    assert xml_string == xml_bytes.decode("utf-8")
