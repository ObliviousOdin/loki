"""Public retry guidance keeps durable completion facts and caller-supplied text intact."""
from __future__ import annotations

import json

import pytest

from hermes_cli import update_completion, update_receipt


@pytest.mark.parametrize("retry", [None, "Hermes task: retry `hermes update` from /srv/Hermes project"])
def test_followup_uses_loki_default_but_keeps_explicit_retry_text(capsys, retry):
    reason = "Hermes job in /srv/Hermes project refused"
    with update_receipt.update_receipt_scope():
        update_receipt.record_followup("custom-Hermes-step", reason, **({"retry": retry} if retry else {}))
    output = capsys.readouterr().out
    assert "Update follow-up 'custom-Hermes-step' did not finish: " + reason in output
    assert (retry or "the next launch or `loki update` retries it") in output


def test_interrupted_run_names_loki_without_changing_its_verdict(capsys):
    with update_receipt.update_receipt_scope():
        update_receipt.begin_update_receipt()
        update_receipt.finalize_interrupted_update_receipt("Hermes operator interrupted")
    assert "the next launch or `loki update` finishes them" in capsys.readouterr().out
    receipt = update_receipt.read_latest_receipt()
    assert receipt["outcome"] == "interrupted" and receipt["exit_code"] == 130
    assert receipt["stop_reason"] == "Hermes operator interrupted"


@pytest.mark.parametrize("boundary", ["lost-child", "post-commit"])
def test_owed_completion_uses_loki_retry_without_changing_receipt(tmp_path, capsys, boundary):
    reason = "Hermes build in /srv/Hermes project refused"
    source = tmp_path / "Hermes checkout"
    source.mkdir()
    with update_receipt.update_receipt_scope():
        update_receipt.begin_update_receipt()
        record = dict(update_receipt._current.get().data)
        request = {"source": str(source), "receipt": record, "desktop": False, "gateway_mode": False}
        if boundary == "lost-child":
            result = update_completion.settle_lost_completion(request, reason)
            retry = "the next launch or `loki update` finishes it"
            step = "completion"
        else:
            result_path = tmp_path / "result.json"
            assert update_completion._settle_after_commit(request, result_path, "build", reason) == 0
            result = json.loads(result_path.read_text(encoding="utf-8-sig"))
            retry = "the next launch or `loki update` retries it"
            step = "build"
    output = capsys.readouterr().out
    assert retry in output and reason in output
    assert result["exit_code"] == 0 and result["receipt"]["outcome"] == "success"
    assert result["receipt"]["update_id"] == record["update_id"]
    followups = result["receipt"]["followups"]
    assert len(followups) == 1 and {"step": step, "reason": reason}.items() <= followups[0].items()
    assert isinstance(followups[0]["at"], str) and followups[0]["at"]
