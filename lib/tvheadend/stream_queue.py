import logging
import time
from threading import Thread
from queue import Queue, Empty


class StreamQueue:
    def __init__(self, stream, bytes_per_read, proc):
        """
        stream: the stream to read from.
                Usually a process' stdout or stderr.
        """

        max_queue_size = 10

        self._bytes_per_read = bytes_per_read
        self._s = stream
        self._q = Queue(max_queue_size)
        self._proc = proc
        self.logger = logging.getLogger(__name__)

        def _populate_queue(_stream, s_queue):
            """
            Collect lines from 'stream' and put them in 'queue'.
            """
            self.logger.debug('Queue Size={}, Process PID={}'.format(max_queue_size, self._proc.pid))
            while True:
                video_data = _stream.read(self._bytes_per_read)
                self.logger.debug('Read {} bytes'.format(len(video_data)))
                if video_data:
                    self.logger.debug('Adding to queue. Queue Length={}'.format(s_queue.qsize()))
                    s_queue.put(video_data)
                    # set a delay to allow other threads to run and pick up the buffer
                    time.sleep(0.1)
                else:
                    self.logger.debug('Stream ended for this process, exiting queue thread')
                    # TBD need to empty queue before thread goes away
                    break

        self._t = Thread(target=_populate_queue,
            args=(self._s, self._q))
        self._t.daemon = True
        self._t.start()  # start collecting blocks from the stream

    def read(self, timeout=None):
        try:
            self.logger.debug('Pulling from queue. Queue Length={}'.format(self._q.qsize()))
            video_data = self._q.get(block=timeout is None,
                timeout=timeout)
            return video_data
        except Empty:
            return None

    def set_bytes_per_read(self, bytes_per_read):
        self.logger.debug('{} changing read buffer to {}'.format(self._proc.pid, bytes_per_read))
        self._bytes_per_read = bytes_per_read


class UnexpectedEndOfStream(Exception):
    pass
