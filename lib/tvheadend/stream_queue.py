import logging
from threading import Thread
from queue import Queue, Empty


class StreamQueue:
    def __init__(self, stream, bytes_per_read, proc):
        '''
        stream: the stream to read from.
                Usually a process' stdout or stderr.
        '''

        MAX_QUEUE_SIZE = 10

        self._bytes_per_read = bytes_per_read
        self._s = stream
        self._q = Queue(MAX_QUEUE_SIZE)
        self._proc = proc

        def _populateQueue(stream, s_queue):
            '''
            Collect lines from 'stream' and put them in 'queue'.
            '''
            logging.debug('Queue Size={}, Process PID={}'.format(MAX_QUEUE_SIZE, self._proc.pid))
            while True:
                videoData = stream.read(self._bytes_per_read)
                logging.debug('Read {} bytes'.format(len(videoData)))
                if videoData:
                    logging.debug('Adding to queue. Queue Length={}'.format(s_queue.qsize()))
                    s_queue.put(videoData)
                    # set a delay to allow other threads to run and pick up the buffer
                    time.sleep(0.1)
                else:
                    logging.debug('Stream ended for this process, exiting queue thread')
                    # TBD need to empty queue before thread goes away
                    break

        self._t = Thread(target = _populateQueue,
                args = (self._s, self._q))
        self._t.daemon = True
        self._t.start() #start collecting blocks from the stream

    def read(self, timeout = None):
        try:
            logging.debug('Pulling from queue. Queue Length={}'.format(self._q.qsize()))
            videoData = self._q.get(block = timeout is None, \
                    timeout = timeout)
            return videoData
        except Empty:
            return None

    def set_bytes_per_read(self, bytes_per_read):
        logging.debug('{} changing read buffer to {}'.format(self._proc.pid, bytes_per_read))
        self._bytes_per_read = bytes_per_read


class UnexpectedEndOfStream(Exception): pass
