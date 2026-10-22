from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from bdl_report.client import BdlClient, BdlError, Unit, Variable
from tests.conftest import FakeResponse, ScriptedSession


def test_data_by_unit_parses_values_and_skips_nulls(make_client):
    payload = {
        "results": [
            {
                "id": 72305,
                "values": [
                    {"year": "2023", "val": 100, "attrId": 1},
                    {"year": "2024", "val": None, "attrId": 2},
                ],
            },
            {"id": 60559, "values": []},
        ]
    }
    client, session, _ = make_client(FakeResponse(payload))
    data = client.data_by_unit("099999999996", [72305, 60559], [2023, 2024])

    assert data == {72305: {2023: 100.0}}
    query = parse_qs(urlsplit(session.calls[0][0]).query)
    assert query["var-id"] == ["72305", "60559"]
    assert query["year"] == ["2023", "2024"]
    assert query["format"] == ["json"]


def test_pagination_follows_next_link(make_client):
    client, session, _ = make_client(
        FakeResponse({"results": [{"id": "1", "name": "A", "level": 6}], "links": {"next": "x"}}),
        FakeResponse({"results": [{"id": "2", "name": "B", "level": 5}], "links": {}}),
    )
    units = client.search_units("a")
    assert [u.id for u in units] == ["1", "2"]
    assert "page=1" in session.calls[1][0]


def test_responses_are_cached(make_client):
    client, session, _ = make_client(FakeResponse({"id": 72305, "n1": "ludność"}))
    assert client.variable(72305).name == "ludność"
    assert client.variable(72305).name == "ludność"
    assert len(session.calls) == 1


def test_api_key_goes_into_header(make_client):
    client, session, _ = make_client(FakeResponse({"id": 1, "n1": "x"}), api_key="KEY")
    client.variable(1)
    assert session.calls[0][1] == {"X-ClientId": "KEY"}


def test_429_waits_retry_after_then_succeeds(make_client):
    client, _, sleeps = make_client(
        FakeResponse({}, 429, {"Retry-After": "7"}), FakeResponse({"id": 1, "n1": "x"})
    )
    client.variable(1)
    assert sleeps == [7.0]


def test_limit_gives_helpful_message(make_client):
    client, _, _ = make_client(*[FakeResponse({}, 429)] * 4)
    with pytest.raises(BdlError, match="GUS_API_KEY"):
        client.variable(1)


def test_connection_errors_are_retried(make_client):
    client, session, _ = make_client(
        requests.ConnectionError("down"), FakeResponse({"id": 1, "n1": "x"})
    )
    client.variable(1)
    assert len(session.calls) == 2


def test_throttle_spaces_requests():
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    session = ScriptedSession(*[FakeResponse({"id": i, "n1": "x"}) for i in range(3)])
    client = BdlClient(session=session, sleep=sleep, clock=lambda: now[0], min_interval=0.25)
    for i in range(3):
        client.variable(i)
    assert sleeps == [0.25, 0.25]


def test_models():
    unit = Unit.from_api({"id": "1", "name": "Sopot", "level": 6, "kind": "1", "parentId": "2"})
    assert unit.level_name == "gmina miejska"
    var = Variable.from_api({"id": 5, "n1": "ludność", "n2": "ogółem", "measureUnitName": "osoba"})
    assert (var.name, var.unit) == ("ludność, ogółem", "osoba")


def test_unknown_unit_raises_but_empty_search_does_not(make_client):
    client, _, _ = make_client(FakeResponse({}, 404), FakeResponse({}, 404))
    with pytest.raises(BdlError, match="nie zna"):
        client.unit("999999999999")
    assert client.search_units("zzz") == []
