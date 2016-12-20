"""
This module parses the command line args, sets up logging, runs the
tests, and reports the results.
"""

import os
import sys
import pdb
import time
import socket
import logging
import datetime
import tempfile
import traceback
from datetime import datetime as dt
from optparse import OptionParser, SUPPRESS_HELP
from xml.etree import ElementTree
from pytest.globals import *
from pytest.test import *
from pytest.connections import Connection
from pytest.environment import add_system, System, Subsystem, User, Component


CURRENT_TEST = None
FORMAT = 'DEFAULT'
FORMATS = {'DEFAULT':'%(asctime)s - [%(levelname)s] %(message)s',
           'DEBUG':'%(asctime)s - [%(module)s] [%(funcName)s] ' +
                   '[line %(lineno)d] [%(levelname)s] %(message)s'}
LEVEL = 'INFO'
LEVELS = {'DEBUG':logging.DEBUG, 'INFO':logging.INFO,
          'WARNING':logging.WARNING, 'ERROR':logging.ERROR,
          'PASS':PASS, 'SKIP':SKIP, 'FAIL':FAIL, 'ABORT':ABORT,
          'CRITICAL':logging.CRITICAL}
STREAM = 'PASS'
TIME = '%Y/%m/%d %H:%M:%S'
TIME_FILE = '%Y-%m-%d_%H-%M-%S-%f'


class OptionError(Exception):
    """Raised when there are problems with the options.
    """


def main(name=None, version='1.0', *args, **kwargs):
    """Provides an easy setup of a script. Add this function to the main part of
    a script and it will parse all the options and run the tests.

    For example::

        if __name__ == "__main__":
            main('example.py', '1.0', 'arg1', 'arg2', kwarg='default_value')

    :param str name: The name of the script.
    :param str version: The version of the script.
    :param str args: The names of the arguments. This is used to display the
        help message.
    :param str kwargs: The names of the keyword arguments and the default
        values. This is used to display the help message.
    """
    try:
        SECONDS = time.time()
        command = ' '.join(sys.argv)
        options, vargs = get_options(name, version, *args, **kwargs)
        formatter = logging.Formatter(options.format, TIME)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(options.verbosity)
        add_log_setting(stream_handler, formatter)
        stream_logger.addHandler(stream_handler)
	logging.root.setLevel(logging.DEBUG)
        if not options.nolog:
            tmp_path = tempfile.gettempdir()
            debug_path = os.path.join(tmp_path, 'pytest_debug_logs')
            if not check_make_dir(debug_path):
                sys.exit(FAILED)
            log_handler = start_log('', debug_path, FORMATS['DEBUG'],
                                    LEVELS['DEBUG'])
            debug_logger.addHandler(log_handler)
            log_empty(command, logger=debug_logger)
        if options.system:
            for system in options.system:
                try:
                    system_file_path = get_systems_path(system)
                    if system_file_path is not None:
                        add_system(parse_system(system_file_path))
                        logging.info('Added system {0}'.format(system))
                    else:
                        raise OptionError('System file does not exist')
                except Exception as e:
                    logging.warning('Could not add system ' + system + '\n' +

                                    str_error(e))
        else:
            logging.warning('No systems were added')
        if not options.nolog and not check_make_dir(options.directory):
            sys.exit(FAILED)
        if name is not None:
            if name.endswith('.py'):
                name = name[:-3]
            options.tests = [parse_test(name, vargs)]
        if name is None:
            log_empty('{0:=^79}'.format(' Running Tests '))
        total_passed = 0
        total_failed = 0
        total_aborted = 0
        for test in options.tests:
            if type(test) is str:
                test_name = 'Scenario ' + test
                test_name_other = test
            else:
                test_name = 'Module ' + test[0]
                test_name_other = test[0]
            if not options.nolog:
                log_handler = start_log(test_name_other, options.directory,
                                        options.format, options.level)
                file_logger.addHandler(log_handler)
                log_empty(command, logger=file_logger)
            log_empty('{0:=^79}'.format(' Running ' + test_name + ' '))
            passed = 0
            failed = 0
            issues = 0
            aborted = 0
            try:
                passed, failed, issues, aborted = run(test, options.debug)
            except OptionError as e:
                logging.log(SKIP, test_name + ' was skipped\n' +
                            str_error(e))
            except Exception as e:
                logging.critical(test_name + ' failed to run\n\n' +
                                 traceback.format_exc())
                Connection.close_all()
            log_empty('{0:=^79}'.format(''))
            log_result(test_name)
            log_empty('{0:=^79}'.format(''))
            log_result('Passed: ' + str(passed))
            log_result('Failed: ' + str(failed))
            log_result('Issues: ' + str(issues))
            log_result('Aborted: ' + str(aborted))
            log_empty('{0:=^79}'.format(''))
            total_passed += passed
            total_failed += failed
            total_aborted += aborted
            if not options.nolog:
                remove_log_setting(log_handler)
                file_logger.removeHandler(log_handler)
                log_handler.close()
        running_time = int(time.time() - SECONDS)
        running_time = str(datetime.timedelta(seconds=running_time))
        log_empty('{0:=^79}'.format(' Running Time: ' + running_time + ' '))
        if name is None:
            log_empty('{0:=^79}'.format(' Finished Running Tests '))
        if not total_failed and not total_aborted:
            result = PASSED
        else:
            result = FAILED
        logging.shutdown()
        sys.exit(result)
    except Exception as e:
        print('Caught unhandled error')
        print(str_error(e))
        shutdown()
        sys.exit(FAILED)
    except KeyboardInterrupt:
        print('')
        print('Caught keyboard interrupt')
        shutdown()
        sys.exit(FAILED)


def shutdown():
    try:
        CURRENT_TEST.cleanup()
    except:
        pass
    print('Closing connections')
    try:
        Connection.close_all()
    except Exception as e:
        print('Could not close connections')
        print(str_error(e))
    logging.shutdown()


def get_options(name, version, *args, **kwargs):
    arguments = ' '.join(args)
    kwargument_list = ['{0}={1}'.format(key, value)
                       for key, value in kwargs.items()]
    kwarguments = ' '.join(kwargument_list)
    extra = arguments + ' ' + kwarguments
    usage = 'Usage: %prog [OPTION]... ' + extra
    usage = usage.strip()
    parser = OptionParser(usage=usage, version=version)
    if name is None:
        parser.add_option('-t', '--test', action='callback',
                          callback=add_test, type='string',
                          help='test to be run')
        parser.add_option('-c', '--scenario', action='callback',
                          callback=add_test, type='string',
                          help='scenario file to be run')
    parser.add_option('-s', '--system',
                      action='append', dest='system',
                      help='system required by test')
    parser.add_option('-d', '--directory',
                      action='store', dest='directory',
                      help='specifies log directory')
    parser.add_option('-l', '--level', action='callback', dest='level',
                      callback=store_level, type='string',
                      help='specifies log level  \
                            DEBUG, INFO, WARNING, ERROR, PASS, SKIP, FAIL,\
                            ABORT, CRITICAL')
    parser.add_option('-f', '--format', action='callback', dest='format',
                      callback=store_format, type='string',
                      help='specifies format     \
                            DEBUG, DEFAULT')
    parser.add_option('-v', '--verbose', action='store_true',
                      dest='verbose', default=False,
                      help='outputs on the command line')
    parser.add_option('--nolog', action='store_true', dest='nolog',
                      default=False, help='inhibits log creation')
    parser.add_option('--debug', action='store_true', dest='debug',
                      default=False, help=SUPPRESS_HELP)
    try:
        options, vargs = parser.parse_args()
    except Exception as e:
        parser.print_help()
        print('')
        print(str_error(e))
        sys.exit(FAILED)
    if name is None and not hasattr(options, 'tests'):
        parser.print_help()
        print('')
        print('OptionError: At least one test or scenario required')
        sys.exit(FAILED)
    if options.format is None:
        options.format = FORMATS[FORMAT]
    if options.level is None:
        options.level = LEVELS[LEVEL]
        print("setting optins.lvel to " + str(LEVEL))
    if options.verbose:
        options.verbosity = options.level
    else:
        options.verbosity = LEVELS[STREAM]
    if options.directory is None:
        options.directory = os.path.join(os.path.expanduser('~'), 'pytest_logs')
    return (options, vargs)


def start_log(name, directory, format, level):
    name = name.replace(os.sep, '.')
    if name:
        log_name = '{0}_{1}.log'.format(name, dt.now().strftime(TIME_FILE))
    else:
        log_name = dt.now().strftime(TIME_FILE) + '.log'
    log_file = os.path.join(directory, log_name)
    log_handler = logging.FileHandler(log_file)
    log_formatter = logging.Formatter(format, TIME)
    log_handler.setLevel(level)
    add_log_setting(log_handler, log_formatter)
    return log_handler


def parse_system(system, log=True):
    tree = ElementTree.parse(system)
    root = tree.getroot()
    system_name = root.tag
    VNC_address = root.get('VNC_address')
    VNC_password = root.get('VNC_password')
    VNC_prompt = root.get('VNC_prompt')
    if (VNC_address is not None and
        VNC_password is not None and
        VNC_prompt is not None):
        VNC = (VNC_address, VNC_password, VNC_prompt)
    else:
        VNC = None
    system_instance = System(system_name, VNC)
    for child in list(root):
        name = child.get('name')
        try:
            address = socket.gethostbyname(name)
        except Exception:
            address = None
        type = child.tag
        if name is None:
            if log:
                logging.warning('Subsystem {0} requires name. '.format(type) +
                                'Not adding {0}...'.format(type))
            continue
        if address is None:
            if log:
                logging.warning('Could not process IP address ' +
                                'for {0}. '.format(name) +
                                'Not adding {0}...'.format(type))
            continue
        subsystem_instance = Subsystem(name, address, type)
        system_instance.subsystems[type] = subsystem_instance
        for grandchild in list(child):
            key = grandchild.tag.lower()
            if key == 'user':
                try:
                    name = grandchild.find('name').text
                except AttributeError:
                    if log:
                        logging.warning('User requires name. ' +
                                        'Not adding user in ' +
                                        subsystem_instance.type + '...')
                    continue
                if name is None:
                    name = ''
                try:
                    password = grandchild.find('password').text
                    prompt = grandchild.find('prompt').text
                    type = grandchild.find('type').text
                except AttributeError:
                    if log:
                        logging.warning('Could not process user ' + name +
                                        ' in ' + subsystem_instance.type)
                    continue
                if password is None:
                    password = ''
                if prompt is None:
                    prompt = ''
                if type is None:
                    type = ''
                user = User(name, password, prompt, type)
                subsystem_instance.users[name] = user
            else:
                try:
                    component = process_component(grandchild, log=log)
                except OptionError as e:
                    if log:
                        logging.warning(str(e) + '. Not adding component ' +
                                        grandchild.tag + ' in ' +
                                        subsystem_instance.type + '...')
                    continue
                key += 's'
                try:
                    type = component.type
                    path = os.path.join(PYTEST_DATA_PATH, key, type)
                    f = open(path, 'r')
                    lines = [line.strip() for line in f.readlines()
                             if line.strip() and not line.startswith('#')]
                    f.close()
                    values = {}
                    for line in lines:
                        try:
                            k, value = line.split(':', 1)
                            k = k.strip()
                            value = value.strip()
                            if k and value:
                                values[k] = value
                        except ValueError:
                            continue
                    component.values = values
                except Exception:
                    pass
                try:
                    getattr(subsystem_instance, key)[component.name] = component
                except AttributeError:
                    setattr(subsystem_instance, key, {component.name:component})
    return system_instance


def process_component(component, log=True):
    name = ''
    found = False
    dictionary = {}
    subcomponents = {}
    for child in list(component):
        key = child.tag.lower()
        if key == 'name':
            name = child.text
            if name is None:
                name = ''
            found = True
        elif list(child):
            try:
                subcomponent = process_component(child, log=log)
            except OptionError as e:
                if log:
                    logging.warning(str(e) + '. Not adding component ' +
                                    child.tag + ' in ' + name + '...')
                continue
            key += 's'
            try:
                subcomponents[key][subcomponent.name] = subcomponent
            except KeyError:
                subcomponents[key] = {subcomponent.name:subcomponent}
        else:
            value = child.text
            if value is None:
                value = ''
            dictionary[key] = value
    if not found:
        raise OptionError('Component ' + component.tag + ' requires name')
    component = Component(name, **dictionary)
    for key, value in subcomponents.items():
        setattr(component, key, value)
    return component


def run(test, debug):
    global CURRENT_TEST
    passed = 0
    failed = 0
    issues = 0
    aborted = 0
    if type(test) is str:
        file_path = get_file_path(test)
        if file_path is None:
            raise OptionError('Scenario file ' + test + ' does not exist')
        f = open(file_path)
        tests = f.readlines()
        f.close()
        for t in tests:
            if not t.startswith('#'):
                test_list = t.split()
                try:
                    module = test_list[0]
                    values = test_list[1:]
                    result = run(parse_test(module, values), debug)
                    passed += result[0]
                    failed += result[1]
                    issues += result[2]
                    aborted += result[3]
                except IndexError:
                    continue
                except Exception as e:
                    logging.log(SKIP, 'Module {0} in {1} '.format(module, test) +
                                'was skipped\n\n' + traceback.format_exc())
    else:
        module_name = test[0]
        try:
            module = import_module(module_name)
        except (ImportError, AttributeError) as e:
            raise OptionError(str(e))
        class_names = test[1]
        method_names = test[2]
        args = test[3]
        kwargs = test[4]
        if not class_names:
            try:
                tests = module.TESTS
            except AttributeError:
                tests = []
            inspect_list = []
            for name in tests:
                try:
                    attribute = getattr(module, name)
                except Exception:
                    logging.warning('Module {0} does not '.format(module) +
                                    'contain test {0}'.format(name))
                inspect_list.append((name, attribute))
            if not inspect_list:
                inspect_list = inspect.getmembers(module)
            class_names = [name for name, attribute in inspect_list
                           if (inspect.isclass(attribute) and
                               issubclass(attribute, Test) and
                               attribute is not Test)]
            number = len(class_names)
            method_names = []
            args = []
            kwargs = []
            for i in range(number):
                method_names.append([])
                args.append([[]])
                kwargs.append([{}])
        for i in range(len(class_names)):
            test_aborted = 0
            class_name = class_names[i]
            class_method_names = method_names[i]
            class_args = args[i][0]
            class_kwargs = kwargs[i][0]
            class_description = get_description(class_name,
                                                class_args, class_kwargs)
            description = [class_description]
            message = ' Running Test ' + class_description + ' '
            log_empty('{0:*^79}'.format(' Running Test ' +
                                        class_description + ' '),
                      level=logging.INFO)
            try:
                class_ = getattr(module, class_name)
                if not issubclass(class_, Test) and class_ is not Test:
                    logging.log(SKIP, 'Test {0} in '.format(class_description) +
                                module_name + ' was skipped\n' +
                                'TestError: Not a subclass of Test')
                    continue
                try:
                    if class_.__dict__['notest']:
                        logging.log(SKIP,
                                    'Test {0} in '. format(class_description) +
                                    module_name + ' was skipped\n' +
                                    "TestError: Flag 'notest' was set")
                        continue
                except KeyError:
                    pass
                class_instance = class_(*class_args, **class_kwargs)
                CURRENT_TEST = class_instance
            except Exception:
                logging.log(SKIP, 'Test {0} in '.format(class_description) +
                            module_name + ' was skipped\n\n' +
                            traceback.format_exc())
                Connection.close_all()
                continue
            if not class_method_names:
                class_method_names = class_.TESTCASES
            for j in range(len(class_method_names)):
                if class_instance.stop:
                    break
                class_instance.current_failed_count = 0
                class_instance.current_passed_count = 0
                class_instance.current_issue_count = 0
                class_method_name = class_method_names[j]
                try:
                    method_args = args[i][j+1]
                    method_kwargs = kwargs[i][j+1]
                except IndexError:
                    method_args = []
                    method_kwargs = {}
                method_description = get_description(class_method_name,
                                                     method_args,
                                                     method_kwargs)
                description.append(method_description)
                log_empty('{0:-^79}'.format(' Running Testcase ' +
                                            method_description + ' '),
                          level=logging.INFO)
                try:
                    method = getattr(class_instance, class_method_name)
                except AttributeError:
                    logging.log(SKIP, 'Testcase ' + method_description +
                                ' in ' + class_description + ' was skipped\n' +
                                'OptionError: Does not exist')
                    log_empty('{0:-^79}'.format(' Finished Running Testcase ' +
                                                method_description + ' '),
                              level=logging.INFO)
                    continue
                if not inspect.ismethod(method):
                    logging.log(SKIP, 'Testcase ' + method_description +
                                ' in ' + class_description + ' was skipped\n' +
                                'OptionError: Not a method')
                    log_empty('{0:-^79}'.format(' Finished Running Testcase ' +
                                                method_description + ' '),
                              level=logging.INFO)
                    continue
                try:
                    if debug:
                        pdb.runcall(method, *method_args, **method_kwargs)
                    else:
                        method(*method_args, **method_kwargs)
                except StopTestcase:
                    pass
                except TestError:
                    aborted += 1
                    test_aborted += 1
                except Exception:
                    aborted += 1
                    test_aborted += 1
                    logging.log(ABORT, 'Testcase ' + method_description +
                                       ' in ' + class_description +
                                       ' was aborted\n\n' +
                                       traceback.format_exc())
                try:
                    logging.info('Running testcase cleanup routine')
                    class_instance.testcase_cleanup()
                    logging.info('Finished running testcase cleanup routine')
                except Exception:
                    logging.warning('Could not cleanup after testcase\n\n' +
                                    traceback.format_exc())
                log_empty('{0:-^79}'.format(' Finished Running Testcase ' +
                                            method_description + ' '),
                          level=logging.INFO)
            failed += class_instance.failed_count
            passed += class_instance.passed_count
            issues += class_instance.issue_count
            try:
                logging.info('Running cleanup routine')
                class_instance.cleanup()
                logging.info('Finished running cleanup routine')
            except Exception:
                logging.warning('Could not cleanup\n\n' +
                                traceback.format_exc())
            Connection.close_all()
            log_empty('{0:*^79}'.format(''), level=logging.INFO)
            log_result(' '.join(description), level=logging.INFO)
            log_empty('{0:*^79}'.format(''), level=logging.INFO)
            log_result('Passed: ' + str(class_instance.passed_count),
                       level=logging.INFO)
            log_result('Failed: ' + str(class_instance.failed_count),
                       level=logging.INFO)
            log_result('Issues: ' + str(class_instance.issue_count),
                       level=logging.INFO)
            log_result('Aborted: ' + str(test_aborted), level=logging.INFO)
            log_empty('{0:*^79}'.format(''), level=logging.INFO)
    return (passed, failed, issues, aborted)


def get_description(name, args, kwargs):
    strings = []
    for arg in args:
        strings.append('"{0}"'.format(arg))
    for key, value in kwargs.items():
        strings.append('{0}="{1}"'.format(key, value))
    string = ', '.join(strings)
    string = '{0}({1})'.format(name, string)
    return string


def add_test(option, opt_str, value, parser):
    if not hasattr(parser.values, 'tests'):
        parser.values.tests = []
    if opt_str == '-c' or opt_str == '--scenario':
        parser.values.tests.append(value.replace('.', os.sep))
    else:
        values = []
        for arg in parser.rargs:
            if arg[:2] == '--' and len(arg) > 2:
                break
            if arg[:1] == '-' and len(arg) > 1 and not floatable(arg):
                break
            values.append(arg)
        del parser.rargs[:len(values)]
        test = parse_test(value, values)
        parser.values.tests.append(test)


def store_format(option, opt_str, value, parser):
    if value.upper() not in list(FORMATS):
        raise OptionError('Invalid format')
    else:
        parser.values.format = FORMATS[value.upper()]


def store_level(option, opt_str, value, parser):
    if value.upper() not in list(LEVELS):
        raise OptionError('Invalid level')
    else:
        parser.values.level = LEVELS[value.upper()]


def parse_test(module, values):
    current_class = None
    classes = []
    methods = []
    args = []
    kwargs = []
    for value in values:
        if not value.startswith('/') and not value.startswith(':'):
            current_class = value
            classes.append(value)
            methods.append([])
            args.append([[]])
            kwargs.append([{}])
        else:
            if current_class is None:
                continue
            arg = value[1:]
            if value.startswith('/'):
                methods[-1].append(arg)
                args[-1].append([])
                kwargs[-1].append({})
            else:
                try:
                    key, word = arg.split('=', 1)
                    kwargs[-1][-1][key] = word
                except ValueError:
                    args[-1][-1].append(arg)
    return (module, classes, methods, args, kwargs)
