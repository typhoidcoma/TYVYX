from abc import ABC, abstractmethod
from typing import Optional

from tyvyx.models.video_frame import VideoFrame


class BaseVideoModel(ABC):
    """
    Stateless interface that turns *chunks* (whatever the protocol
    thinks a chunk is: a JPEG slice, a whole JPEG, a H.264 NALU ...)
    into complete VideoFrame objects.
    """

    @abstractmethod
    def ingest_chunk(
        self,
        *,
        stream_id: int | None = None,
        chunk_id: int | None = None,
        payload: bytes,
    ) -> Optional[VideoFrame]:
        """
        Feed one chunk into the model.

        Returns VideoFrame when a frame is complete, None if more data is required.
        """
        raise NotImplementedError
