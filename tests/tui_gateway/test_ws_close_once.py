"""Send deadlines and fanout aborts share one WebSocket close attempt."""
from __future__ import annotations

import asyncio

import pytest

from tui_gateway.ws import WSTransport


class _BlockedSocket:
    def __init__(self):
        self.sending = asyncio.Event()
        self.closing = asyncio.Event()
        self.release_close = asyncio.Event()
        self.codes = []
        self.close_tasks = set()

    async def send_text(self, _payload):
        self.sending.set()
        await asyncio.Event().wait()

    async def close(self, code=1000):
        task = asyncio.current_task()
        self.close_tasks.add(task)
        self.codes.append(code)
        self.closing.set()
        try:
            await self.release_close.wait()
        finally:
            self.close_tasks.remove(task)


@pytest.mark.parametrize("first", ["deadline", "abort"])
def test_timeout_and_abort_close_the_socket_only_once(monkeypatch, first):
    monkeypatch.setattr("tui_gateway.ws._WS_SEND_DEADLINE_S", 0.05)

    async def exercise():
        socket = _BlockedSocket()
        transport = WSTransport(socket, asyncio.get_running_loop(), peer="close-race")
        progress = asyncio.create_task(transport.write_async({"id": "pending", "result": {}}))
        try:
            await asyncio.wait_for(socket.sending.wait(), timeout=2.0)
            if first == "abort":
                # Abort starts closing while the real send is still awaiting its deadline.
                transport.abort()
            await asyncio.wait_for(socket.closing.wait(), timeout=2.0)
            assert await asyncio.wait_for(progress, timeout=2.0) is False
            if first == "deadline":
                # The deadline already started closing; a later overflow cannot close twice.
                transport.abort()
            await asyncio.sleep(0)  # Run the newly queued close attempt before observing it.
            assert socket.codes == [1011]
            assert transport.closed
            assert await transport.write_async({"id": "after-close", "result": {}}) is False
        finally:
            transport.close()
            socket.release_close.set()
            if not progress.done():
                progress.cancel()
            await asyncio.gather(progress, *tuple(socket.close_tasks), return_exceptions=True)

    asyncio.run(exercise())
