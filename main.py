#!/usr/bin/env python
import os
import signal
import sys
import threading
import urllib2
import time
import logging
import httplib
import ssl
import datetime
import subprocess
from datetime import datetime, timedelta
try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty  # python 2.x


# Configuration
URL_TO_CHECK = "https://www.youtube.com/watch?v=O_Nzv-PNMmE"  # type: str
USE_LOCK = False  # if True - only one checker will work
CHECK_YOUTUBE_COUNTRY = True  # type: bool
THREADS = 50  # number of checker at same time

input_file = 'proxylist.txt'
PRINT_BAD = False  # for debug
PRINT_START = False  # for debug
ADD_ERROR_LOG = False
ADD_ALL_LOG = False
queue = Queue()
output = []
CONTINUE_LOOP = True  # for internal use
USER_AGENT= 'Mozilla/5.0'  # type: str

run_prefix = datetime.now().strftime("%y%m%d_%H%M")
log_frmt = '%(asctime)s | %(name)-10s | %(levelname)-9s | %(message)s'
datefmt = '%Y/%m/%d %H:%M:%S'

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# create console handler and set level to info
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter(log_frmt, datefmt=datefmt)
handler.setFormatter(formatter)
logger.addHandler(handler)

if ADD_ERROR_LOG:
    # create error file handler and set level to error
    handler = logging.FileHandler(os.path.join("./", "error_{}.log".format(run_prefix)), "w", encoding=None,
                                  delay="true")
    handler.setLevel(logging.ERROR)
    formatter = logging.Formatter(log_frmt, datefmt=datefmt)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

if ADD_ALL_LOG:
    # create debug file handler and set level to debug
    handler = logging.FileHandler(os.path.join("./", "all_{}.log".format(run_prefix)), "w")
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(log_frmt, datefmt=datefmt)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

loaded = False
logging.info("Starting execution : ID {}".format(run_prefix))


class ThreadUrl(threading.Thread):
    """Threaded Url Grab"""
    connect_sem = threading.Semaphore()
    inter_sem = threading.Semaphore()
    counter = 0

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.id = 0
        self.youtube_dl_proc = None

    def start_youtube_dl(self, proxy_info):
        ret = False
        start_time = datetime.now()
        expired_time = False
        ON_POSIX = 'posix' in sys.builtin_module_names
        _cmd = "youtube-dl --proxy=\"{}\" --no-check-certificate " \
               "--prefer-insecure -F https://www.youtube.com/watch?v=VXOjcxhevlM".format(proxy_info)
        self.youtube_dl_proc = subprocess.Popen(_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                close_fds=ON_POSIX, preexec_fn=os.setsid)
        q_stdout_youtube = Queue()
        q_error_em = Queue()

        def enqueue_output(out, queue):
            for line in iter(out.readline, b''):
                queue.put(line)
            out.close()

        t_stdout_youtube= threading.Thread(target=enqueue_output, args=(self.youtube_dl_proc.stdout, q_stdout_youtube))
        t_error_em = threading.Thread(target=enqueue_output, args=(self.youtube_dl_proc.stderr, q_error_em))
        t_stdout_youtube.daemon = True  # thread dies with the program
        t_error_em.daemon = True  # thread dies with the program
        t_stdout_youtube.start()
        t_error_em.start()
        time.sleep(0.5)
        full_stdout = ''
        # read line without blocking
        while t_stdout_youtube.is_alive() and CONTINUE_LOOP:
            try:
                line = q_stdout_youtube.get_nowait()
            except Empty:
                pass
            else:
                try:
                    if isinstance(line, bytes):
                        line = line.decode('utf8')
                except:
                    pass
                # got line
                if line != '':
                    full_stdout += line.rstrip()
                    # print('STDOUT: {} - {}'.format(proxy_info, line.rstrip()))
            try:
                line = q_error_em.get_nowait()
            except Empty:
                pass
            else:
                try:
                    if isinstance(line, bytes):
                        line = line.decode('utf8')
                except:
                    pass
                # got line
                if line != '':
                    try:
                        if isinstance(line, bytes):
                            line = line.decode('utf8')
                    except:
                        pass
                    print('STDERR: {} - {}'.format(proxy_info, line.rstrip()))
        end_time = datetime.now()
        if 'fps' in full_stdout and 'video only' in full_stdout:
            ret = True
        logging.info('{} - YOUTUBE RES IS {} - Finish in {}'.format(proxy_info, ret, end_time - start_time))

        return ret

    def run(self):
        while CONTINUE_LOOP:
            proxy_info = clean_proxy_info = first_input = ''
            try:
                ThreadUrl.inter_sem.acquire()
                ThreadUrl.counter += 1
                self.id = ThreadUrl.counter
            except:
                pass
            finally:
                ThreadUrl.inter_sem.release()
            try:
                first_input = self.queue.get().strip()  # type: str
                clean_proxy_info = first_input.replace('\xc2\xa0', ' ').strip()  # type: str
                if ' ' in clean_proxy_info:
                    proxy_info = clean_proxy_info.split(' ')[1]
                else:
                    proxy_info = clean_proxy_info
            except Exception as ex:
                logging.error('Error in {}'.format(first_input))
                logging.exception(ex)
            try:
                if len(proxy_info):
                    if PRINT_START:
                        logging.info('Start {}'.format(proxy_info))
                    proxy_handler = urllib2.ProxyHandler({'https': proxy_info})
                    opener = urllib2.build_opener(proxy_handler)
                    opener.addheaders = [('User-agent', USER_AGENT)]
                    urllib2.install_opener(opener)
                    req = urllib2.Request(URL_TO_CHECK)
                    if USE_LOCK:
                        ThreadUrl.connect_sem.acquire()
                    try:
                        start_t = time.time()
                        sock = urllib2.urlopen(req, timeout=5)
                        rs = sock.read(100000)
                        end_t = time.time()
                    except Exception as ex:
                        raise
                    finally:
                        if USE_LOCK:
                            ThreadUrl.connect_sem.release()
                    #  and '<title>YouTube</title>' in rs
                    t_r = round(end_t-start_t, 3)
                    if sock.msg == 'OK' and sock.code == 200 and '<title>' in rs \
                            and (CHECK_YOUTUBE_COUNTRY and 'UNPLAYABLE' not in rs):
                        logging.info('{:>3} Success [ {:>21} ] ( in {} )'.format(
                            self.id, proxy_info, timedelta(seconds=t_r)))

                        if self.start_youtube_dl(proxy_info):
                            output.append((t_r, proxy_info))
                        else:
                            if PRINT_BAD:
                                logging.error('start_youtube_dl returned False for {}'.format(proxy_info))
                    else:
                        if PRINT_BAD:
                            if sock.msg != 'OK' or sock.code != 200:
                                logging.error('BAD socket')
                            if CHECK_YOUTUBE_COUNTRY and 'UNPLAYABLE' in rs:
                                logging.error('UNPLAYABLE FOUND')
                else:
                    logging.debug('Skip connection to [{}]'.format(first_input))
            except (urllib2.URLError, httplib.BadStatusLine, ssl.SSLError) as ex:
                if PRINT_BAD:
                    logging.error('Cannot connect to {} - {}'.format(clean_proxy_info, ex.message))
            except Exception as ex:
                logging.error("------------------")
                logging.exception(ex)
                logging.error("------------------")
                # output.append(('x', proxy_info))
            self.queue.task_done()  # signals to queue job is done


def signal_handler(sig, frame):
    global CONTINUE_LOOP
    CONTINUE_LOOP = False
    print('INTERRUPT: Exiting from MAIN {}'.format(sig))
    time.sleep(0.5)
    sys.exit(27)


def main():
    # spawn a pool of threads, and pass them queue instance
    for i in range(THREADS):
        t = ThreadUrl(queue)
        t.setDaemon(True)
        t.start()
    hosts = [host_tmp.strip() for host_tmp in open(input_file).readlines()]
    # populate queue with data
    for host_tmp in hosts:
        queue.put(host_tmp)
    # wait on the queue until everything has been processed
    queue.join()


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGABRT, signal_handler)
signal.signal(signal.SIGPIPE, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)
start = time.time()
main()
logging.debug('')
for proxy, host in output:
    logging.info('{:>6} - {:>22}'.format(proxy, host))
logging.debug('')
logging.warning("Elapsed Time: {}".format(time.time() - start))
