#!/usr/bin/env python3
import os
import re
import signal
import sys
import threading
import time
import logging
import ssl
import argparse
import datetime
import subprocess
from datetime import datetime, timedelta
import urllib.request
import socket
from http.client import BadStatusLine, RemoteDisconnected
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
queue = Queue()  # type: Queue
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


class StartYoutubeDlException(Exception):
    pass


class DownloadYoutubeDlException(Exception):
    pass


class ThreadUrl(threading.Thread):
    """Threaded Url Grab"""
    delay_sem = threading.Semaphore()
    connect_sem = threading.Semaphore()
    inter_sem = threading.Semaphore()
    counter = 0
    good_found = 0
    good_found_printed = 0
    total_urls = 0
    url_error = 0
    total_errors = 0
    threads = []  # type: typing.List[threading.Thread]
    started_threads = []    # type: typing.List[ThreadUrl]

    def __init__(self, the_queue, url):
        # type: (Queue, str) -> None
        threading.Thread.__init__(self)
        self.queue = the_queue  # type: Queue
        self.id = 0  # type: int
        self.youtube_dl_proc = None
        self.youtube_verify_time = 0
        self.last_traffic_line = ''  # type: str
        self.last_real_download_traffic_line = ''  # type: str
        self.speed = ''  # type: str
        self.ETA = ''  # type: str
        self.__download_url = ''  # type: str
        self.isGood = False     # type: bool
        self.proxy_info = ''   # type: str
        self.download_url = url  # type: str

    @staticmethod
    def add_good_to_file(proxy_info, file_name):
        # type: (str, str) -> bool
        try:
            with open(file_name, 'a') as f:
                f.write(proxy_info + '\n')
        except Exception as ex:
            logging.exception(ex)
            return False
        return True

    def get_download_url(self):
        # type () -> str
        return self.__download_url

    def set_download_url(self, new_url):
        # type (str) -> None
        self.__download_url = new_url

    @staticmethod
    def enqueue_output(out, my_queue):
        try:
            for _line in iter(out.readline, b''):
                my_queue.put(_line)
        except Exception as ex:
            logging.exception(ex)
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
                        # line = line.decode('utf8')
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
                        # line = line.decode('utf8')
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
                        # line = line.encode('utf8')
                    except:
                        pass

                    if line != '':
                        line = line.rstrip()
                        try:
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
                        except Exception as ex:
                            logging.exception(ex)

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
                        # line = line.encode('utf8')
                    except:
                        pass
                    # got line
                    if line != '':
                        if 'unable to download video data' in line:
                            loop_timeout = loop_timeout / 2
                        # if 'Unable to download webpage' in line:
                        #     loop_timeout = loop_timeout / 1.2
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

    @staticmethod
    def real_download_youtube_dl(url, proxy_info, loop_timeout=3600, verbose=False):
        # type: (str, str, int, bool) -> bool
        ret = False
        logging.warning('Start Real download for {} {}'.format(url, proxy_info))
        start_time = time.time()
        ON_POSIX = 'posix' in sys.builtin_module_names
        _flags = ' --limit-rate 2M --retries 3 --no-check-certificate --prefer-insecure '
        if verbose:
            _flags = '{} --verbose'.format(_flags)
        if len(proxy_info):
            _cmd = "youtube-dl --proxy=\"{}\" {} {}".format(proxy_info, _flags, url)
        else:
            _cmd = "youtube-dl {} {}".format(_flags, url)
        logging.warning('CMD:: {:<250}'.format(_cmd))
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
                        # line = line.encode('utf8')
                    except:
                        pass

                    if line != '':
                        line = line.rstrip()
                        try:
                            if 'Downloading webpage' in line:
                                loop_timeout = loop_timeout * 20
                                #f_print = False
                            if 'Downloading video info webpage' in line:
                                loop_timeout = loop_timeout * 20
                                #f_print = False
                            if 'Resuming download at byte ' in line:
                                loop_timeout = loop_timeout * 20
                            if ' Destination:' in line:
                                loop_timeout = loop_timeout * 20
                                #f_print = False
                            if ' Downloading js player ' in line:
                                loop_timeout = loop_timeout * 20
                        except Exception as ex:
                            logging.exception(ex)

                        if '%' in line:
                            try:
                                if "\r" in line:
                                    # self.find_avg_speed(line)
                                    _lines = line.split("\r")
                                    logging.info('DL: File started download for [{}]'.format(proxy_info))
                                    for _l in _lines:
                                        _tmp_str = '{}'.format(_l)
                                        # if len(_tmp_str) > 5:
                                            # self.last_real_download_traffic_line = \
                                            #     _tmp_str.replace('[download]', '').strip()
                                    f_print = False
                                else:
                                    logging.info('REAL DL: {} File started download for [{}]'.format(proxy_info, line))
                                ret = True
                            except Exception as ex:
                                logging.exception(ex)
                        if f_print:
                            logging.info('REAL DL - {}: RT {} STDOUT: {}'.format(proxy_info, round(run_time, 1), line))
                try:
                    line = q_error_em.get_nowait()
                except Empty:
                    pass
                else:

                    try:
                        if isinstance(line, bytes):
                            line = line.decode('utf8')
                        # line = line.encode('utf8')
                    except:
                        pass
                    # got line
                    if line != '':
                        # if 'unable to download video data' in line:
                        #     loop_timeout = loop_timeout / 2
                        # if 'Unable to download webpage' in line:
                        #     loop_timeout = loop_timeout / 1.2
                        if 'for merge and will be merged into mkv' in line:
                            continue
                        logging.warning('REAL DL:STDERR: {} - {}'.format(proxy_info, line.rstrip()))

                if run_time > loop_timeout:
                    cont_this_loop = False
            except Exception as ex:
                logging.exception(ex)
        if not CONTINUE_LOOP:
            logging.warning('REAL DL killed for {}'.format(proxy_info))
        if not cont_this_loop:
            # send signal to YT process
            os.killpg(os.getpgid(this_process.pid), signal.SIGTERM)
            err_msg = 'REAL DL: {} - Aborted! Timeout expired after {} sec'.format(proxy_info, loop_timeout)
            logger.error(err_msg)
            try:
                try:
                    t_stdout_yt.join(0)
                except Exception as ex:
                    logger.error('REAL DL: cannot kill the thread: {}, {}'.format(t_stdout_yt, ex))
                try:
                    t_error_em.join(0)
                except Exception as ex:
                    logger.error('REAL DL: cannot kill the thread: {}, {}'.format(t_error_em, ex))
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
            logging.info('REAL DL: {} - YOUTUBE RES IS {} - Finish in {}'.format(
                proxy_info, ret, end_time - start_time))

        return ret

    def run(self):
        time.sleep(1)
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
                time.sleep(0.1)
                proxy_info = self.queue.get().strip()  # type: str
            except Exception as ex:
                logging.error('Error in {}'.format(first_input))
                logging.exception(ex)
            try:
                if len(proxy_info):
                    self.proxy_info = proxy_info
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
                        sock = opener.open(req, timeout=180)
                        encoding = sock.headers.get_content_charset('utf-8')
                        rs = sock.read(100000)
                        end_t = time.time()
                        rs = rs.decode(encoding, errors='ignore')
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
                                    logging.warning(' ! ! ! Good thread found {}'.format(self.id))
                                    self.isGood = True
                                    break
                                else:
                                    raise DownloadYoutubeDlException(
                                        'download_youtube_dl returned False for {}'.format(proxy_info))
                            except:
                                pass
                            finally:
                                ThreadUrl.delay_sem.release()
                        else:
                            if PRINT_BAD:
                                logging.error('start_youtube_dl returned False for {}'.format(proxy_info))
                            raise StartYoutubeDlException('start_youtube_dl returned False for {}'.format(proxy_info))
                    else:

                        if not sock.msg or sock.code != 200:
                            if PRINT_BAD:
                                logging.error('BAD socket')
                            raise Exception('BAD socket')
                        if CHECK_YOUTUBE_COUNTRY and 'UNPLAYABLE' in rs:
                            if PRINT_BAD:
                                logging.error('UNPLAYABLE FOUND')
                            raise Exception('UNPLAYABLE FOUND')
                else:
                    logging.debug('Skip connection to [{}]'.format(first_input))
            except StartYoutubeDlException as ex:
                logging.error(' *** StartYoutubeDlExceptionfor {:<70} - {}'.format(proxy_info, ex))
                ThreadUrl.total_errors += 1
            except DownloadYoutubeDlException as ex:
                logging.error(' *** DownloadYoutubeDlException {:<70} - {}'.format(proxy_info, ex))
                ThreadUrl.total_errors += 1
            except urllib.error.URLError as ex:
                logging.error(' *** URL ERROR for {:<70} - {}'.format(proxy_info, ex))
                ThreadUrl.url_error += 1
                ThreadUrl.total_errors += 1
            except RemoteDisconnected as ex:
                logging.error(' *** RemoteDisconnected for {:<120} - {}'.format(proxy_info, ex))
                ThreadUrl.total_errors += 1
            except BadStatusLine as ex:
                logging.error(' *** BadStatusLine for {:<80} - {}'.format(proxy_info, ex))
                ThreadUrl.total_errors += 1
            except socket.timeout as ex:
                logging.error(' *** socket.timeout: for {:<60} - {}'.format(proxy_info, ex))
                ThreadUrl.total_errors += 1
            except (urllib.request.URLError, ssl.SSLError) as ex: # , httplib.BadStatusLine,
                ThreadUrl.total_errors += 1
                if PRINT_BAD:
                    logging.error('Cannot connect to {} - {}'.format(clean_proxy_info, ex.message))
            except Exception as ex:
                logging.error("------------------")
                logging.exception(ex)
                logging.error("------------------")
                ThreadUrl.total_errors += 1
                # output.append(('x', proxy_info))
            finally:
                self.queue.task_done()  # signals to queue job is done
            break
        logging.warning(' RES IS {} EXIT FROM {:<3}/{:>3} In progress {:<3}/ Good {:>2} UrlError:{} Totoal Errors: {}'.
                        format(self.isGood, self.id, ThreadUrl.total_urls, queue.unfinished_tasks,
                                ThreadUrl.good_found, ThreadUrl.url_error, ThreadUrl.total_errors))

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

    @staticmethod
    def download_good_sync():
        time.sleep(120)
        _p = '{:5} - {:>6} - {:>25} - {:>10} - {:>10} - {}'
        logging.debug('download_good_sync')
        while CONTINUE_LOOP:
            for _t in ThreadUrl.started_threads:
                if _t.isGood:
                    logging.warning(' - - - - - - - START DOWNLOAD {}'.format(_t.proxy_info))
                    ThreadUrl.real_download_youtube_dl(_t.download_url, _t.proxy_info)
        # logging.info(_p.format('ID', 'Time', 'PROXY HOST', 'PASS yt-dl', 'Speed', 'Speed Line'))
        # for id, first_time, host, download_res, speed, for_th in output:
        #     logging.info(_p.format(id, first_time, host, download_res, speed, for_th))
        #     ThreadUrl.real_download_youtube_dl(url, host)
        # logging.debug('')

    @staticmethod
    def download_good(url=''):
        _p = '{:5} - {:>6} - {:>25} - {:>10} - {:>10} - {}'
        logging.debug('')
        logging.info(_p.format('ID', 'Time', 'PROXY HOST', 'PASS yt-dl', 'Speed', 'Speed Line'))
        for id, first_time, host, download_res, speed, for_th in output:
            logging.info(_p.format(id, first_time, host, download_res, speed, for_th))
            ThreadUrl.real_download_youtube_dl(url, host)
        logging.debug('')


    @staticmethod
    def parse_args():
        parser = argparse.ArgumentParser()
        parser.add_argument("-v", "--video", action='store', default='', help="video link")
        return parser.parse_args()

    @staticmethod
    def clean_host(input_proxy):
        # type: (str) -> str
        clean_proxy_info = input_proxy.replace('\xc2\xa0', ' ').strip()  # type: str
        clean_proxy_info = clean_proxy_info.replace('\xa0', ' ').strip()  # type: str
        if ' ' in clean_proxy_info:
            proxy_info = clean_proxy_info.split(' ')[1]
        else:
            proxy_info = clean_proxy_info
        return proxy_info

    @staticmethod
    def clean_hosts_list(input_list):
        # type: (typing.List[str]) -> typing.List[str]
        ret_list = []  # type: typing.List[str]
        for tmp_host in input_list:
            try:
                tmp_host_clean = ThreadUrl.clean_host(tmp_host)
                if tmp_host_clean not in ret_list:
                    ret_list.append(tmp_host_clean)
            except Exception as ex:
                logging.exception(ex)
        return ret_list


def signal_handler(sig, frame):
    global CONTINUE_LOOP
    CONTINUE_LOOP = False
    logging.warning('INTERRUPT: Exiting from MAIN - SIGNAL RECEIVED {}'.format(sig))
    print('INTERRUPT: Exiting from MAIN - SIGNAL RECEIVED {}'.format(sig))
    time.sleep(0.5)
    for _t in ThreadUrl.threads:
        try:
            _t.join(0)
        except Exception as ex:
            logging.exception(ex)
    sys.exit(27)


def main():
    #signal.signal(signal.SIGTERM, signal_handler)
    #signal.signal(signal.SIGINT, signal_handler)
    #signal.signal(signal.SIGABRT, signal_handler)
    #signal.signal(signal.SIGPIPE, signal_handler)
    #signal.signal(signal.SIGHUP, signal_handler)
    start = time.time()
    args = ThreadUrl.parse_args()
    download_good = False
    started_threads = []  # type: typing.List[ThreadUrl]

    hosts = [host_tmp.strip() for host_tmp in open(input_file).readlines()]
    new_hosts = ThreadUrl.clean_hosts_list(hosts)
    logging.warning('Starting list with {} hosts cleaned, total in list {}'.format(len(new_hosts), len(hosts)))
    hosts = new_hosts
    # spawn a pool of threads, and pass them queue instance
    # for i in range(len(hosts)):
    #     t = ThreadUrl(queue)
    #     if len(args.video):
    #         t.set_download_url(args.video)
    #         download_good = True
    #     t.setDaemon(True)
    #     t.start()
    #     time.sleep(0.01)
    #     started_threads.append(t)

    ThreadUrl.total_urls = len(hosts)
    counter = 0
    added_hosts = []
    logging.warning(" --- Started {} Threads Elapsed Time: {}".format(THREADS, round(time.time() - start, 2)))

    _looper = threading.Thread(target=ThreadUrl.download_good_sync)
    _looper.setDaemon(True)
    _looper.start()
    for host_tmp in hosts:
        if host_tmp not in added_hosts:

            t = ThreadUrl(queue, args.video)
            if len(args.video):
                t.set_download_url(args.video)
                download_good = True
            t.setDaemon(True)
            t.start()
            time.sleep(0.01)
            ThreadUrl.started_threads.append(t)
            new_started_threads = ThreadUrl.started_threads


            added_hosts.append(host_tmp)
            counter += 1
            queue.put(host_tmp)
            time.sleep(0.1)
            _tsks = queue.unfinished_tasks
            if _tsks > 1:
                if _tsks < 10:
                    _ut = round(_tsks / 10)
                    _st = min(0.01, _ut)
                elif _tsks < 30:
                    _ut = round(_tsks / 8)
                    _st = min(10, _ut)
                elif _tsks < 40:
                    _ut = round(_tsks / 4)
                    _st = min(20, _ut)
                else:
                    _ut = round(_tsks / 2)
                    _st = min(60, _ut)
                logging.info('Sleep for {} ; unfinished tasks {}'.format(_st, _tsks))
                time.sleep(_st)
            try:
                for _t in new_started_threads:
                    if not _t.isAlive():
                        if _t.isGood:
                            pass  # Should  not get here
                        else:
                            _t.join(0)
                            ThreadUrl.started_threads.remove(_t)
            except Exception as ex:
                logging.exception(ex)
        if counter > 100:
            logging.warning('EXIT FROM searcher for first 100 entryies')
            break
    logging.info('Added {} hosts to check'.format(counter))
    # wait on the queue until everything has been processed
    queue.join()
    logging.warning("Elapsed Time: {}".format(round(time.time() - start, 2)))
    ThreadUrl.print_good(True)

    if download_good:
        logging.warning('')
        logging.warning('Starting download video via good proxy [{}]:'.format(args.video))
        logging.warning('')
        ThreadUrl.download_good(args.video)
        logging.warning('Finish')

    logging.warning("Elapsed Time: {}".format(round(time.time() - start, 2)))


if __name__ == '__main__':
    main()
