import re
import logging
import string
import os
import socket
import ssl
import sys
import time
import datetime
import exceptions
import traceback
from optparse import OptionParser
from configs import add_system, System

def main(name=None, version='1.0', *args, **kwargs):
    """Provides a setup of a script. 
       Parses the command line
       Reads the system infomation from the config file
       Initializes the logging
       Executes the tests
       Calculates runtime
       Prints a summary of the tests run

    """
    options, vargs = get_options(name, version, *args, **kwargs)
    f = 'config' + "/" + options.system 
    file=open(f, 'r')
    lines=file.readlines()
    for line in lines:
        l = line.strip()
        var = l.split("=")
        if (var[0].strip() == 'os_ipaddr'):
            os_ipaddr = var[1].strip()
        elif (var[0].strip() == 'os_username'):
            os_username = var[1].strip()
        elif (var[0].strip() == 'os_password'):
            os_password = var[1].strip()
        elif (var[0].strip() == 'sp_ipaddr'):
            sp_ipaddr = var[1].strip()
        elif (var[0].strip() == 'sp_username'):
            sp_username = var[1].strip()
        elif (var[0].strip() == 'sp_password'):
            sp_password = var[1].strip()
    system = System(os_ipaddr, os_username, os_password, 
                sp_ipaddr, sp_username, sp_password)
    add_system(system)

    # Set up logging
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s',
                 "%Y-%m-%d %H:%M:%S")
    empty = logging.Formatter()

    logging.root.setLevel(logging.INFO)

    # create a logger called log; this is a log like logger is a logger
    # create this so we can call empty_log with our own logger
    log = logging.getLogger (name = "tpm_auth_fuzz")

    stream_handler = logging.StreamHandler(sys.stdout)

    # create a handler to log the messages to  
    os.remove('/var/tmp/tpm_auth_fuzz.log')
    hdlr = logging.FileHandler('/var/tmp/tpm_auth_fuzz.log')
    hdlr.setFormatter(formatter)

    # tell the loggers log and logger to write to the file when they are called
    logging.root.addHandler(hdlr)
    logging.root.addHandler(stream_handler)

    module = __import__('security.tpmadm_fuzz')
    module = getattr(module, 'tpmadm_fuzz')
    from inspect import getmembers, isfunction
    functions_list = [o for o in getmembers(module) if isfunction(o[1])]
    set_log_format(hdlr, stream_handler, formatter)
    t_passed = 0
    t_failed = 0
    t_issues = 0 
    SECONDS = time.time()
    results_summary = {}

    for test in module.TESTCASES:
        for function in functions_list:
            if function[0] == test:
                set_log_format(hdlr, stream_handler, empty)
                log.info('{0:=^79}'.format(function[0]))
                set_log_format(hdlr, stream_handler, formatter)
                passed = failed = issues = 0
                messages = []
                try:
                    passed, failed, issues, messages = function[1]() 
                except Exception as e:
                    log.info("failed to run\n "  + traceback.format_exc())
                results = {test:(passed, failed, issues, messages)}
                results_summary.update(results)
                t_passed = t_passed + passed
                t_failed = t_failed + failed
                t_issues = t_issues + issues 
    results = {'Totals':(t_passed, t_failed, t_issues)}
    results_summary.update(results)
    set_log_format(hdlr, stream_handler, empty)
    for r in results_summary.keys():
        log.info('\n{0:=^79}'.format(r))
        log.info("    Passed: " +str(results_summary[r][0]))
        log.info("    Failed: " +str(results_summary[r][1]))
        log.info("    Issues: " +str(results_summary[r][2]))
        if r != 'Totals':
            log.info("    Debug messages:")
            for m in results_summary[r][3]:
                log.info('    ' + m)

    # Calulate and display total runtime
    running_time = int(time.time() - SECONDS)
    running_time = str(datetime.timedelta(seconds=running_time))
    log.info('\n{0:=^79}'.format(' Running Time: ' + str(running_time) + ' '))
    log.info('\n{0:=^79}'.format(' Log File: /var/tmp/tpm_auth_fuzz.log '))
    set_log_format(hdlr, stream_handler, formatter)

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

def set_log_format(hdlr, stream_handler, format):
     hdlr.setFormatter(format)
     stream_handler.setFormatter(format)

def get_options(name, version, *args, **kwargs):
    arguments = ' '.join(args)
    kwargument_list = ['{0}={1}'.format(key, value)
                       for key, value in kwargs.items()]
    kwarguments = ' '.join(kwargument_list)
    extra = arguments + ' ' + kwarguments
    usage = 'Usage: %prog -s system name -t test [OPTION]... ' + extra
    usage = usage.strip()
    parser = OptionParser(usage=usage, version=version)
    if name is None:
        parser.add_option('-t', '--test', action='store',
                          dest='test',
                          help='test to be run')
        parser.add_option('-s', '--system',
                      action='store', dest='system',
                      help='system required by test')
    try:
        options, vargs = parser.parse_args()
    except Exception as e:
        parser.print_help()
        print('')
        print(str_error(e))
        sys.exit(1)
    if not options.system or not options.test:
        print('must enter system name and test to run') 
        print(usage)
        sys.exit(1)
    return (options, vargs)
