"""`validate` and `schema_errors`: the schema check any caller can make."""
import pytest

from camt import CamtError, CamtValidationError, schema_errors, validate
from camt.testing import notification_xml, receipt_xml


def test_a_valid_document_is_returned_as_it_is():
    xml = notification_xml()
    assert validate(xml) is xml
    assert schema_errors(xml) == []


def test_a_misplaced_element_is_refused_with_the_schemas_finding():
    xml = receipt_xml(original_message_id="PSPLT-0001")
    misplaced = xml.replace(b"</RctDtls>", b"<MsgHdr/></RctDtls>", 1)

    with pytest.raises(CamtValidationError) as caught:
        validate(misplaced)

    assert caught.value.errors and "MsgHdr" in caught.value.errors[0]
    assert isinstance(caught.value, CamtError)


@pytest.mark.parametrize("xml, start", [
    (b"not xml", "not XML"),
    (b"<Document/>", "not a camt message"),
    (b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"/>', "not a camt message"),
    (b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.08"/>', "no schema for camt.054.001.08: the library checks camt.054.001.14"),
    (b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.999.001.01"/>', "no schema for camt.999.001.01"),
])
def test_what_it_cannot_check_is_one_error(xml, start):
    [error] = schema_errors(xml)
    assert error.startswith(start)
    with pytest.raises(CamtValidationError):
        validate(xml)


def test_a_document_missing_a_mandatory_element_is_refused():
    assert schema_errors(notification_xml().replace(b"<MsgId>TEST-NTF-0001</MsgId>", b"", 1))
