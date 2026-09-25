from datetime import date, datetime

from lxml import etree

from camt.camt018 import (
    build_get_business_day_request_bytes,
    build_get_business_day_request_string,
)

_NS = {"n": "urn:iso:std:iso:20022:tech:xsd:camt.018.001.04"}


def test_build_get_business_day_request_is_well_formed_and_uses_camt018_namespace():
    xml = build_get_business_day_request_bytes(
        "TARGET2",
        "MSGID-1",
        creation_datetime=datetime(2026, 9, 25, 6, 0, 0),
    )

    root = etree.fromstring(xml)
    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:camt.018.001.04}Document"


def test_build_get_business_day_request_carries_msg_id_and_system_id():
    xml = build_get_business_day_request_bytes("TARGET2", "MSGID-1")
    root = etree.fromstring(xml)

    msg_id = root.find(".//n:MsgHdr/n:MsgId", namespaces=_NS)
    sys_id = root.find(".//n:SchCrit/n:SysId/n:Cd", namespaces=_NS)

    assert msg_id.text == "MSGID-1"
    assert sys_id.text == "TARGET2"


def test_build_get_business_day_request_defaults_creation_datetime_to_now():
    xml = build_get_business_day_request_bytes("TARGET2", "MSGID-1")
    root = etree.fromstring(xml)

    cre_dt_tm = root.find(".//n:MsgHdr/n:CreDtTm", namespaces=_NS)
    assert cre_dt_tm.text  # non-empty, parseable ISO datetime
    datetime.fromisoformat(cre_dt_tm.text)


def test_build_get_business_day_request_without_date_omits_sys_dt():
    xml = build_get_business_day_request_bytes("TARGET2", "MSGID-1")
    root = etree.fromstring(xml)

    assert root.find(".//n:SysDt", namespaces=_NS) is None


def test_build_get_business_day_request_encodes_business_date():
    xml = build_get_business_day_request_bytes(
        "TARGET2", "MSGID-1", business_date=date(2026, 9, 25)
    )
    root = etree.fromstring(xml)

    sys_dt = root.find(".//n:SchCrit/n:SysDt", namespaces=_NS)
    assert sys_dt.text == "2026-09-25"


def test_build_get_business_day_request_string_matches_bytes_decoded():
    kwargs = dict(
        business_date=date(2026, 9, 25),
        creation_datetime=datetime(2026, 9, 25, 6, 0, 0),
    )
    xml_string = build_get_business_day_request_string("TARGET2", "MSGID-1", **kwargs)
    xml_bytes = build_get_business_day_request_bytes("TARGET2", "MSGID-1", **kwargs)

    assert xml_string == xml_bytes.decode("utf-8")
