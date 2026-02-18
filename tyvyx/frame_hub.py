"""Asyncio-based fan-out hub for MJPEG frames.

Each MJPEG HTTP client gets its own asyncio.Queue so multiple consumers
don't steal frames from each other.
"""

import asyncio
from typing import Optional


class FrameHub:

    def __init__(self, per_client_queue_size: int = 2):
        self._per_client_queue_size = per_client_queue_size
        self._clients: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(self._per_client_queue_size)
        async with self._lock:
            self._clients.add(q)
        return q

    async def unregister(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._clients.discard(q)

    async def publish(self, frame: Optional[bytes]) -> None:
        async with self._lock:
            clients = list(self._clients)

        for q in clients:
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                try:
                    _ = q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(frame)
                except Exception:
                    await self.unregister(q)

    async def shutdown(self) -> None:
        """Send None to all clients to signal stream end, then clear."""
        async with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(None)
                except Exception:
                    pass
