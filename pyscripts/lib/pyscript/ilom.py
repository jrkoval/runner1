"""
This module contains classes that provide connection functionality to ilom.
"""

import paramiko
import paramiko_expect
import socket
import logging

class IlomError(Exception):
    """Raised when the connection encounters an error with Ilom.
    """

def login(system):
    """
    The function I{login()} provides login functionality for Ilom. 
    param: system:         System object 
    param: user:           The system information to use when authenticating
                           this connection
    """
    if system == None:
       raise IlomError('login: missing system info')
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(hostname=system.sp_ipaddr, username=system.sp_username,
                                        password=system.sp_password)
    except Exception as e:
        raise IlomError(' Connection to system.sp_ipaddr failed ' + str(e))

    #for some reason, creating interact and returning it fails to
    #return an open connection, so this is handled in the testcase
    #interact = paramiko_expect.SSHClientInteraction(ssh, \
    #                                           timeout=10, display=True)
    logging.info("Connected to %s" % system.sp_ipaddr)

    #prompt = ['-> ']

    # get output from logging in; clears the expect buffer
    #try:
    #    match = interact.expect(prompt)
    #except socket.timeout:
    #     raise IlomError('login: timeout')

    return(ssh)

def start_sys(interact=None):
    """
    The function I{start_sys()} provides functionality to start /SYS from Ilom. 
    :param interact:       parmiko_expect.SSHClientInteraction object that
                           provides expect-like interface to ilom. 
    """
    if interact == None:
       raise IlomError('start_sys: missing interact fd')

    prompt = ['.*(?i)console login: ', 'Password: ', '-> ', '.*#.', '.*\[y\/N\]\?.']

    logging.info("Sending  stop -f /SYS")
    interact.send('stop -f -script /SYS')
    interact.expect(prompt)

    logging.info("Sending set /HOST/bootmode script=setenv auto-boot? true")
    interact.send('set /HOST/bootmode script=\'setenv auto-boot? true\'')
    interact.expect(prompt)

    logging.info("Sending  start -f -script /SYS")
    interact.send('start -f -script /SYS')
    interact.expect(prompt)
    if 'Starting' not in interact.current_output_clean:
       raise IlomError('start /SYS failed:' + interact.current_output_clean)
    logging.info("\nSending  start -f -script /SP/console")
    interact.send('start -f -script /SP/console')
    try:
        interact.expect(prompt)
    except:
        raise IlomError('failed to start /SP/console')

    logging.info("Start the host and wait for the login prompt")
    match = interact.expect(prompt, timeout=600)
    if match == 0:
        logging.info("got login prompt")
        pass
    else:
        logging.info("failed to get login prompt after start /SYS")
        raise IlomError('failed to get to the login prompt')

def ilom_set_prop(interact=None, target=None, property=None, log=True):
    """
    The function I{ilom_set()} provides functionality to set an ilom property. 
    :param interact:       parmiko_expect.SSHClientInteraction object that
                           provides expect-like interface to ilom. 
    :param target:         target to set
    :param property:       property to set
    """
    if interact == None:
       raise IlomError('set: missing interact fd')
    interact.send('set ' + target + " " + property)
    try:
        interact.expect("-> ")
    except:
       raise IlomError('ilom_set_prop: timeout')
    if "Invalid" in interact.current_output_clean or "No such object value" \
                  in interact.current_output_clean:
        raise IlomError('ilom_set_prop: ' + interact.current_output_clean)
    if log:
        logging.info(interact.current_output_clean.strip())

def ilom_get_prop(interact=None, target=None, property=None, log=True):
    """
    The function I{ilom_get()} provides functionality to get an ilom property. 
    :param interact:       parmiko_expect.SSHClientInteraction object that
                           provides expect-like interface to ilom. 
    :param target:         target to get
    :param property:       property to get
   
    """
    if interact == None:
       raise IlomError('ilom_get_prop: missing interact fd')
    interact.send('show ' + target + " " + property)
    try:
        interact.expect("-> ")
    except:
       raise IlomError('ilom_get_prop: timeout')
    if log:
        logging.info(interact.current_output_clean.strip())
    for line in interact.current_output_clean: 
        if property in interact.current_output_clean: 
            val = interact.current_output_clean.split("=")
            return(val[1].strip())
        else:
            raise IlomError('ilom_get_prop: " + target + " " + property + \
                                  "property not found')
            
