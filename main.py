#!/usr/bin/env python
import Queue
import os
import signal
import sys
import threading
import urllib2
import time
import logging
import httplib
import datetime
from threading import Semaphore


input_file = 'proxylist.txt'
threads = 10
queue = Queue.Queue()
output = []
CONTINUE_LOOP = True
PRINT_BAD = False
PRINT_START = False
USE_LOCK = False

run_prefix = datetime.datetime.now().strftime("%y%m%d_%H%M")
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

# create error file handler and set level to error
handler = logging.FileHandler(os.path.join("./", "error_{}.log".format(run_prefix)), "w", encoding=None, delay="true")
handler.setLevel(logging.ERROR)
formatter = logging.Formatter(log_frmt, datefmt=datefmt)
handler.setFormatter(formatter)
logger.addHandler(handler)

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
    counter = 0

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue

    def run(self):
        while CONTINUE_LOOP:
            #grabs host from queue
            proxy_info = clean_proxy_info = first_input = ''
            ThreadUrl.counter += 1
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
                    opener.addheaders = [('User-agent','Mozilla/5.0')]
                    urllib2.install_opener(opener)
                    req = urllib2.Request("https://www.youtube.com/watch?v=O_Nzv-PNMmE")
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
                    if sock.msg == 'OK' and sock.code == 200 and '<title>' in rs and 'UNPLAYABLE' not in rs:
                        logging.info('{:>3} Success [ {:>21} ] ( in {} )'.format(ThreadUrl.counter,
                            proxy_info, datetime.timedelta(seconds=t_r)))
                        output.append((t_r, proxy_info))
                    else:
                        if PRINT_BAD:
                            if sock.msg != 'OK' or sock.code != 200:
                                logging.error('BAD socket')
                            if 'UNPLAYABLE' in rs:
                                logging.error('UNPLAYABLE FOUND')
                        #raise Exception("{} Not Google".format(clean_proxy_info))
                else:
                    logging.debug('Skip connection to [{}]'.format(first_input))
            except (urllib2.URLError, httplib.BadStatusLine) as ex:
                if PRINT_BAD:
                    logging.error('Cannot connect to {} - {}'.format(clean_proxy_info, ex.message))
            except Exception as ex:
                logging.error("------------------")
                logging.exception(ex)
                logging.error("------------------")
                # output.append(('x', proxy_info))
            #signals to queue job is done
            self.queue.task_done()


def signal_handler(sig, frame):
    global CONTINUE_LOOP
    CONTINUE_LOOP = False
    print('INTERRUPT: Exiting from MAIN {}'.format(sig))
    sys.exit(27)


def main():
    #spawn a pool of threads, and pass them queue instance
    for i in range(5):
        t = ThreadUrl(queue)
        t.setDaemon(True)
        t.start()
    hosts = [host.strip() for host in open(input_file).readlines()]
    #populate queue with data
    for host in hosts:
        queue.put(host)
    #wait on the queue until everything has been processed
    queue.join()


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGABRT, signal_handler)
signal.signal(signal.SIGPIPE, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)
start = time.time()
main()
for proxy, host in output:
    logging.info ('{:>6} - {:>22}'.format(proxy, host))

logging.warning("Elapsed Time: {}".format(time.time() - start))
