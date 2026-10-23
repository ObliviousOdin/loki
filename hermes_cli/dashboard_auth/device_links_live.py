"""Retire linked-device viewers on revocation without changing canonical session ownership."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import threading

from hermes_cli.dashboard_auth.device_links_provider import context_store

_lock = threading.Lock()
_channels: dict[tuple[str, str], set] = {}


class Channel:
    def __init__(self, store, device_id):
        self.store, self.device_id = store, device_id
        self.loop = asyncio.get_running_loop()
        self.revoked = asyncio.Event()


def attach_device_channel(ws, context):
    """Called only with server-minted ticket or verified Session provenance."""
    store = context_store(context)
    if store is None:
        return False
    channel = Channel(store, context['device_id'])
    with _lock:
        _channels.setdefault((store.home, channel.device_id), set()).add(channel)
        # Close the verification→registration race against a concurrent revoke.
        if not store.is_active(channel.device_id):
            _detach(channel)
            return False
    ws.scope['loki.device_channel'] = channel
    ready = ws.scope.get('loki.device_channel_ready')
    if ready is not None:
        ready.set()
    return True


def _detach(channel):
    key = (channel.store.home, channel.device_id)
    entries = _channels.get(key)
    if entries is not None:
        entries.discard(channel)
        if not entries:
            _channels.pop(key, None)


def revoke_channels(store, device_id):
    with _lock:
        channels = tuple(_channels.get((store.home, device_id), ()))
    for channel in channels:
        channel.loop.call_soon_threadsafe(channel.revoked.set)


class DeviceLinkSocketMiddleware:
    """Watch the authenticated channel, including while a handler is waiting elsewhere."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'websocket':
            await self.app(scope, receive, send)
            return
        scope['loki.device_channel_ready'] = asyncio.Event()
        closed = False

        async def guarded_send(message):
            nonlocal closed
            if closed:
                return
            channel = scope.get('loki.device_channel')
            if channel is not None and not channel.store.is_active(channel.device_id):
                closed = True
                await send({'type': 'websocket.close', 'code': 4401})
                channel.revoked.set()
                return
            if message['type'] == 'websocket.close':
                closed = True
            await send(message)

        async def wait_revoked():
            await scope['loki.device_channel_ready'].wait()
            await scope['loki.device_channel'].revoked.wait()

        async def guarded_receive():
            message = await receive()
            channel = scope.get('loki.device_channel')
            if channel is not None and not channel.store.is_active(channel.device_id):
                channel.revoked.set()
                return {'type': 'websocket.disconnect', 'code': 4401}
            return message

        application = asyncio.create_task(self.app(scope, guarded_receive, guarded_send))
        watcher = asyncio.create_task(wait_revoked())
        try:
            done, _ = await asyncio.wait((application, watcher), return_when=asyncio.FIRST_COMPLETED)
            if watcher in done and not closed:
                closed = True
                await send({'type': 'websocket.close', 'code': 4401})
            if application in done:
                await application
        finally:
            for task in (application, watcher):
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            channel = scope.get('loki.device_channel')
            if channel is not None:
                with _lock:
                    _detach(channel)
