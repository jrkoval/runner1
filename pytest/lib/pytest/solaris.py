"""
This module provides Solaris funcionality.
"""

import re
import time
import logging
from pexpect import TIMEOUT as TimeoutError
from pytest.openboot import stop_console, OpenBootError, PROMPT
from pytest.globals import log_empty, debug_logger, file_logger


REBOOT_TIMEOUT = 600
SUNVTS_TIMEOUT = 300
INSTALLATION_TIMEOUT = 1800
STATUS = '(?P<status>\w+)\(Pass\=(?P<passed>\d+)/Error\=(?P<failed>\d+)\)'
STATUS_REGEX = re.compile(STATUS)
PERMIT_SSH_CMD = "perl -pi -e 's/^PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config"


class SolarisError(Exception):
    """Raised when the connection encounters an error with Solaris.
    """


class SunVTS_Test(object):
    def __init__(self, name, enabled, policy, number, stress, progress, status,
                 passed, failed):
        self.name = name
        self.enabled = enabled
        self.policy = policy
        self.number = number
        self.stress = stress
        self.progress = progress
        self.status = status
        self.passed = passed
        self.failed = failed


def login(self, log=True):
    self.sendline()
    login_list = ['(?i)Console Login:', TimeoutError]
    i = self.expect(login_list)
    if i == 1:
        raise SolarisError('Could not get to login prompt')
    if log:
        logging.info('Logging in')
    logging.debug('Login:')
    self.sendline(self.user)
    logging.debug(self.user)
    login_list = [self.prompt, '(?i)Password:', '(?i)Login incorrect']
    i = self.expect(login_list)
    if i == 1:
        logging.debug('Password:')
        self.sendline(self.password)
        logging.debug(self.password)
        i = self.expect(login_list)
    if i == 0 and log:
        logging.info('Logged in successfully')
    elif i == 1:
        raise SolarisError('Received password prompt again')
    elif i == 2:
        raise SolarisError('Login incorrect')

def logout(self, log=True):
    self.sendline()
    login_list = [self.prompt, TimeoutError]
    i = self.expect(login_list)
    if i == 1:
        raise SolarisError('Could not get to user prompt')
    if log:
        logging.info('Logging out')
    logout_list = ['(?i)Console Login:', TimeoutError]
    self.sendline('exit')
    i = self.expect(logout_list)
    if i == 1:
        raise SolarisError('Could not get to logout prompt')
    if log:
        logging.info('Logged out')

def reboot(self, login=True, log=True, timeout=REBOOT_TIMEOUT):
    if not hasattr(self, 'in_console'):
        raise SolarisError('Must be in console')
    if log:
        logging.info('Starting reboot')
    self.sendline('reboot')
    login_list = ['(?i)Console Login:', PROMPT, TimeoutError]
    output = self.sync(login_list, timeout=timeout)
    log_empty(output, level=logging.INFO,
              logger=[debug_logger, file_logger])
    if self.match_index == 2:
        raise SolarisError('Timed out in reboot')
    if self.match_index == 1:
        raise OpenBootError('Returned to OpenBoot')
    if login:
        self.login(log=log)
    if log:
        logging.info('Finished reboot')
    return output


def start_SunVTS(self, log=True):
    if log:
        logging.info('Starting SunVTS')
    start_command = '/usr/sunvts/bin/startsunvts -c'
    output = self.sendcmd(start_command, timeout=SUNVTS_TIMEOUT)
    if 'No such file or directory' in output:
        command = ('/net/bur413-114/export/m7t7/notes/t7_solaris_vts/' +
                   'install_t7m7_sunvts.sh')
        self.sendcmd(command, timeout=INSTALLATION_TIMEOUT)
        output = self.sendcmd(start_command, timeout=SUNVTS_TIMEOUT)
    status = self.sendcmd('echo $?', debug=False)
    if status != '1':
        raise SolarisError(output)
    self.SunVTS = True
    if log:
        logging.info('Finished starting SunVTS')


def stop_SunVTS(self, log=True):
    if hasattr(self, 'SunVTS'):
        if log:
            logging.info('Stopping SunVTS')
        self._SunVTS_command('quit')
        del self.SunVTS
        if log:
            logging.info('Finished stopping SunVTS')
    else:
        if log:
            logging.info('SunVTS already stopped')


def SunVTS_get_status(self, timeout=-1):
    output = self._SunVTS_command('get_status', timeout=timeout)
    values = output.split('/', 3)
    if len(values) != 4:
        raise SolarisError(output)
    status = values[0]
    try:
        passed = int(values[1].split('=', 1)[1].strip())
        failed = int(values[2].split('=', 1)[1].strip())
        elapsed_time = values[3].split('=', 1)[1].strip()
    except Exception:
        raise SolarisError(output)
    output = self._SunVTS_command('list_tests', timeout=timeout)
    lines = output.splitlines()
    tests = {}
    for line in lines:
        values = line.split(';')
        if len(values) != 6:
            continue
        try:
            test_name = values[0].split(':', 1)[1].strip()
            test_enabled = values[1].split(':', 1)[1].strip()
            policy_value = values[2].split(':', 1)[1].strip()
            test_policy, test_number = policy_value.split('=')
            test_stress = values[3].split(':', 1)[1].strip()
            test_progress = values[4].split(':', 1)[1].strip()
            status_value = values[5].split(':', 1)[1].strip()
            match = STATUS_REGEX.search(status_value)
            test_status = match.group('status')
            test_passed = match.group('passed')
            test_failed = match.group('failed')
        except Exception:
            continue
        test = SunVTS_Test(test_name, test_enabled, test_policy, test_number,
                           test_stress, test_progress, test_status, test_passed,
                           test_failed)
        tests[test_name] = test
    return (status, passed, failed, elapsed_time, tests)


def _SunVTS_command(self, command, timeout=SUNVTS_TIMEOUT):
    if not hasattr(self, 'SunVTS'):
        raise SolarisError('SunVTS is not started')
    string = '/usr/sunvts/bin/vts_cmd ' + command
    output = self.sendcmd(string, timeout=timeout)
    status = self.sendcmd('echo $?', debug=False)
    if status != '0':
        raise SolarisError(output)
    return output


def permit_root_ssh(self):
    self.sendline(PERMIT_SSH_CMD)
    self.sync(debug=False)
    self.sendcmd('svcadm restart ssh')
    time.sleep(10)
