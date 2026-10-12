from datetime import datetime

import pytest
from lxml import etree

from camt import CamtError
from camt.camt050 import build_liquidity_transfer_bytes, build_liquidity_transfer_string

_NS = {"n": "urn:iso:std:iso:20022:tech:xsd:camt.050.001.07"}


def test_build_liquidity_transfer_bytes_is_well_formed_and_uses_camt050_namespace():
    xml = build_liquidity_transfer_bytes(
        "IT60X0542811101000000MCA001",
        "IT60X0542811101000000DCA001",
        100.0,
        msg_id="LT-1",
        end_to_end_id="E2E-1",
        creation_datetime=datetime(2026, 9, 2, 10, 0, 0),
    )
    root = etree.fromstring(xml)
    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:camt.050.001.07}Document"


def test_build_liquidity_transfer_encodes_iban_accounts():
    xml = build_liquidity_transfer_bytes(
        "IT60X0542811101000000MCA001",
        "IT60X0542811101000000DCA001",
        100.0,
        msg_id="LT-1",
        end_to_end_id="E2E-1",
    )
    root = etree.fromstring(xml)
    dbtr_iban = root.find(".//n:DbtrAcct/n:Id/n:IBAN", namespaces=_NS)
    cdtr_iban = root.find(".//n:CdtrAcct/n:Id/n:IBAN", namespaces=_NS)
    assert dbtr_iban.text == "IT60X0542811101000000MCA001"
    assert cdtr_iban.text == "IT60X0542811101000000DCA001"


def test_build_liquidity_transfer_encodes_proprietary_accounts():
    xml = build_liquidity_transfer_bytes(
        "MCA-INTERNAL-001",
        "DCA-INTERNAL-001",
        50.0,
        msg_id="LT-2",
        end_to_end_id="E2E-2",
    )
    root = etree.fromstring(xml)
    dbtr_id = root.find(".//n:DbtrAcct/n:Id/n:Othr/n:Id", namespaces=_NS)
    cdtr_id = root.find(".//n:CdtrAcct/n:Id/n:Othr/n:Id", namespaces=_NS)
    assert dbtr_id.text == "MCA-INTERNAL-001"
    assert cdtr_id.text == "DCA-INTERNAL-001"


def test_build_liquidity_transfer_carries_amount_currency_and_end_to_end_id():
    xml = build_liquidity_transfer_bytes(
        "IT60X0542811101000000MCA001",
        "IT60X0542811101000000DCA001",
        1234.5,
        currency="USD",
        msg_id="LT-3",
        end_to_end_id="E2E-3",
    )
    root = etree.fromstring(xml)
    amt = root.find(".//n:TrfdAmt/n:AmtWthCcy", namespaces=_NS)
    e2e = root.find("n:LqdtyCdtTrf/n:LqdtyCdtTrf/n:LqdtyTrfId/n:EndToEndId", namespaces=_NS)
    msg_id = root.find("n:LqdtyCdtTrf/n:MsgHdr/n:MsgId", namespaces=_NS)

    assert amt.text == "1234.50"
    assert amt.get("Ccy") == "USD"
    assert e2e.text == "E2E-3"
    assert msg_id.text == "LT-3"


def test_build_liquidity_transfer_uses_custom_agent_ids():
    xml = build_liquidity_transfer_bytes(
        "IT60X0542811101000000MCA001",
        "IT60X0542811101000000DCA001",
        10.0,
        debtor_agent_id="PSP-01",
        creditor_agent_id="DESP-DCA-SVC",
        msg_id="LT-5",
        end_to_end_id="E2E-5",
    )
    root = etree.fromstring(xml)
    dbtr = root.find(".//n:Dbtr/n:FinInstnId/n:Othr/n:Id", namespaces=_NS)
    cdtr = root.find(".//n:Cdtr/n:FinInstnId/n:Othr/n:Id", namespaces=_NS)
    assert dbtr.text == "PSP-01"
    assert cdtr.text == "DESP-DCA-SVC"


def test_build_liquidity_transfer_auto_generates_ids_when_omitted():
    xml = build_liquidity_transfer_bytes(
        "IT60X0542811101000000MCA001", "IT60X0542811101000000DCA001", 10.0
    )
    root = etree.fromstring(xml)
    msg_id = root.find("n:LqdtyCdtTrf/n:MsgHdr/n:MsgId", namespaces=_NS).text
    e2e_id = root.find("n:LqdtyCdtTrf/n:LqdtyCdtTrf/n:LqdtyTrfId/n:EndToEndId", namespaces=_NS).text
    assert msg_id.startswith("LT-")
    assert e2e_id.startswith("E2E-")


def test_build_liquidity_transfer_string_matches_bytes_decoded():
    kwargs = dict(
        msg_id="LT-4",
        end_to_end_id="E2E-4",
        creation_datetime=datetime(2026, 9, 2, 10, 0, 0),
    )
    xml_string = build_liquidity_transfer_string(
        "IT60X0542811101000000MCA001", "IT60X0542811101000000DCA001", 100.0, **kwargs
    )
    xml_bytes = build_liquidity_transfer_bytes(
        "IT60X0542811101000000MCA001", "IT60X0542811101000000DCA001", 100.0, **kwargs
    )
    assert xml_string == xml_bytes.decode("utf-8")


def test_build_liquidity_transfer_names_bic_agents_by_bic():
    xml = build_liquidity_transfer_bytes(
        "MCA-IT-UNCRITM1-0001", "DCA-IT-UNCRITM1-0001", 10.0,
        debtor_agent_id="UNCRITM1XXX", creditor_agent_id="UNCRITM1",
    )
    root = etree.fromstring(xml)
    assert root.findtext(".//n:Dbtr/n:FinInstnId/n:BICFI", namespaces=_NS) == "UNCRITM1XXX"
    assert root.findtext(".//n:Cdtr/n:FinInstnId/n:BICFI", namespaces=_NS) == "UNCRITM1"


def test_build_liquidity_transfer_follows_the_schema_order():
    """MsgHdr, then the transfer: its id, the creditor side, the amount, the debtor side."""
    root = etree.fromstring(build_liquidity_transfer_bytes("MCA-1", "DCA-1", 10.0))
    transfer = root.find("n:LqdtyCdtTrf/n:LqdtyCdtTrf", namespaces=_NS)

    assert [etree.QName(child).localname for child in root.find("n:LqdtyCdtTrf", namespaces=_NS)] == ["MsgHdr", "LqdtyCdtTrf"]
    assert [etree.QName(child).localname for child in transfer] == [
        "LqdtyTrfId", "Cdtr", "CdtrAcct", "TrfdAmt", "Dbtr", "DbtrAcct",
    ]


@pytest.mark.parametrize("amount", [0.0, -5.0])
def test_build_liquidity_transfer_refuses_an_amount_that_is_not_positive(amount):
    with pytest.raises(CamtError, match="must be positive"):
        build_liquidity_transfer_bytes("MCA-1", "DCA-1", amount)
