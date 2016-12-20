"""
This module provides openboot functionality and methods.
"""

import time
import logging
from pexpect import TIMEOUT as TimeoutError
from globals import log_empty, debug_logger, file_logger, sleep
from pytest.ilom import ESCAPE


TIMEOUT = 600
BOOT_TIMEOUT = 1200
INSTALL_TIMEOUT = 4800
USER = 'OpenBoot'
ADDRESS = 'Console'
PASSWORD = 'None'
PROMPT = '} ok '


class OpenBootError(Exception):
    """Raised when the connection encounters an error with OpenBoot.
    """


def boot(self, disk=None, timeout=-1):
    """
    """
    if timeout == -1:
        if self.timeout < TIMEOUT:
            timeout = TIMEOUT
        else:
            timeout = self.timeout
    command = 'boot'
    if disk is not None:
        command += ' ' + disk
    boot_list = [self.prompt, '(?i)Console Login:', TimeoutError]
    logging.info('Starting to boot. This might take a while...')
    result = self.sendcmd(command, prompt=boot_list, timeout=timeout,
                          debug=False).strip()
    log_empty(result, level=logging.INFO, logger=[debug_logger, file_logger])
    if self.match_index == 0:
        raise OpenBootError('Could not boot\n' + result)
    elif self.match_index == 1:
        logging.info('Finished booting')
    else:
        raise OpenBootError('Timed out in booting')
    return result


def stop_console(self, log=True):
    """
    """
    if hasattr(self, 'in_console'):
        self.send(ESCAPE)
        self.switch(timeout=-1)
        del self.in_console
        if log:
            logging.info('Host console stopped')
    elif log:
        logging.info('Connection not in console')


def install(self, disk=None, timeout=-1, log=False):

    """TODO: Login to burpen"""

    if timeout == -1:
        if self.timeout < INSTALL_TIMEOUT:
            timeout = INSTALL_TIMEOUT
        else:
            timeout = self.timeout
    if log:
        logging.info('Starting disk install...')
    self.sendcmd('set-defaults', timeout=120)
    if disk is not None:
        self.sendcmd('setenv boot-device ' + disk)
    self.sendline('boot net:dhcp - install')
    start_list = ['(?i)Automated Installation finished successfully',
                  '(?i)Automated Installation failed',
                  '(?i)Timed out waiting for BOOTP/DHCP reply',
                  '(?i)Unable to locate the disk',
                  'FATAL',
                  TimeoutError]
    for i in range(10):
        install_output = self.sync(start_list, timeout=timeout, debug=False,
                                   after=True).strip()
        if self.match_index == 2:
            continue
        else:
            break
    else:
        return (install_output, 2)
    if not install_output:
        install_output = 'No start output available'
    log_empty(install_output, level=logging.INFO,
              logger=[debug_logger, file_logger])
    if self.match_index == 0:
        if log:
            logging.info('Automated Install complete')
            logging.info('Waiting for configuration to complete...')
        start_list = ['(?i)Console Login:']
        self.sync(start_list, timeout=BOOT_TIMEOUT, debug=False)
        sleep(300)
        if log:
            logging.info('Configuration complete')
    return (install_output, self.match_index)


def probe_scsi_all(self, timeout=120, log=False):
    self.sendline('probe-scsi-all')
    sync_list = [self.prompt, '(?i)Do you wish to continue']
    result = self.sync(sync_list, timeout=timeout)
    if self.match_index == 1:
        result = self.sendcmd('y', timeout=timeout, log=log)
    result = result.splitlines()
    i = 0
    current = None
    boot_devices = []
    while i < len(result):
        if result[i].startswith('/'):
            if 'sas' in result[i].lower() or 'scsi' in result[i].lower():
                current = result[i].strip()
            else:
                current = None
        elif 'disk' in result[i].lower():
            if current is not None:
                i += 1
                line = result[i].split()
                line = [x.lower() for x in line]
                disk = line[line.index('sasaddress')+1]
                boot_devices.append((current,disk))
        i += 1
    return boot_devices


def probe_nvme_all(self, timeout=120, log=False):
    self.sendline('probe-nvme-all')
    sync_list = [self.prompt, '(?i)Do you wish to continue']
    result = self.sync(sync_list, timeout=timeout)
    if self.match_index == 1:
        result = self.sendcmd('y', timeout=timeout, log=log)
    result = result.splitlines()
    i = 0
    current = None
    boot_devices = []
    for line in result:
        if line.startswith('/'):
            boot_devices.append(line.strip())
    return boot_devices
