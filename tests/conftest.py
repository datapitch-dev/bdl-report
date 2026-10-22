import json

import pytest

from bdl_report.client import BdlClient


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.status_code = status_code
        self.ok = status_code < 400
        self.headers = headers or {}
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class ScriptedSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def make_client():
    def factory(*responses, **kwargs):
        session = ScriptedSession(*responses)
        sleeps = []
        client = BdlClient(session=session, sleep=sleeps.append, min_interval=0, **kwargs)
        return client, session, sleeps

    return factory
