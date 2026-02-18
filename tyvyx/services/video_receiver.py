import queue
import socket
import threading
import time

from tyvyx.utils.dropping_queue import DroppingQueue
from tyvyx.models.video_frame import VideoFrame


class VideoReceiverService:
    """
    Creates and manages a protocol adapter, destroying and recreating
    it from scratch if the connection is lost.
    """

    def __init__(
        self,
        protocol_adapter_class,
        protocol_adapter_args,
        frame_queue=None,
        max_queue_size=2,
    ):
        self.protocol_adapter_class = protocol_adapter_class
        self.protocol_adapter_args = protocol_adapter_args
        self.frame_queue = frame_queue or DroppingQueue(maxsize=max_queue_size)
        self.protocol = None

        self._running = threading.Event()
        self._receiver_thread = None

    def start(self) -> None:
        if self._receiver_thread and self._receiver_thread.is_alive():
            return

        self._running.set()
        self._receiver_thread = threading.Thread(
            target=self._receiver_loop, name="VideoReceiver", daemon=True
        )
        self._receiver_thread.start()

    def stop(self) -> None:
        self._running.clear()
        if self.protocol:
            self.protocol.stop()

        if self._receiver_thread and self._receiver_thread.is_alive():
            self._receiver_thread.join(timeout=2.0)

    def get_frame_queue(self) -> queue.Queue:
        return self.frame_queue

    def _receiver_loop(self) -> None:
        while self._running.is_set():
            try:
                self.protocol = self.protocol_adapter_class(
                    **self.protocol_adapter_args
                )
                self.protocol.start()

                while self._running.is_set() and self.protocol.is_running():
                    try:
                        frame = self.protocol.get_frame(timeout=1.0)
                        if frame:
                            self.frame_queue.put(frame)
                    except queue.Empty:
                        continue
                    except Exception as e:
                        print(f"[VideoReceiverService] Error processing frame: {e}")
                        break

            except socket.error as e:
                print(f"[VideoReceiverService] Socket error: {e}. Reconnecting...")
            except Exception as e:
                print(f"[VideoReceiverService] Unexpected error: {e}")
            finally:
                if self.protocol:
                    self.protocol.stop()
                    self.protocol = None

            if self._running.is_set():
                print("[VideoReceiverService] Waiting 2s before reconnecting...")
                time.sleep(2)

        print("[VideoReceiverService] Receiver loop stopped.")
