#!/usr/bin/env python3
"""Read the operational collection summary through the public HTTP API."""

import json
import urllib.error
import urllib.request


ENDPOINT = "http://127.0.0.1:8100/api/operational/collection-summary"
TIMEOUT_SECONDS = 5
VALID_HEALTH_STATES = {"HEALTHY", "DEGRADED", "UNHEALTHY"}


def _parse_json(body):
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _has_common_contract_fields(payload):
    return (
        payload.get("command") == "collection-summary"
        and payload.get("contract_version") == "1"
        and isinstance(payload.get("timestamp"), str)
        and payload.get("timestamp") != ""
        and payload.get("evidence_file") is None
    )


def _success_health(payload):
    if not _has_common_contract_fields(payload):
        return None
    if payload.get("result") != "PASS" or type(payload.get("exit_code")) is not int:
        return None
    if payload["exit_code"] != 0 or payload.get("errors") != []:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    health = data.get("collection_health")
    return health if health in VALID_HEALTH_STATES else None


def _is_api_failure(payload):
    return (
        _has_common_contract_fields(payload)
        and payload.get("result") == "FAIL"
        and type(payload.get("exit_code")) is int
        and payload["exit_code"] == 100
        and payload.get("data") == {}
        and isinstance(payload.get("errors"), list)
        and len(payload["errors"]) > 0
    )


def _print_failure(kind, message):
    print("CONSUMER_RESULT=FAIL")
    print(f"FAILURE_KIND={kind}")
    print(f"ERROR={message}")
    return 1


def main():
    request = urllib.request.Request(ENDPOINT, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.getcode()
            body = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        try:
            body = error.read()
        except Exception:
            return _print_failure(
                "CONTRACT", "operational summary contract validation failed"
            )
    except (urllib.error.URLError, OSError, TimeoutError):
        return _print_failure("TRANSPORT", "operational summary request failed")
    except Exception:
        return _print_failure("TRANSPORT", "operational summary request failed")

    payload = _parse_json(body)
    if payload is None:
        return _print_failure(
            "CONTRACT", "operational summary contract validation failed"
        )

    if status == 200:
        health = _success_health(payload)
        if health is not None:
            print("CONSUMER_RESULT=PASS")
            print("CONTRACT_VERSION=1")
            print(f"COLLECTION_HEALTH={health}")
            return 0
    elif status == 500 and _is_api_failure(payload):
        return _print_failure("API", "operational summary API execution failed")

    return _print_failure("CONTRACT", "operational summary contract validation failed")


if __name__ == "__main__":
    raise SystemExit(main())
