"""Telling an IBAN from a DEAN (`camt.identifiers`): a DEAN is shaped like an IBAN, and is never written as one."""
from lxml import etree

from camt import parse_bytes
from camt.camt050 import build_liquidity_transfer_bytes
from camt.identifiers import is_dean, is_iban
from camt.testing import statement_xml

DEAN = "EU4900000000000001"
IBAN = "IT60X0542811101000000123456"


def test_a_dean_is_eu_and_16_digits():
    assert is_dean(DEAN)
    assert not is_dean(IBAN) and not is_dean("EU490000000000001") and not is_dean("DCA-IT-UNCRITM1-0001")


def test_a_dean_isn_t_an_iban():
    assert is_iban(IBAN) and not is_iban(DEAN) and not is_iban("DCA-IT-UNCRITM1-0001")


def test_a_liquidity_transfer_writes_a_dean_as_another_id():
    root = etree.fromstring(build_liquidity_transfer_bytes(DEAN, IBAN, 10.0, msg_id="LT-1", end_to_end_id="E2E-1"))
    ns = {"n": root.nsmap[None]}

    assert root.findtext(".//n:DbtrAcct/n:Id/n:Othr/n:Id", namespaces=ns) == DEAN
    assert root.findtext(".//n:CdtrAcct/n:Id/n:IBAN", namespaces=ns) == IBAN


def test_a_statement_of_a_dean_has_it_as_another_id():
    [statement] = parse_bytes(statement_xml(account=DEAN)).statements

    assert (statement.account_other_id, statement.account_iban) == (DEAN, None)
