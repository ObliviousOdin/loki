"""Authored cron commands are Loki; dynamic operator/provider strings stay exact."""
from cron.scheduler_failure_copy import (
    blocked_config_notice,
    generic_failure_notice,
    inactivity_notice,
    provider_failure_notice,
    script_timeout_notice,
)


def test_cron_remedies_preserve_hermes_named_user_values():
    title = "Hermes quarterly job"
    job_id = "hermes-owned-job-42"
    detail = "Hermes user text: keep hermes cron here"
    backup = "Hermes fallback text: keep hermes cron here."
    messages = [
        provider_failure_notice(title, job_id, "auth", backup_provider_phrase=backup, provider="openai-codex"),
        provider_failure_notice(title, job_id, "rate_limit", backup_provider_phrase=backup),
        generic_failure_notice(title, job_id, detail),
        script_timeout_notice(title, job_id),
        inactivity_notice(title, job_id),
    ]
    for message in messages:
        assert f"Cron '{title}'" in message
        assert f"loki cron runs {job_id}" in message
        assert f"loki cron run {job_id}" in message
    assert "auth add openai-codex --type oauth" in messages[0]
    assert backup in messages[1]
    assert detail in messages[2]
    blocked = blocked_config_notice(title, detail)
    assert title in blocked and detail in blocked
    assert "Loki will try again" in blocked and "loki cron doctor" in blocked
