import importlib.util
import io
from pathlib import Path
import urllib.error

import pytest


SCRIPT = Path(__file__).parents[2] / "scripts" / "show_operational_summary.py"
SPEC = importlib.util.spec_from_file_location("show_operational_summary", SCRIPT)
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


class Response:
    def __init__(self, body, status=200):
        self.body = body.encode() if isinstance(body, str) else body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self.body


def envelope(health="HEALTHY"):
    return (
        '{"command":"collection-summary","contract_version":"1",'
        '"timestamp":"2026-08-25T00:00:00Z","result":"PASS",'
        '"exit_code":0,"data":{"collection_health":"%s"},'
        '"errors":[],"evidence_file":null}' % health
    )


def run(monkeypatch, capsys, response):
    monkeypatch.setattr(consumer.urllib.request, "urlopen", lambda *_a, **_k: response)
    result = consumer.main()
    return result, capsys.readouterr()


@pytest.mark.parametrize("health", ["HEALTHY", "DEGRADED", "UNHEALTHY"])
def test_valid_health_is_success(monkeypatch, capsys, health):
    result, captured = run(monkeypatch, capsys, Response(envelope(health)))

    assert result == 0
    assert captured.err == ""
    assert captured.out.splitlines() == [
        "CONSUMER_RESULT=PASS",
        "CONTRACT_VERSION=1",
        f"COLLECTION_HEALTH={health}",
    ]


def test_contract_version_mismatch_fails_closed(monkeypatch, capsys):
    body = envelope().replace('"contract_version":"1"', '"contract_version":"2"')
    result, captured = run(monkeypatch, capsys, Response(body))

    assert result == 1
    assert "FAILURE_KIND=CONTRACT" in captured.out
    assert "COLLECTION_HEALTH=" not in captured.out


def test_invalid_collection_health_fails_closed(monkeypatch, capsys):
    result, captured = run(monkeypatch, capsys, Response(envelope("UNKNOWN")))

    assert result == 1
    assert "FAILURE_KIND=CONTRACT" in captured.out
    assert "COLLECTION_HEALTH=" not in captured.out


def test_invalid_json_is_contract_failure(monkeypatch, capsys):
    result, captured = run(monkeypatch, capsys, Response("not JSON"))

    assert result == 1
    assert "FAILURE_KIND=CONTRACT" in captured.out


def test_transport_failure(monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise urllib.error.URLError("connection refused: secret detail")

    monkeypatch.setattr(consumer.urllib.request, "urlopen", fail)
    result = consumer.main()
    captured = capsys.readouterr()

    assert result == 1
    assert "FAILURE_KIND=TRANSPORT" in captured.out
    assert "secret detail" not in captured.out


def http_error(body):
    return urllib.error.HTTPError(
        consumer.ENDPOINT, 500, "internal server detail", {}, io.BytesIO(body.encode())
    )


def test_valid_http_500_failure_envelope_is_api_failure(monkeypatch, capsys):
    body = (
        '{"command":"collection-summary","contract_version":"1",'
        '"timestamp":"2026-08-25T00:00:00Z","result":"FAIL",'
        '"exit_code":100,"data":{},"errors":["sensitive server detail"],'
        '"evidence_file":null}'
    )
    result, captured = run(monkeypatch, capsys, http_error(body))

    assert result == 1
    assert "FAILURE_KIND=API" in captured.out
    assert "COLLECTION_HEALTH=" not in captured.out
    assert "sensitive server detail" not in captured.out


def test_malformed_http_500_body_is_contract_failure(monkeypatch, capsys):
    result, captured = run(monkeypatch, capsys, http_error("not JSON"))

    assert result == 1
    assert "FAILURE_KIND=CONTRACT" in captured.out
    assert "internal server detail" not in captured.out


def test_unexpected_internal_exception_details_are_not_exposed(monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise RuntimeError("private implementation detail")

    monkeypatch.setattr(consumer.urllib.request, "urlopen", fail)
    result = consumer.main()
    captured = capsys.readouterr()

    assert result == 1
    assert "FAILURE_KIND=TRANSPORT" in captured.out
    assert "private implementation detail" not in captured.out
    assert "Traceback" not in captured.out + captured.err


def test_source_respects_dependency_boundary():
    source = SCRIPT.read_text()

    assert "services" not in source
    assert "adapters" not in source
    assert "models.operational_summary" not in source
