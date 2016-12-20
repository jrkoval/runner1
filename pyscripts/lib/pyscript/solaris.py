"""
This module contains classes that provide connection functionality to a device.
"""

import paramiko
import paramiko_expect
import logging

class SolarisError(Exception):
    """Raised when the connection encounters an error with Solaris.
    """

def login(system):
    """
    The function I{login()} provides login functionality for Solaris.
    :param system:         System object
    :param user:           The system information to use when authenticating
                           this connection
    """

    if system == None:
       raise SolarisError('login: missing system info')
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(hostname=system.os_ipaddr, username=system.os_username,
                                        password=system.os_password)
    except Exception as e:
        raise SolarisError("solaris login failed" + str(e))

    logging.info("Connected to %s" % system.os_ipaddr)

    return(ssh)
