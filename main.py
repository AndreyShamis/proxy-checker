#!/usr/bin/env python3
import os
import re
import signal
import sys
import threading
import time
import logging
import ssl
import datetime
import subprocess
from datetime import datetime, timedelta
import urllib.request
from queue import Queue, Empty
try:
    import typing
except:
    pass
try:
    import httplib
except:
    pass


# Configuration
URL_TO_CHECK = "https://www.youtube.com/watch?v=DY30Kf19Puk"  # type: str
USE_LOCK = False  # if True - only one checker will work
DELAY_BETWEEN_RUNS_SEC = 3
CHECK_YOUTUBE_COUNTRY = True  # type: bool
THREADS = 50  # number of checker at same time

input_file = 'proxylist.txt'
PRINT_BAD = False  # for debug
PRINT_START = True  # for debug
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
    delay_sem = threading.Semaphore()
    connect_sem = threading.Semaphore()
    inter_sem = threading.Semaphore()
    counter = 0
    good_found = 0
    good_found_printed = 0
    total_urls = 0
    threads = []  # type: typing.List[threading.Thread]

    def __init__(self, the_queue):
        # type: (Queue) -> None
        threading.Thread.__init__(self)
        self.queue = the_queue  # type: Queue
        self.id = 0  # type: int
        self.youtube_dl_proc = None
        self.youtube_verify_time = 0
        self.last_traffic_line = ''  # type: str
        self.speed = ''  # type: str
        self.ETA = ''  # type: str

    @staticmethod
    def enqueue_output(out, my_queue):
        for _line in iter(out.readline, b''):
            my_queue.put(_line)
        out.close()

    def start_youtube_dl(self, proxy_info, loop_timeout=180):
        # type: (str, int) -> bool
        ret = False
        start_time = time.time()
        expired_time = False
        ON_POSIX = 'posix' in sys.builtin_module_names
        _flags = ' --no-check-certificate --prefer-insecure '
        _cmd = "youtube-dl --proxy=\"{}\" {} -F {}".format(proxy_info, _flags, URL_TO_CHECK)
        process = subprocess.Popen(_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                close_fds=ON_POSIX, preexec_fn=os.setsid)
        q_stdout_yt = Queue()
        q_error_em = Queue()

        t_stdout_yt= threading.Thread(target=ThreadUrl.enqueue_output, args=(process.stdout, q_stdout_yt))
        t_error_em = threading.Thread(target=ThreadUrl.enqueue_output, args=(process.stderr, q_error_em))
        ThreadUrl.threads.append(t_stdout_yt)
        ThreadUrl.threads.append(t_error_em)
        t_stdout_yt.daemon = True  # thread dies with the program
        t_error_em.daemon = True  # thread dies with the program
        t_stdout_yt.start()
        t_error_em.start()
        time.sleep(0.5)
        full_stdout = ''
        run_time = time.time() - start_time
        cont_this_loop = True

        # read line without blocking
        while t_stdout_yt.is_alive() and CONTINUE_LOOP and cont_this_loop:
            try:
                run_time = time.time() - start_time
                try:
                    line = q_stdout_yt.get_nowait()
                except Empty:
                    pass
                else:
                    try:
                        if isinstance(line, bytes):
                            line = line.decode('utf8')
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
                        line = line.decode('utf8')
                    except:
                        pass
                    if line != '':
                        pass
                        # logging.warning('STDERR: {} - {}'.format(proxy_info, line.rstrip()))
                if run_time > loop_timeout:
                    cont_this_loop = False
            except Exception as ex:
                logging.exception(ex)

        if not cont_this_loop:
            # send signal to YT process
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            # err_msg = '{} - Aborted! Timeout expired after {} sec'.format(proxy_info, loop_timeout)
            # logger.error(err_msg)
            try:
                try:  # kill threads
                    t_stdout_yt.join(0)
                except Exception as ex:
                    logger.error('cannot kill the thread: {}, {}'.format(t_stdout_yt, ex))
                try:
                    t_error_em.join(0)
                except Exception as ex:
                    logger.error('cannot kill the thread: {}, {}'.format(t_error_em, ex))
                # kill process
                time.sleep(1)  # sleep 1 sec, after the signal has been sent
                process.kill()
                process.returncode = 1
            except Exception as ex:
                logger.error('cannot kill the process: {}, {}'.format(process, ex))
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except Exception as ex:
                logging.exception(ex)
        end_time = time.time()
        if 'fps' in full_stdout and 'video only' in full_stdout:
            ret = True
        self.youtube_verify_time = end_time - start_time
        # if ret:
        #     logging.info('{} - YOUTUBE RES IS {} - Finish in {}'.format(proxy_info, ret, self.youtube_verify_time))

        return ret

    def find_avg_speed(self, input_text):
        # type: (str) -> float
        input_text = input_text.replace('\r', '\n')
        regex = re.compile('at\s*(\d+\.?\d*)(\w+\/s)\s*ETA\s*([\d|\:]+)', re.MULTILINE)
        # txt = """
        # [download]   0.0% of 1.03GiB at 10.52KiB/s ETA 28:23:15
        # [download]   0.0% of 1.03GiB at 31.48KiB/s ETA 09:29:05
        # [download]   5.4% of 1.03GiB at 557.43KiB/s ETA 30:24
        # [download]   5.5% of 1.03GiB at 567.27KiB/s ETA 29:51
        # [download]   5.5% of 1.03GiB at 576.27KiB/s ETA 29:22
        # [download]   9.3% of 1.03GiB at  1.06MiB/s ETA 15:02
        # [download]   5.5% of 1.03GiB at 579.76KiB/s ETA 29:11"""
        list_of_lines = regex.findall(input_text)
        total_lines = 0
        sum_speed = 0.0
        for speed_digit, speed_word, eta in list_of_lines:
            speed_digit = float(speed_digit)
            total_lines += 1
            if speed_word == 'MiB/s':
                speed_digit = speed_digit * 1000
                speed_word = 'KiB/s'
            sum_speed += speed_digit
            # logging.info('Speed {} {} for {}'.format(speed_digit, speed_word, eta))
        self.speed = round(sum_speed / max(total_lines, 0.001), 2)
        #logging.info('Total lines {}, AVG {}'.format(total_lines, self.speed))
        return self.speed

    def download_youtube_dl(self, proxy_info, loop_timeout=200):
        # type: (str, int) -> bool
        ret = False
        start_time = time.time()
        ON_POSIX = 'posix' in sys.builtin_module_names
        _flags = ' --no-check-certificate --prefer-insecure --no-cache-dir --no-continue '
        _cmd = "youtube-dl --proxy=\"{}\" {} {}".format(proxy_info, _flags, URL_TO_CHECK)
        this_process = subprocess.Popen(_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        stdin=subprocess.PIPE, close_fds=ON_POSIX, preexec_fn=os.setsid)
        q_stdout_yt = Queue()
        q_error_em = Queue()

        t_stdout_yt = threading.Thread(target=ThreadUrl.enqueue_output, args=(this_process.stdout, q_stdout_yt))
        t_error_em = threading.Thread(target=ThreadUrl.enqueue_output, args=(this_process.stderr, q_error_em))
        ThreadUrl.threads.append(t_stdout_yt)
        ThreadUrl.threads.append(t_error_em)
        t_stdout_yt.daemon = True  # thread dies with the program
        t_error_em.daemon = True  # thread dies with the program
        t_stdout_yt.start()
        t_error_em.start()
        time.sleep(1.5)
        cont_this_loop = True

        while t_stdout_yt.is_alive() and CONTINUE_LOOP and cont_this_loop:
            try:
                run_time = time.time() - start_time
                try:
                    line = q_stdout_yt.get_nowait()
                except Empty:
                    pass
                else:
                    f_print = True
                    try:
                        if isinstance(line, bytes):
                            line = line.decode('utf8')
                        line = line.encode('utf8')
                    except:
                        pass

                    if line != '':
                        line = line.rstrip()
                        if 'Downloading webpage' in line:
                            loop_timeout = loop_timeout * 2
                            f_print = False
                        if 'Downloading video info webpage' in line:
                            loop_timeout = loop_timeout * 2
                            f_print = False
                        if 'Resuming download at byte ' in line:
                            loop_timeout = loop_timeout * 2
                        if ' Destination:' in line:
                            loop_timeout = loop_timeout * 2
                            f_print = False
                        if '%' in line:
                            try:
                                if "\r" in line:
                                    self.find_avg_speed(line)
                                    _lines = line.split("\r")
                                    logging.info('DL: File started download for [{}]'.format(proxy_info))
                                    for _l in _lines:
                                        # logging.info('DL: --- {} [{}]'.format(proxy_info, _l))
                                        _tmp_str = '{}'.format(_l)
                                        if len(_tmp_str) > 5:
                                            self.last_traffic_line = _tmp_str.replace('[download]', '').strip()
                                    f_print = False
                                else:
                                    logging.info('DL: {} File started download for [{}]'.format(proxy_info, line))
                                ret = True
                            except Exception as ex:
                                logging.exception(ex)
                        if f_print:
                            logging.info('DL - {}: RT {} STDOUT: {}'.format(proxy_info, round(run_time, 1), line))
                try:
                    line = q_error_em.get_nowait()
                except Empty:
                    pass
                else:
                    try:
                        if isinstance(line, bytes):
                            line = line.decode('utf8')
                        line = line.encode('utf8')
                    except:
                        pass
                    # got line
                    if line != '':
                        if 'unable to download video data' in line:
                            loop_timeout = loop_timeout / 2
                        if 'Unable to download webpage' in line:
                            loop_timeout = loop_timeout / 1.2
                        if 'for merge and will be merged into mkv' in line:
                            continue
                        logging.warning('DL:STDERR: {} - {}'.format(proxy_info, line.rstrip()))

                if run_time > loop_timeout:
                    cont_this_loop = False
            except Exception as ex:
                logging.exception(ex)
        if not CONTINUE_LOOP:
            logging.warning('DL killed for {}'.format(proxy_info))
        if not cont_this_loop:
            # send signal to YT process
            os.killpg(os.getpgid(this_process.pid), signal.SIGTERM)
            err_msg = 'DL: {} - Aborted! Timeout expired after {} sec'.format(proxy_info, loop_timeout)
            logger.error(err_msg)
            try:
                try:
                    t_stdout_yt.join(0)
                except Exception as ex:
                    logger.error('DL: cannot kill the thread: {}, {}'.format(t_stdout_yt, ex))
                try:
                    t_error_em.join(0)
                except Exception as ex:
                    logger.error('DL: cannot kill the thread: {}, {}'.format(t_error_em, ex))
                # kill process
                time.sleep(1)  # sleep 1 sec, after the signal has been sent
                this_process.kill()
                this_process.returncode = 1
            except Exception as ex:
                logger.error('DL: cannot kill the process: {}, {}'.format(this_process, ex))
        else:
            try:
                os.killpg(os.getpgid(this_process.pid), signal.SIGTERM)
            except Exception as ex:
                logging.exception(ex)
        end_time = time.time()

        if ret:
            logging.info('DL: {} - YOUTUBE RES IS {} - Finish in {}'.format(proxy_info, ret, end_time - start_time))

        return ret

    def run(self):
        while CONTINUE_LOOP:
            proxy_info = clean_proxy_info = first_input = ''
            try:
                ThreadUrl.inter_sem.acquire()
                ThreadUrl.counter += 1
                self.id = ThreadUrl.counter
                time.sleep(0.2)
            except:
                pass
            finally:
                ThreadUrl.inter_sem.release()

            try:
                first_input = self.queue.get().strip()  # type: str
                clean_proxy_info = first_input.replace('\xc2\xa0', ' ').strip()  # type: str
                clean_proxy_info = clean_proxy_info.replace('\xa0', ' ').strip()  # type: str
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
                        logging.info('Start {}/{}/ In progress {}/ Good {} - {}'.format(
                            self.id, ThreadUrl.total_urls, queue.unfinished_tasks,
                            ThreadUrl.good_found, proxy_info))
                        ThreadUrl.print_good(False)
                    proxy_handler = urllib.request.ProxyHandler({'https': proxy_info})
                    opener = urllib.request.build_opener(proxy_handler)
                    opener.addheaders = [('User-agent', USER_AGENT)]
                    urllib.request.install_opener(opener)
                    req = urllib.request.Request(URL_TO_CHECK)
                    if USE_LOCK:
                        ThreadUrl.connect_sem.acquire()
                    try:
                        start_t = time.time()
                        # sock = urllib.request.urlopen(req, timeout=(20 + queue.unfinished_tasks))
                        sock = opener.open(req, timeout=(20 + queue.unfinished_tasks))
                        encoding = sock.headers.get_content_charset('utf-8')
                        rs = sock.read(100000)
                        end_t = time.time()
                        rs = rs.decode(encoding)
                    except Exception as ex:
                        raise
                    finally:
                        if USE_LOCK:
                            ThreadUrl.connect_sem.release()

                    try:
                        ThreadUrl.delay_sem.acquire()
                        if DELAY_BETWEEN_RUNS_SEC > 0 and ThreadUrl.counter > 1:
                            time.sleep(DELAY_BETWEEN_RUNS_SEC)
                    except Exception as ex:
                        logging.exception(ex)
                    finally:
                        try:
                            ThreadUrl.delay_sem.release()
                        except Exception as ex:
                            logging.exception(ex)

                    #  and '<title>YouTube</title>' in rs
                    t_r = round(end_t-start_t, 3)
                    sock_msg_ok = sock.msg == 'OK'  # type: bool
                    if sock_msg_ok and sock.code == 200 and '<title>' in rs \
                            and (CHECK_YOUTUBE_COUNTRY and 'UNPLAYABLE' not in rs):
                        _test_yt = self.start_youtube_dl(proxy_info)
                        if not _test_yt:
                            time.sleep(5 + queue.unfinished_tasks)
                            _test_yt = self.start_youtube_dl(proxy_info)
                        if _test_yt:
                            _t = (end_t-start_t) + self.youtube_verify_time
                            logging.info('{:>3} Check youtube [ {:>21} ] ( in {} )'.format(
                                self.id, proxy_info, timedelta(seconds=_t)))
                            _dr = self.download_youtube_dl(proxy_info)
                            if not _dr:
                                time.sleep(5 + queue.unfinished_tasks)
                                _dr = self.download_youtube_dl(proxy_info)
                            try:
                                ThreadUrl.delay_sem.acquire()
                                if _dr:
                                    output.append((self.id, t_r, proxy_info, _dr, self.speed, self.last_traffic_line))
                                    ThreadUrl.good_found += 1
                            except:
                                pass
                            finally:
                                ThreadUrl.delay_sem.release()
                        else:
                            if PRINT_BAD:
                                logging.error('start_youtube_dl returned False for {}'.format(proxy_info))
                    else:
                        if PRINT_BAD:
                            if not sock_msg or sock.code != 200:
                                logging.error('BAD socket')
                            if CHECK_YOUTUBE_COUNTRY and 'UNPLAYABLE' in rs:
                                logging.error('UNPLAYABLE FOUND')
                else:
                    logging.debug('Skip connection to [{}]'.format(first_input))
            except (urllib.request.URLError, ssl.SSLError) as ex: # , httplib.BadStatusLine,
                if PRINT_BAD:
                    logging.error('Cannot connect to {} - {}'.format(clean_proxy_info, ex.message))
            except Exception as ex:
                logging.error("------------------")
                logging.exception(ex)
                logging.error("------------------")
                # output.append(('x', proxy_info))
            self.queue.task_done()  # signals to queue job is done

    @staticmethod
    def print_good(force_print=False):
        _p = '{:5} - {:>6} - {:>25} - {:>10} - {:>10} - {}'
        if ThreadUrl.good_found_printed != ThreadUrl.good_found:
            ThreadUrl.good_found_printed = ThreadUrl.good_found
            force_print = True
        if force_print:
            logging.debug('')
            logging.info(_p.format('ID', 'Time', 'PROXY HOST', 'PASS yt-dl', 'Speed', 'Speed Line'))
            for id, first_time, host, download_res, speed, for_th in output:
                logging.info(_p.format(id, first_time, host, download_res, speed, for_th))
            logging.debug('')


def signal_handler(sig, frame):
    global CONTINUE_LOOP
    CONTINUE_LOOP = False
    print('INTERRUPT: Exiting from MAIN - SIGNAL RECEIVED {}'.format(sig))
    time.sleep(0.5)
    for _t in ThreadUrl.threads:
        try:
            _t.join(0)
        except Exception as ex:
            logging.exception(ex)
    sys.exit(27)


def main():
    # spawn a pool of threads, and pass them queue instance
    for i in range(THREADS):
        t = ThreadUrl(queue)
        t.setDaemon(True)
        t.start()
    hosts = [host_tmp.strip() for host_tmp in open(input_file).readlines()]
    # populate queue with data
    ThreadUrl.total_urls = len(hosts)
    counter = 0
    added_hosts = []
    for host_tmp in hosts:
        if host_tmp not in added_hosts:
            added_hosts.append(host_tmp)
            counter += 1
            queue.put(host_tmp)
            if queue.unfinished_tasks > 1:
                time.sleep(min(30, int(queue.unfinished_tasks / 2)))

    logging.info('Added {} hosts to check'.format(counter))
    # wait on the queue until everything has been processed
    queue.join()


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGABRT, signal_handler)
signal.signal(signal.SIGPIPE, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)
start = time.time()
main()
ThreadUrl.print_good(True)

logging.warning("Elapsed Time: {}".format(round(time.time() - start, 2)))
