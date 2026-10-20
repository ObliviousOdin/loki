"""Bind disposable inherited subprocess fixtures as owned Loki children.

These tests exercise internal profile/runtime contracts after entry. Their
explicit legacy selector inputs describe synthetic test homes, so translate
them through the real public boundary once before spawning the owned child.
Fresh-entry isolation tests deliberately do not use this helper.
"""
from loki_identity import bind_loki_environment


def bind_fixture_child_env(environment):
    env = dict(environment)
    for key, value in list(env.items()):
        if key.startswith("HERMES_"):
            env["LOKI_" + key[7:]] = value
    env.pop("__LOKI_ENV_BOUND", None)
    bind_loki_environment(env)
    return env
