from typing import Dict, Optional

from tyvyx.models.video_frame import VideoFrame
from tyvyx.models.base_video_model import BaseVideoModel


class S2xVideoModel(BaseVideoModel):
    """
    Reassembles sliced JPEG frames used by S2x-style drones.

    Ignores the unreliable "is-last-slice" flag.
    Finishes a frame when the frame-id rolls over.
    """

    SOI_MARKER = b"\xFF\xD8"
    EOI_MARKER = b"\xFF\xD9"

    def __init__(self) -> None:
        self._cur_fid: Optional[int] = None
        self._frags: Dict[int, bytes] = {}

    def ingest_chunk(
        self,
        *,
        stream_id: int | None = None,
        chunk_id: int | None = None,
        payload: bytes,
    ) -> Optional[VideoFrame]:
        if stream_id is None or chunk_id is None:
            return None

        completed: Optional[VideoFrame] = None
        if self._cur_fid is None:
            self._cur_fid = stream_id
        elif stream_id != self._cur_fid:
            completed = self._assemble_current()
            self._reset(stream_id)

        self._frags.setdefault(chunk_id, payload)
        return completed

    def _reset(self, new_fid: Optional[int]) -> None:
        self._cur_fid = new_fid
        self._frags.clear()

    def _assemble_current(self) -> Optional[VideoFrame]:
        if not self._frags:
            return None

        keys = sorted(self._frags)
        complete = len(keys) == keys[-1] - keys[0] + 1
        if not complete:
            return None

        data = b"".join(self._frags[k] for k in keys)

        start = data.find(self.SOI_MARKER)
        end = data.rfind(self.EOI_MARKER)
        if start < 0 or end < 0 or end <= start:
            return None

        jpeg = data[start : end + len(self.EOI_MARKER)]
        frame = VideoFrame(self._cur_fid, jpeg, "jpeg")
        self._reset(None)
        return frame
