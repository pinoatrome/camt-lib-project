from pathlib import Path

import pytest

from camt.camt019 import Camt019Response, parse_camt019

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_camt019_success_response():
    xml = (FIXTURES / "camt019_success_sample.xml").read_bytes()
    result = parse_camt019(xml)

    assert isinstance(result, Camt019Response)
    assert result.response_msg_id == "RESP-0001"
    assert result.original_msg_id == "REQ-0001"
    assert result.created_at == "2026-09-25T06:00:00"
    assert result.error_code is None
    assert result.error_description is None

    business_day = result.business_day
    assert business_day is not None
    assert business_day.system_id == "TARGET2"
    assert business_day.business_date == "2026-09-25"
    assert business_day.status == "OPEN"


def test_parse_camt019_reads_all_events_in_order():
    xml = (FIXTURES / "camt019_success_sample.xml").read_bytes()
    events = parse_camt019(xml).business_day.events

    assert [e.code for e in events] == ["START", "CUT-OFF-CUST", "CUT-OFF-BANK", "END"]
    assert events[0].event_datetime == "2026-09-25T07:00:00"
    assert events[-1].event_datetime == "2026-09-25T18:45:00"


def test_business_day_info_event_time_looks_up_by_code():
    xml = (FIXTURES / "camt019_success_sample.xml").read_bytes()
    business_day = parse_camt019(xml).business_day

    assert business_day.event_time("CUT-OFF-CUST") == "2026-09-25T17:00:00"
    assert business_day.event_time("NO-SUCH-EVENT") is None


def test_parse_camt019_error_response_has_no_business_day():
    xml = (FIXTURES / "camt019_error_sample.xml").read_bytes()
    result = parse_camt019(xml)

    assert result.response_msg_id == "RESP-0002"
    assert result.original_msg_id == "REQ-0002"
    assert result.business_day is None
    assert result.error_code == "UNKNOWN_SYSTEM"
    assert result.error_description == "System not found"


def test_parse_camt019_missing_root_element_raises():
    bogus = b'<?xml version="1.0"?><Document xmlns="urn:example"><SomethingElse/></Document>'
    with pytest.raises(ValueError, match="RtrBizDayInf"):
        parse_camt019(bogus)


def test_parse_camt019_report_without_events():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.019.001.06">
  <RtrBizDayInf>
    <MsgHdr>
      <MsgId>RESP-0003</MsgId>
      <CreDtTm>2026-09-25T06:10:00</CreDtTm>
    </MsgHdr>
    <RptOrErr>
      <BizDayInfRpt>
        <SysId>
          <Cd>CLM</Cd>
        </SysId>
        <SysDt>2026-09-25</SysDt>
        <SysSts>
          <Cd>CLOSED</Cd>
        </SysSts>
      </BizDayInfRpt>
    </RptOrErr>
  </RtrBizDayInf>
</Document>"""
    result = parse_camt019(xml)

    assert result.original_msg_id is None  # no <OrgnlBizQry>
    business_day = result.business_day
    assert business_day.status == "CLOSED"
    assert business_day.events == []
