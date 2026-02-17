import queue


class DroppingQueue(queue.Queue):
    """
    A queue that drops the oldest item when it is full.
    """

    def put(self, item, block=True, timeout=None):
        with self.mutex:
            if self.maxsize > 0 and self._qsize() >= self.maxsize:
                self._get()
                if self.unfinished_tasks > 0:
                    self.unfinished_tasks -= 1

            self._put(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()

    def put_nowait(self, item):
        self.put(item, block=False)
