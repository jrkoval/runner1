"""
This module contains an abstract base class that must be implemented to create
a test to be run by pytest.
"""

import sys
import signal
import inspect
import logging
import traceback
from Queue import Queue
from pytest.globals import PASS, FAIL, ISSUE, ABORT, LockError


#: The list of class names that should be run by default. The tests are run in
#: order. This variable should be added to the module if there are default
#: tests.
TESTS = []


class TestError(Exception):
    """Raised when the class :class:`Test` or any of its subclasses
    encounters an error.
    """

class StopTestcase(Exception):
    """Raise to stop a testcase.
    """


class Test(object):
    """Base class that all tests should inherit from. When overriding
    :func:`__init__`, the :func:`__init__` of :class:`Test` must be called.
    Arguments and keyword arguments can be added to the new :func:`__init__`.
    To have a default set of testcases, the class variable `TESTCASES` should be
    modified.

    For example::

        class ExampleTest(Test):
            TESTCASES = ['example_testcase']

            def __init__(self, arg, kwarg=value):
                super(ExampleTest, self).__init__()
                ...

            def example_testcase(self, kwarg=vale):
                ...

    The following instance variables should not be overridden::

        failed_count
        passed_count
        issue_count
        current_failed_count
        current_passed_count
        current_issue_count
        current_caller
        stop
    """

    def web(function):
        function.web = True
        return function

    web = staticmethod(web)

    def silent(function):
        function.silent = True
        return function

    silent = staticmethod(silent)

    #: The list of method names that should be run by default. The testcases are
    #: run in order. This variable should be overridden if there are default
    #: testcases.
    TESTCASES = []

    def __init__(self):
        self.passed_count = 0
        self.failed_count = 0
        self.issue_count = 0
        self.aborted_count = 0
        self.current_passed_count = 0
        self.current_failed_count = 0
        self.current_issue_count = 0
        self.current_caller = None
        self.stop = False
        self.clean = True
        self.testcase_clean = True
        self.signalers = Queue()
        self.testcases = []
        self.debug = logging.debug
        self.info = logging.info
        self.warning = logging.warning
        self.error = logging.error
        self.critical = logging.critical
        self.log = logging.log
        self.info_lock = None
        signal.signal(signal.SIGUSR1, self.__handle)

    def abort(self, message='', stop=False, clean=True, testcase_clean=True):
        """Aborts a testcase. Also, logs the given message.

        :param str message: The reason for aborting. If this is '', then the
            given message is not logged.
        :param bool stop: The flag for stopping a test.
        :raises: :class:`TestError`
        """
        self.stop = stop
        self.clean = clean
        self.testcase_clean = testcase_clean
        self.aborted_count += 1
        self.__upload('abort')
        logging.log(ABORT, message)
        if message:
            raise TestError(message)
        else:
            raise TestError('Abort')

    def cleanup(self):
        """Placeholder method. This is always called when the test has finished
        running.
        """

    def testcase_cleanup(self):
        """Placeholder method. This is always called when a testcase has
        finished running.
        """

    def failed(self, message='', stop=False, clean=True, testcase_clean=True):
        """Fails a testcase. Also, logs the given message. This can be called
        multiple times in a testcase. Each failure within a testcase will have a
        number associated with it.

        :param str message: The reason for failing.
        :param bool stop: The flag for stopping a testcase.
        """
        self.__state(message=message, stop=stop, clean=True,
                     testcase_clean=True)

    def passed(self, message='', stop=False, clean=True, testcase_clean=True):
        """Passes a testcase. Also, logs the given message. This can be called
        multiple times in a testcase. Each pass within a testcase will have a
        number associated with it.

        :param str message: The reason for passing.
        :param bool stop: The flag for stopping a testcase.
        """
        self.__state(message=message, stop=stop, clean=True,
                     testcase_clean=True)

    def issue(self, message='', stop=False, clean=True, testcase_clean=True):
        """Records an issue with a testcase. Also, logs the given message. This
        can be called multiple times in a testcase. Each issue within a testcase
        will have a number associated with it.

        :param str message: The reason for the issue.
        :param bool stop: The flag for stopping a testcase.
        """
        self.__state(message=message, stop=stop, clean=True,
                     testcase_clean=True)

    def handle(self, object):
        """Placeholder method. This is always called when a SIGUSR1 signal is
        received.
        """

    def __state(self, message='', stop=False, clean=True, testcase_clean=True):
        self.clean = clean
        self.testcase_clean = testcase_clean
        message = str(message)
        stack = inspect.stack()
        try:
            state = stack[1][3]
        except IndexError:
            raise TestError('Invalid state')
        caller = stack[0][3]
        class_ = stack[0][0].f_locals['self']
        for i in range(len(stack)):
            try:
                new_class = stack[i][0].f_locals['self']
            except KeyError:
                break
            if new_class != class_:
                break
            caller = stack[i][3]
        if caller != self.current_caller:
            self.current_caller = caller
            self.current_passed_count = 0
            self.current_failed_count = 0
            self.current_issue_count = 0
        if state == 'passed':
            self.passed_count += 1
            self.current_passed_count += 1
            prefix = '[{0}] [No. {1}]'.format(caller, self.current_passed_count)
            level = PASS
        elif state == 'failed':
            self.failed_count += 1
            self.current_failed_count += 1
            prefix = '[{0}] [No. {1}]'.format(caller, self.current_failed_count)
            level = FAIL
        elif state == 'issue':
            self.issue_count += 1
            self.current_issue_count += 1
            prefix = '[{0}] [No. {1}]'.format(caller, self.current_issue_count)
            level = ISSUE
        else:
            raise TestError('Invalid state')
        self.__upload(state)
        if message:
            result = ' '.join([prefix, message])
            logging.log(level, result)
        else:
            logging.log(level, prefix)
        if stop:
            raise StopTestcase

    def __upload(self, state):
        if self.info_lock is not None:
            try:
                info_value = self.info_lock.download(exit=False)
            except LockError:
                pass
            else:
                info_value[state] += 1
                info_value['latest'][state] += 1
                try:
                    self.info_lock.upload(info_value, exit=False)
                except LockError:
                    self.info_lock.release()

    def __handle(self, signal, frame):
        try:
            signaler = self.signalers.get()
        except Exception as e:
            logging.critical('[handle] ' + str_error(e))
            signaler = None
        self.handle(signaler)


class Testcase(object):
    def __init__(self, name, *args, **kwargs):
        self.name = name
        self.args = args
        self.kwargs = kwargs
