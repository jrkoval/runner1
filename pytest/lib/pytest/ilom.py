"""
This module provides ilom functionality and methods.
"""

import re
import time
import logging
from pexpect import TIMEOUT as TimeoutError
from pytest.globals import log_empty, debug_logger, file_logger, sleep
from pytest.connections import Console, SSH


ESCAPE = '#.'
TIMESTEP = 15
TIMEOUT = 600
STOP_TIMEOUT = 900
START_TIMEOUT = 3600
STATUS_LIST = ['Starting', 'Powered On', 'HV started', 'OpenBoot initializing',
               'OpenBoot Running', 'OpenBoot Primary Boot Loader',
               'OpenBoot Running OS Boot', 'Solaris running']


class ILOMError(Exception):
    """Raised when the connection encounters an error with ILOM.
    """


class Property(object):
    def __init__(self, name, description, values=None, role=None):
        self.name = name
        self.description = description
        if values is None:
            self.values = []
        else:
            self.values = values
        self.role = role

    def __str__(self):
        string = '{0} : {1}'.format(self.name, self.description)
        if self.role is not None:
            values = ', '.join(self.values)
            values = 'Possible values = ' + values
            string += '\n' + '{0} : {1}'.format(self.name, values)
            role = 'User role required for set = ' + self.role
            string += '\n' + '{0} : {1}'.format(self.name, role)
        return string


class HelpMessage(object):
    """
    """

    def __init__(self, name, description, targets, properties, order):
        self.name = name
        self.description = description
        self.targets = targets
        self.properties = properties
        self.order = order

    def __str__(self):
        string = ' ' + self.name + '\n'
        targets = ['    Targets:']
        keys = self.targets.keys()
        keys.sort()
        values = ['{0} : {1}'.format(key, self.targets[key]) for key in keys]
        targets.extend(values)
        string += '\n        '.join(targets) + '\n\n'
        properties = ['    Properties:']
        keys = self.order
        values = []
        values = [str(self.properties[key]).replace('\n', '\n        ') + '\n'
                  for key in keys]

        properties.extend(values)
        string += '\n        '.join(properties)
        string = string.rstrip()
        return string


class Target(object):
    """
    """

    def __init__(self, name, targets, properties, commands, order):
        self.name = name
        self.targets = targets
        self.properties = properties
        self.commands = commands
        self.order = order

    def __str__(self):
        string = ' ' + self.name + '\n'
        targets = ['    Targets:']
        targets.extend(self.targets)
        string += '\n        '.join(targets) + '\n\n'
        properties = ['    Properties:']
        keys = self.order
        values = ['{0} = {1}'.format(key, self.properties[key]) for key in keys]
        properties.extend(values)
        string += '\n        '.join(properties)
        if self.commands:
            string += '\n\n'
            commands = ['    Commands:']
            commands.extend(self.commands)
            string += '\n        '.join(commands)
        return string


class Log(list):
    """
    """

    def __init__(self, description, *args, **kwargs):
        super(Log, self).__init__(*args, **kwargs)
        self.description = description

    def __str__(self):
        string = self.description
        for element in self:
            string += '\n' + str(element)
        return string.strip()


class Entry(dict):
    """
    """

    def __init__(self, description, *args, **kwargs):
        super(Entry, self).__init__(*args, **kwargs)
        self.description = description

    def __str__(self):
        return self.description


def help(self, target, *property):
    """
    """
    def get_properties(lines):
        properties = {}
        order = []
        for line in lines:
            try:
                name, description = line.split(' : ', 1)
            except ValueError:
                continue
            if name == target:
                raise ILOMError('No such target ' + target)
            try:
                property_object = properties[name]
            except KeyError:
                if 'Property not found' in description:
                    continue
                properties[name] = Property(name, description)
                order.append(name)
                continue
            try:
                first, second = description.split(' = ')
            except ValueError:
                continue
            if 'Possible values' in first:
                property_values = second.split(', ')
                property_object.values.extend(property_values)
            elif 'User role required' in first:
                role = second
                property_object.role = role
            else:
                raise ILOMError('Unknown help message description: ' +
                                description)
        return (properties, order)
    properties = ' '.join(property)
    command = ' '.join(['help -format nowrap ' + target, properties]).strip()
    output = self.sendcmd(command)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if output.startswith('help: '):
        raise ILOMError(output[6:].strip())
    try:
        properties_index = lines.index('Properties:')
    except ValueError:
        properties_index = None
    try:
        targets_index = lines.index('Targets:')
    except ValueError:
        targets_index = None
    if targets_index is None:
        if properties_index is None:
            start = 0
        else:
            start = properties_index + 1
        values = lines[start:]
        properties, order = get_properties(values)
        if len(property) == 1:
            try:
                return properties[property[0]]
            except KeyError:
                raise ILOMError('Property not found')
        else:
            return properties
    else:
        line = lines[0]
        try:
            name, description = line.split(' : ', 1)
        except ValueError:
            raise ILOMError('Unable to parse help message')
        targets = {}
        values = lines[targets_index + 1 : properties_index]
        for line in values:
            try:
                target_name, target_description = line.split(' : ', 1)
            except ValueError:
                continue
            targets[target_name] = target_description
        values = lines[properties_index + 1 :]
        properties, order = get_properties(values)
        return HelpMessage(name, description, targets, properties, order)


def reset(self, sp='SP', login=True):
    logging.info('Resetting ' + sp)
    self.sendline('reset -script /' + sp)
    i = self.expect(['reset: ', 'Performing reset on'])
    if i == 0:
        output = self.sync(debug=False).strip()
        raise ILOMError(output)
    for connection in self.current[0].connections[:]:
        if connection.origin and connection.origin[0][1].type == sp:
            if connection in SSH.CONNECTIONS:
                connection.close()
            self.current[0].connections.remove(connection)
        elif connection.current[1].type == sp:
            if connection in SSH.CONNECTIONS:
                connection.close()
            self.current[0].connections.remove(connection)
    if self.__class__ is not Console:
        log_empty('No reset output available because SSH connection was used',
                  level=logging.INFO, logger=[debug_logger, file_logger])
        logging.info('Finished resetting ' + sp)
        return None
    login_list = ['(?i)Login:', TimeoutError]
    lines = self.sync(login_list, timeout=TIMEOUT, debug=False).splitlines()[1:]
    output = '\n'.join(lines).strip()
    if output.startswith(self.prompt):
        output = output[len(self.prompt):].strip()
    log_empty(output, level=logging.INFO, logger=[debug_logger, file_logger])
    if self.match_index == 1:
        raise ILOMError('Timed out in resetting ' + sp)
    if login:
        self.login()
    logging.info('Finished resetting ' + sp)
    return output


def set(self, target, timeout=-1, log=True, **property_value):
    """Sets the value of a property associated with a target.
    """
    property_value_list = ['{0}="{1}"'.format(key, value)
                           for key, value in property_value.items()]
    properties = ' '.join(property_value_list)
    command = 'set -script {0} '.format(target) + properties
    result = self.sendcmd(command, timeout=timeout)
    results = result.splitlines()
    results = [result for result in results
               if result.startswith('Set') or result.startswith('set:')]
    if results[-1].startswith('Set'):
        changed = True
        if log:
            logging.info('Set {0} '.format(target) + properties)
    else:
        changed = False
        i = len(results) - 1
        if i > 0 and log:
            logging.info('Set {0} '.format(target) +
                         ' '.join(property_value_list[:i]))
        logging.warning('Could not set {0} '.format(target) +
                        ' '.join(property_value_list[i:]))
    return changed


def show(self, target, *property, **property_value):
    """
    """
    defaults = {'debug':True, 'log':False, 'timeout':-1, 'level':1}
    defaults.update(property_value)
    debug = defaults['debug']
    log = defaults['log']
    timeout = defaults['timeout']
    if timeout == -1 and self.timeout < TIMEOUT:
        timeout = TIMEOUT
    level = defaults['level']
    property_value.pop('debug', None)
    property_value.pop('log', None)
    property_value.pop('timeout', None)
    property_value.pop('level', None)
    properties = ' '.join(property)
    property_value_list = ['{0}=="{1}"'.format(key, value)
                           for key, value in property_value.items()]
    property_values = ' '.join(property_value_list)
    values = ' '.join([properties, property_values]).strip()
    command = ' '.join(['show -format nowrap -script -l', str(level),
                        target, values]).strip()
    output = self.sendcmd(command, timeout=timeout, log=log, debug=debug)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if output.startswith('show: '):
        raise ILOMError(output[6:].strip())
    if output.strip().startswith('Unexpected filter type'):
        raise ILOMError('Unexpected filter type')
    # The target could be a log
    strings = target.split('/')
    strings.reverse()
    log = False
    for string in strings:
        if string:
            log = string.lower() == 'list' or string.lower() == 'open_problems'
            break
    if log:
        try:
            keys_line = lines[1]
        except IndexError:
            raise ILOMError('Unable to parse log')
        keys = [key.strip() for key in keys_line.split('  ') if key.strip()]
        keys_number = len(keys)
        unfiltered_lines = [line
                            for line in output.splitlines() if line.strip()]
        index = 0
        for i in range(len(unfiltered_lines)):
            if unfiltered_lines[i].startswith('-'):
                index = i
                break
        entry_lines = unfiltered_lines[index + 1 :]
        start = 0
        end = 1
        entries = Log('\n'.join(unfiltered_lines[: index + 1]))
        while start < len(entry_lines):
            # There will always be at least one character
            while end < len(entry_lines) and entry_lines[end][0] == ' ':
                end += 1
            # ILOM has an inconsisteny when it comes to the date. There is an
            # extra space sometimes. We should find it first and then split the
            # string by two spaces.
            pattern = '([A-z]{3}) ([A-z]{3}) (\s|\d)\d \d\d:\d\d:\d\d (\d{4})'
            line = entry_lines[start]
            regex = re.compile(pattern)
            result = regex.search(line)
            if result is not None:
                values = [value.strip()
                          for value in line[:result.start()].split('  ')
                          if value.strip()]
                values.append(result.group())
                values.extend([value.strip()
                               for value in line[result.end():].split('  ')
                               if value.strip()])
            else:
                values = [value.strip()
                          for value in entry_lines[start].split('  ')
                          if value.strip()]
            if len(values) != keys_number:
                start = end
                end += 1
                continue
            entry = Entry('\n'.join(entry_lines[start:end]))
            for i in range(keys_number):
                entry[keys[i]] = values[i]
            messages = []
            i = start + 1
            while i < end:
                messages.append(entry_lines[i].strip())
                i += 1
            entry['messages'] = messages
            entries.append(entry)
            start = end
            end += 1
        return entries
    # Usually, 'Properties:' is always displayed if the target is not a log but
    # there is a bug in ILOM where it might not be displayed. This only occurs
    # when level is 1 and when an invalid property is specified followed by a
    # valid one. In this case, every line is a property. This bug is not going
    # to be handled because there are other targets that are more important.
    try:
        lines.index('Properties:')
    except ValueError:
        return output
    target_objects = []
    start = 0
    end = 1
    while start < len(lines):
        while end < len(lines) and not lines[end].startswith('/'):
            end += 1
        name = lines[start]
        sublines = lines[start:end]
        try:
            properties_index = sublines.index('Properties:')
        except ValueError:
            properties_index = None
        try:
            commands_index = sublines.index('Commands:')
            commands = sublines[commands_index + 1 :]
        except ValueError:
            commands_index = None
            commands = []
        try:
            targets_index = sublines.index('Targets:')
            if properties_index is not None:
                targets = sublines[targets_index + 1 : properties_index]
            else:
                targets = sublines[targets_index + 1 : commands_index]
        except ValueError:
            targets = []
        properties = {}
        order = []
        if properties_index is not None:
            values = sublines[properties_index + 1 : commands_index]
            for line in values:
                try:
                    key, value = line.split(' = ', 1)
                    properties[key] = value
                    order.append(key)
                except ValueError:
                    pass
        target_object = Target(name, targets, properties, commands, order)
        target_objects.append(target_object)
        start = end
        end += 1
    # There will always be at least one target at this point
    if level == 1:
        # Just in case the connection is closed prematurely
        if len(target_objects) == 1:
            if len(property) == 1:
                return target_objects[0].properties[property[0]]
            elif property:
                return target_objects[0].properties
            else:
                return target_objects[0]
        else:
            return None
    else:
        return target_objects


def start_console(self, host='HOST', log=True):
    """
    """
    if not hasattr(self, 'in_console'):
        host = host.upper()
        command = 'start -force -script /' + host + '/console'
        console_list = [ESCAPE, 'start:']
        self.sendcmd(command, prompt=console_list, debug=False)
        if self.match_index == 0:
            self.in_console = None
            if log:
                logging.info('Host console started')
        else:
            raise ILOMError('Could not start console')
    elif log:
        logging.info('Connection already in console')


def start_system(self, system='System', host='HOST', user=None, boot=True,
                 disk=None, stop=True, force=True, console=False, timeout=-1,
                 boot_timeout=-1, verbose=True):
    """
    """
    if timeout == -1:
        if self.timeout < START_TIMEOUT:
            timeout = START_TIMEOUT
        else:
            timeout = self.timeout
    status = self.show('/' + host, 'status', debug=False)
    if status != 'Powered Off' and status not in STATUS_LIST:
        if stop:
            self.stop_system(system=system, force=force)
            status = self.show('/' + host, 'status', debug=False)
        else:
            raise ILOMError(system + ' is in state ' + status)
    bootmode = '/' + host + '/bootmode'
    if status == 'Powered Off':
        self.set(bootmode, script='setenv auto-boot? false', log=False)
        result = self.sendcmd('start -script /' + system)
        if not result.startswith('Starting'):
            raise ILOMError('Could not start ' + system + '\n' + result)
        if verbose:
            logging.info('Starting ' + system + '. This might take a while...')
    elif status in STATUS_LIST:
        if verbose:
            logging.info(system + ' already started. This might take a while...')
    else:
        raise ILOMError(system + ' is in state ' + status)
    self.start_console(host=host, log=verbose)
    self.switch(user='openboot')
    self.sendline()
    start_list = [self.prompt, '(?i)Console Login:', TimeoutError]
    start_output = self.sync(start_list, timeout=timeout, debug=False).strip()
    if not start_output:
        start_output = 'No start output available'
        if self.match_index != 2:
            start_output += ' because ' + system + ' was already up'
    log_empty(start_output, level=logging.INFO,
              logger=[debug_logger, file_logger])
    boot_output = None
    if self.match_index == 2:
        raise ILOMError('Timed out in starting ' + system)
    if verbose:
        logging.info('Finished starting ' + system)
    if self.match_index == 1:
        if not boot or (boot and disk is not None):
            if verbose:
                logging.info('Switching to OpenBoot')
            self.stop_console(log=False)
            domain_control = '/' + host + '/domain/control'
            control_properties = {'auto-boot':'disabled'}
            self.set(domain_control, log=False, **control_properties)
            self.sendcmd('reset -force -script ' + domain_control, debug=False)
            #self.set(bootmode, script='setenv auto-boot? false', log=False)
            #self.set('/' + host, send_break_action='break', log=False)
            self.start_console(host=host, log=False)
            #self.sendline()
            #i = self.expect_exact(['c)ontinue, s)ync, r)eset?', TimeoutError])
            #if i == 1:
            #    raise ILOMError('Timed out in break')
            #self.sendline('r')
            self.sync(start_list, timeout=TIMEOUT, debug=False)
            if self.match_index == 1:
                raise ILOMError('Returned to login prompt')
            elif self.match_index == 2:
                raise ILOMError('Timed out in resetting ' + system)
            self.switch(user='openboot', nopage=True)
            if verbose:
                logging.info('Finished switching to OpenBoot')
        if boot and disk is None:
            if verbose:
                logging.info('Starting to boot. This might take a while...')
            boot_output = ('No boot output available because ' + system +
                           ' was started with auto-boot?=true')
            log_empty(boot_output, level=logging.INFO,
                      logger=[debug_logger, file_logger])
            if verbose:
                logging.info('Finished booting')
    if self.match_index == 0:
        if boot:
            boot_output = self.boot(disk=disk, timeout=boot_timeout)
        else:
            self.switch(user='openboot', nopage=True)
    if boot:
        if user is not None:
            self.switch(subsystem=host, user=user)
            self.login(log=verbose)
    if not console:
        self.stop_console(log=verbose)
    errors = []
    for line in start_output.splitlines():
        if 'ERROR:' in line:
            errors.append(line)
    return (start_output, boot_output, errors)


def stop_system(self, system='System', force=False, timeout=-1):
    """
    """
    if timeout == -1 and self.timeout < STOP_TIMEOUT:
        timeout = STOP_TIMEOUT
    elif timeout == -1:
        timeout = self.timeout
    if force:
        command = 'stop -force -script /' + system
    else:
        command = 'stop -script /' + system
    result = self.sendcmd(command)
    if (result.startswith('Stopping')
        or 'Target shutdown in progress' in result):
        logging.info('Stopping ' + system)
        timed_out = True
        end_time = time.time() + timeout
        while True:
            remaining = end_time - time.time()
            if remaining <= 0:
                break
            sleep(TIMESTEP)
            result = self.sendcmd(command, debug=False)
            if result.startswith('stop:'):
                if result.startswith('stop: Target already stopped'):
                    timed_out = False
                    logging.info('Finished stopping ' + system)
                    break
                elif 'Target shutdown in progress' in result:
                    continue
                else:
                    raise ILOMError('Could not stop ' + system + '\n' + result)
        """
        for i in range(0, timeout, TIMESTEP):
            time.sleep(TIMESTEP)
            result = self.sendcmd(command, debug=False)
            if result.startswith('stop:'):
                if result.startswith('stop: Target already stopped'):
                    timed_out = False
                    logging.info('Finished stopping ' + system)
                    break
                elif 'Target shutdown in progress' in result:
                    continue
                else:
                    raise ILOMError('Could not stop ' + system + '\n' + result)
        """
        if timed_out:
            raise ILOMError('Timed out in stopping ' + system)
    elif result.startswith('stop: Target already stopped'):
        logging.info(system + ' already stopped')
    else:
        raise ILOMError('Could not stop ' + system + '\n' + result)
