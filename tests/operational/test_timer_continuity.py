import json
from datetime import datetime, timezone

import pytest


def utc(value):
    assert value.endswith("Z")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def validate(failure_text, recovery_text, timer, now):
    failure, recovery = json.loads(failure_text), json.loads(recovery_text)
    assert utc(recovery["started_at"]) > utc(failure["completed_at"])
    assert utc(recovery["started_at"]) < utc(recovery["completed_at"])
    assert recovery["result"] == "PASS" and recovery["exit_code"] == 0
    assert timer["UnitFileState"] == "enabled"
    assert timer["ActiveState"] == "active"
    assert utc(timer["LAST"]) <= utc(recovery["completed_at"])
    assert utc(timer["NEXT"]) > now


def document(start, end, result, code):
    return json.dumps({"started_at": start, "completed_at": end, "result": result, "exit_code": code})


FAILURE = document("2026-08-05T07:40:06.440497Z", "2026-08-05T07:40:06.513875Z", "FAIL", 70)
RECOVERY = document("2026-08-05T07:55:07.991815Z", "2026-08-05T07:55:08.066198Z", "PASS", 0)
STATE = {"UnitFileState": "enabled", "ActiveState": "active", "LAST": "2026-08-05T07:55:07.882630Z", "NEXT": "2026-08-05T08:10:07.882630Z"}


def test_accepts_later_pass_zero_recovery_with_continuing_timer():
    validate(FAILURE, RECOVERY, STATE, utc("2026-08-05T08:00:00.000000Z"))


def test_rejects_recovery_at_failure_completion():
    recovery = document("2026-08-05T07:40:06.513875Z", "2026-08-05T07:40:07.000000Z", "PASS", 0)
    with pytest.raises(AssertionError):
        validate(FAILURE, recovery, STATE, utc("2026-08-05T07:50:00.000000Z"))


@pytest.mark.parametrize("field,value", [("UnitFileState", "disabled"), ("ActiveState", "inactive"), ("NEXT", "2026-08-05T07:59:59.000000Z")])
def test_requires_enabled_active_and_future_next(field, value):
    state = dict(STATE)
    state[field] = value
    with pytest.raises(AssertionError):
        validate(FAILURE, RECOVERY, state, utc("2026-08-05T08:00:00.000000Z"))
