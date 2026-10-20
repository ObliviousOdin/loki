"""Gateway admission must retry a conflict that disappeared during its holder probe."""
from __future__ import annotations

import time

import pytest

from gateway.run_bootstrap import _reserve_waiting_out_browse_reconcile
from gateway.runtime_ownership import OwnershipConflict, ProfileOwnership
from hermes_state_reconcile import BROWSE_RECONCILE_PURPOSE


@pytest.mark.platforms("linux", "macos")
@pytest.mark.parametrize("wait_s", [10.0, 0.0], ids=["within-budget", "expired-budget"])
@pytest.mark.parametrize("as_iterator", [False, True], ids=["reusable-homes", "one-shot-homes"])
def test_released_holder_during_conflict_probe_respects_the_wait_budget(tmp_path, monkeypatch, wait_s, as_iterator):
    home = tmp_path / "profile"
    holder = ProfileOwnership()
    holder.reserve([home], purpose=BROWSE_RECONCILE_PURPOSE)
    booting = ProfileOwnership()
    reserve = booting.reserve
    attempts = 0

    def release_after_failed_reservation(homes):
        nonlocal attempts
        attempts += 1
        try:
            return reserve(homes)
        except OwnershipConflict:
            # The maintenance process releases between the failed admission and
            # the real conflict probe. No sleeps or advisory-lock bypasses.
            holder.close()
            raise

    monkeypatch.setattr(booting, "reserve", release_after_failed_reservation)
    homes = iter([home]) if as_iterator else [home]
    started = time.monotonic()
    try:
        if wait_s:
            _reserve_waiting_out_browse_reconcile(booting, homes, wait_s=wait_s)
            assert booting.owns(home)
            assert attempts == 2
            contender = ProfileOwnership()
            try:
                with pytest.raises(OwnershipConflict):
                    contender.reserve([home])
            finally:
                contender.close()
        else:
            with pytest.raises(OwnershipConflict):
                _reserve_waiting_out_browse_reconcile(booting, homes, wait_s=wait_s)
            assert not booting.owns(home)
            assert attempts == 1
        assert time.monotonic() - started < 2
    finally:
        booting.close()
        holder.close()

    # Neither a successful reservation nor a deadline refusal leaves a lock.
    after = ProfileOwnership()
    try:
        after.reserve([home])
        assert after.owns(home)
    finally:
        after.close()
