"""Job creation and its atomic request receipt; scheduler registration remains the caller's step."""
from typing import Any, Optional


def create_job(*, creation_request=None, **options):
    from cron import jobs as store
    if creation_request is None:
        job = _build_job(**options)
        with store._jobs_lock():
            store.save_jobs(store.load_jobs() + [job])
        return job
    from cron.job_creation_receipts import create
    return create(creation_request, options, lambda: _build_job(**options))


def _build_job(
    prompt: Optional[str],
    schedule: str,
    name: Optional[str] = None,
    repeat: Optional[int] = None,
    deliver: Optional[str] = None,
    origin: Optional[dict[str, Any]] = None,
    skill: Optional[str] = None,
    skills: Optional[list[str]] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    script: Optional[str] = None,
    context_from: Optional[str | list[str]] = None,
    enabled_toolsets: Optional[list[str]] = None,
    workdir: Optional[str] = None,
    no_agent: bool = False,
    attach_to_session: Optional[bool] = None,
    monitor_script: Optional[str] = None,
    monitor_url: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    failure_deliver: Optional[str] = None,
    paused: bool = False,
    paused_reason: Optional[str] = None,
    pinned: bool = False,
    interpreter: Optional[str] = None,
) -> dict[str, Any]:
    """Create a new cron job and return the stored record.

    deliver defaults to "origin" when ``origin`` is given, else "local"; repeat None = forever.
    script: stdout is injected as prompt context, or with ``no_agent=True`` IS the job (stdout
    delivered verbatim, requires ``script``). context_from: job id(s) whose latest output is
    injected. workdir: absolute cwd for tools/scripts. monitor_script/monitor_url: cheap monitor
    source run FIRST each tick; unchanged output suppresses the agent run (mutually exclusive,
    incompatible with ``no_agent``). reasoning_effort: per-job pin; capability NOT validated.
    interpreter: absolute/``~`` Python for ``.py`` script/monitor_script, validated at run time
    (a venv can be rebuilt or moved after creation)."""
    from cron import jobs as store
    if not isinstance(paused, bool):
        raise ValueError("paused must be a boolean.")
    if paused_reason is not None and not isinstance(paused_reason, str):
        raise ValueError("paused_reason must be a string.")
    if paused_reason is not None and not paused:
        raise ValueError("paused_reason requires paused=True.")
    parsed_schedule = store.parse_schedule(schedule)
    # Normalize repeat: treat 0 or negative values as None (infinite). String forms
    # ('forever'/'once'/numeric) coerce via normalize_repeat_value — the shared chokepoint with update paths
    # (#66824/#64520/#7142/#71987/#95706).
    repeat = store.normalize_repeat_value(repeat)
    if parsed_schedule["kind"] == "once" and repeat is None:
        repeat = 1
    if deliver is None:
        deliver = "origin" if origin else "local"
    job_id = store.uuid.uuid4().hex[:12]
    now = store._hermes_now().isoformat()

    raw = locals()
    f = {key: norm(raw[key]) for key, norm in store._CREATE_FIELD_NORMALIZERS.items()}
    normalized_skills = store._normalize_skill_list(skill, skills)
    normalized_attach = attach_to_session if isinstance(attach_to_session, bool) else None
    normalized_reasoning_effort = store._normalize_reasoning_effort(reasoning_effort)

    store._validate_job_mode_invariants(f["monitor_script"], f["monitor_url"], f["no_agent"], f["script"])
    prompt_text = store._coerce_job_text(prompt).strip()
    if not prompt_text and not f["script"] and not normalized_skills:
        raise ValueError(store.EMPTY_PAYLOAD_ERROR)
    # Reject gateway-lifecycle commands (respawn loops) here, not just in the CLI: covers the tool.
    from cron.lifecycle_guard import check_gateway_lifecycle
    check_gateway_lifecycle(prompt_text, f["script"])

    label_source = (
        prompt_text
        or (normalized_skills[0] if normalized_skills else None)
        or (f["script"] if f["no_agent"] else None)
        or "cron job"
    )
    name = name or label_source[:50].strip()
    if pinned and not f["model"]:
        f["provider"], f["model"] = store._main_model_pin()
    next_run_at = store._next_run_or_reject_past_oneshot(parsed_schedule, name, schedule, "")

    job = {
        "id": job_id,
        "name": name,
        "prompt": prompt_text,
        "skills": normalized_skills,
        "skill": normalized_skills[0] if normalized_skills else None,
        "model": f["model"],
        "provider": f["provider"],
        "base_url": f["base_url"],
        "script": f["script"],
        "no_agent": f["no_agent"],
        "monitor_script": f["monitor_script"],
        "monitor_url": f["monitor_url"],
        "monitor_state": None,
        "context_from": f["context_from"],
        "schedule": parsed_schedule,
        "schedule_display": parsed_schedule.get("display", schedule),
        "repeat": {"times": repeat, "completed": 0},  # times None = forever
        "enabled": not paused,
        "state": "paused" if paused else "scheduled",
        "paused_at": now if paused else None,
        "paused_reason": ((paused_reason or "").strip() or "Created paused; awaiting operator approval.") if paused else None,
        "created_at": now,
        "next_run_at": None if paused else next_run_at,
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "last_delivery_error": None,
        # Targets acked without message_id/raw_response (accepted but UNVERIFIED).
        "last_delivery_unverified": None,
        # Most recent failed run ({at, detail}); NOT cleared by a later success (#118354).
        "last_failure": None,
        "failure_streak": 0,
        "deliver": deliver,
        "origin": origin,  # Tracks where job was created for "origin" delivery
        "enabled_toolsets": f["enabled_toolsets"],
        "workdir": f["workdir"],
    }
    # Optional keys are persisted only when explicitly set: an absent key falls back to global
    # config (attach/reasoning) or to ``deliver`` (failure_deliver), byte-identical to pre-feature
    # jobs.
    for key, value in (
        ("attach_to_session", normalized_attach), ("reasoning_effort", normalized_reasoning_effort),
        ("failure_deliver", f["failure_deliver"]), ("interpreter", f["interpreter"]),
    ):
        if value is not None:
            job[key] = value

    return job
