import pytest


class _FakeVideoStream:
    def __init__(self, src, prefer_tcp=False):
        self.src = src
        self.prefer_tcp = prefer_tcp
        self._running = False

    def start(self, timeout=1.0):
        # Simulate a quick failed start for network/RTSP sources
        return False

    def read(self):
        return False, None

    def stop(self):
        self._running = False


@pytest.fixture(autouse=True)
def patch_video_stream(monkeypatch):
    import tyvyx.video_stream as vsmod

    monkeypatch.setattr(vsmod, 'OpenCVVideoStream', _FakeVideoStream)
    yield
