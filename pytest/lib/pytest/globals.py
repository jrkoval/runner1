import os
import sys
import time
import types
import errno
import fcntl
import signal
import thread
import pickle
import logging
from threading import Condition as _Condition


PASSED = 0
FAILED = 1
PASS = 46
FAIL = 48
ISSUE = 45
ABORT = 49
SKIP = 47
WIDTH = 80
LOCK_TIMEOUT = 5
EQUAL_HEADER = '{0:=^' + str(WIDTH - 1) + '}'
STAR_HEADER = '{0:*^' + str(WIDTH - 1) + '}'
SPACE_HEADER = '{0: ^' + str(WIDTH - 1) + '}'
DASH_HEADER =  '{0:-^' + str(WIDTH - 1) + '}'
LOG_SETTINGS = {}


class NullHandler(logging.Handler):
    """
    This handler does nothing. It's intended to be used to avoid the
    "No handlers could be found for logger XXX" one-off warning. This is
    important for library code, which may contain code to log events. If a user
    of the library does not configure logging, the one-off warning might be
    produced; to avoid this, the library developer simply needs to instantiate
    a NullHandler and add it to the top-level logger of the library module or
    package.
    """

    def handle(self, record):
        pass

    def emit(self, record):
        pass

    def createLock(self):
        self.lock = None


debug_logger = logging.getLogger('debug')
debug_logger.propagate = False
debug_logger.addHandler(NullHandler())
file_logger = logging.getLogger('file')
file_logger.propagate = False
file_logger.addHandler(NullHandler())
stream_logger = logging.getLogger('stream')
stream_logger.propagate = False
stream_logger.addHandler(NullHandler())
logging.addLevelName(ABORT, 'ABORT')
logging.addLevelName(FAIL, 'FAIL')
logging.addLevelName(ISSUE, 'ISSUE')
logging.addLevelName(PASS, 'PASS')
logging.addLevelName(SKIP, 'SKIP')


PYTEST_PATH = ['']
try:
    PYTEST_PATH.extend(os.environ['PYTEST_PATH'].split(':'))
except KeyError:
    pass
path = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
PYTEST_SCEN_PATH = os.path.abspath(os.path.join(path, 'scen'))
PYTEST_DATA_PATH = os.path.abspath(os.path.join(path, 'data'))
PYTEST_SYSTEMS_PATH = os.path.join(PYTEST_DATA_PATH, 'systems')
PYTEST_PATH.append(PYTEST_SCEN_PATH)
PYTEST_PATH.append(PYTEST_DATA_PATH)
del path


class GlobalError(Exception):
    """Raised when any class in :mod:`~pytest.globals` encounters an error.
    """

class LockError(Exception):
    pass


class Lock(object):
    def __init__(self, name, option='w'):
        self.name = name
        try:
            self.file = open(name, option)
        except IOError as e:
            if e.errno == errno.ENOENT:
                f = open(name, 'w')
                f.close()
                self.file = open(name, option)
            else:
                raise e

    def acquire(self, timeout=None):
        delay = 0.0005
        if timeout is None:
            while True:
                try:
                    fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except IOError as e:
                    if e.errno != errno.EAGAIN:
                        raise e
                    else:
                        delay = min(delay * 2, .05)
                        time.sleep(delay)
                else:
                    return True
        else:
            endtime = time.time() + timeout
            while True:
                try:
                    fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except IOError as e:
                    if e.errno != errno.EAGAIN:
                        raise e
                    else:
                        remaining = endtime - time.time()
                        if remaining <= 0:
                            return False
                        delay = min(delay * 2, remaining, .05)
                        time.sleep(delay)
                else:
                    return True

    def release(self):
        fcntl.flock(self.file, fcntl.LOCK_UN)

    def download(self, acquire=True, release=False, exit=True,
                 timeout=LOCK_TIMEOUT):
        if acquire and not self.acquire(timeout):
            if exit:
                print('Timed out waiting for lock')
                sys.exit(FAILED)
            else:
                raise LockError('Timed out waiting for lock')
        lock_file = open(self.name)
        try:
            data = pickle.load(lock_file)
        except Exception:
            data = None
        lock_file.close()
        if release:
            self.release()
        return data

    def upload(self, data, acquire=False, release=True, exit=True,
               timeout=LOCK_TIMEOUT):
        if acquire and not self.acquire(timeout):
            if exit:
                print('Timed out waiting for lock')
                sys.exit(FAILED)
            else:
                raise LockError('Timed out waiting for lock')
        lock_file = open(self.name, 'w')
        pickle.dump(data, lock_file)
        lock_file.close()
        if release:
            self.release()

    def __del__(self):
        try:
            self.file.close()
        except AttributeError:
            pass


def Condition(*args, **kwargs):
    def wait(self, timeout=None):
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        waiter = thread.allocate_lock()
        waiter.acquire()
        self._Condition__waiters.append(waiter)
        saved_state = self._release_save()
        try:
            delay = 0.0005
            if timeout is None:
                while True:
                    gotit = waiter.acquire(0)
                    if gotit:
                        break
                    delay = min(delay * 2, .05)
                    time.sleep(delay)
                if __debug__:
                    self._note("%s.wait(): got it", self)
                return_value = True
            else:
                endtime = time.time() + timeout
                while True:
                    gotit = waiter.acquire(0)
                    if gotit:
                        break
                    remaining = endtime - time.time()
                    if remaining <= 0:
                        break
                    delay = min(delay * 2, remaining, .05)
                    time.sleep(delay)
                if not gotit:
                    if __debug__:
                        self._note("%s.wait(%s): timed out", self, timeout)
                    try:
                        self._Condition__waiters.remove(waiter)
                    except ValueError:
                        pass
                    return_value = False
                else:
                    if __debug__:
                        self._note("%s.wait(%s): got it", self, timeout)
                    return_value = True
        finally:
            self._acquire_restore(saved_state)
        return return_value
    condition = _Condition(*args, **kwargs)
    method = types.MethodType(wait, condition)
    setattr(condition, 'wait', method)
    return condition


def check_make_dir(path, level=logging.CRITICAL, log=True, empty=False,
                   error=False):
    """Checks the path if it is a directory and makes a directory if the path
    does not exist.

    :param str path: The path to check.
    :param int level: The level to log any errors.
    :returns: The boolean of the directory's existence.
    :rtype: bool
    """
    try:
        os.makedirs(path)
        value = True
    except Exception as e:
        if os.path.isdir(path):
            value = True
        else:
            if log:
                if empty:
                    log_empty(str_error(e), level=level)
                else:
                    logging.log(level, str_error(e))
            value = False
    if error:
        if not value:
            raise e
    return value


def floatable(string):
    """Checks if the string is convertable to a float.

    :param str string: The string to check.
    :returns: The boolean of the string's ability to be converted to a float.
    :rtype: bool
    """
    try:
        float(string)
        return True
    except ValueError:
        return False


def get_systems_path(file_name):
    """Gets the whole file path of the file. The file is searched in the systems
    directory of athena.

    :param str file_name: The name of the file to get the path for.
    :returns: The file path or `None` if the file is not found.
    :rtype: str
    """
    candidate = os.path.join(PYTEST_SYSTEMS_PATH, file_name)
    if os.path.isfile(candidate):
        file_path = candidate
    else:
        file_path = None
    return file_path


def get_file_path(file_name):
    """Gets the whole file path of the file. The file is searched in the paths
    in the environment variable PYTEST_PATH, the scen directory of athena, and
    the data directory of athena.

    :param str file_name: The name of the file to get the path for.
    :returns: The file path or `None` if the file is not found.
    :rtype: str
    """
    file_path = None
    for directory_name in PYTEST_PATH:
        candidate = os.path.join(directory_name, file_name)
        if os.path.isfile(candidate):
            file_path = candidate
            break
    return file_path


def import_module(name):
    """Retrieves the module.

    :param str name: The name of the module.
    :returns: The module.
    :rtype: module
    """
    module = __import__(name)
    components = name.split('.')
    for component in components[1:]:
        module = getattr(module, component)
    return module


def sleep(timeout):
    delay = 0.0005
    endtime = time.time() + timeout
    while True:
        remaining = endtime - time.time()
        if remaining <= 0:
            break
        delay = min(delay * 2, remaining, .05)
        time.sleep(delay)


def str_error(e):
    """Formats an exception.

    For example::

        Exception: Message

    :param Exception e: The exception to format.
    :returns: The string representing the exception.
    :rtype: str
    """
    return type(e).__name__ + ': ' + str(e)


def str_to_bool(string):
    """Converts a string to the corresponding boolean.

    :param str string: The string to convert.
    :returns: The boolean representing the string.
    :rtype: bool
    """
    if type(string) is bool:
        return string
    string = string.title()
    if string == 'True':
        return True
    elif string == 'False':
        return False
    else:
        raise GlobalError('Invalid value')


def str_table(table, separator=' ', header='-', width=None):
    new_table = []
    for column in zip(*table):
        lengths = [len(str(c)) for c in column]
        maximum = max(lengths)
        new_table.append([str(c).ljust(maximum) for c in column])
    strings = []
    for row in zip(*new_table):
        strings.append(separator.join(row))
    if header and strings:
        if width is None:
            width = max(map(len, strings))
        strings.insert(1, header*width)
    return '\n'.join(strings)


def add_log_setting(handler, formatter):
    """Adds a handler and formatter to the settings so that :func:`log_empty`
    and :func:`log_result` work properly for the handler.

    :param Handler handler: The handler to add.
    :param Formatter formatter: The formatter associated with the handler.
    """
    global LOG_SETTINGS
    LOG_SETTINGS[handler] = formatter
    handler.setFormatter(formatter)
    logging.root.addHandler(handler)


def remove_log_setting(handler):
    """Removes the handler and the associated formatter from the settings.

    :param Handler handler: The handler to remove.
    """
    global LOG_SETTINGS
    del LOG_SETTINGS[handler]
    logging.root.removeHandler(handler)


def log_empty(message='', level=logging.CRITICAL, logger=logging):
    """Logs a message without any formatting.

    :param str message: The message to log.
    :param int level: The level to log the message.
    :param Logger logger: The logger to log the message to.
    """
    empty = logging.Formatter()
    for log_handler in LOG_SETTINGS:
        log_handler.setFormatter(empty)
    if type(logger) is list:
        for l in logger:
            l.log(level, message)
    else:
        logger.log(level, message)
    for log_handler in LOG_SETTINGS:
        log_handler.setFormatter(LOG_SETTINGS[log_handler])


def log_result(message='', level=logging.CRITICAL, logger=logging):
    """Logs a message with result formatting.

    :param str message: The message to log.
    :param int level: The level to log the message.
    :param Logger logger: The logger to log the message to.
    """
    if message:
        log_empty(message='[RESULT] ' + message, level=level, logger=logger)
    else:
        log_empty(message='[RESULT]', level=level, logger=logger)
