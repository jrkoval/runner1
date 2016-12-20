"""
This module contains the classes to set up your environment.
"""

import types
import inspect
import logging
import pytest
from pexpect import TIMEOUT as TimeoutError
from pytest import connections
from pytest.connections import Connection, ConnectionError, SSH, Console, BUI
from pytest.globals import import_module, log_empty, debug_logger, file_logger
from pytest.openboot import USER, ADDRESS, PASSWORD, PROMPT


SYSTEMS = []


TIMEOUT = 600
VNC_TIMEOUT = 300


class EnvironmentError(Exception):
    """Raised when the environment is accessed incorrectly.
    """


class System(object):
    """System under test.

    :ivar str name: The name of the system.
    :ivar dict subsystems: The subsystems of the system. The keys are subsystem
        types.
    :param str name: The name of the system.
    """

    def __init__(self, name, VNC=None, model=None):
        self.name = name
        self.VNC = VNC
        self.model = model
        self.subsystems = {}
        self.connections = []

    def get_connection(self, type, subsystem, user, **kwargs):
        """Gets a connection to the subsystem as the specified user.

        :param str type: The name of the subclass of
            :class:`~pytest.connections.Connection`.
        :param str user: The user for the connection.
        :param str subsystem: The subsystem for the connection.
        :param kwargs: The keyword arguments of :class:`~pexpect.spawn`.
        :returns: The connection.
        :rtype: Connection
        :raises: EnvironmentError
        """
        try:
            class_ = getattr(connections, type)
            if class_ is Connection or class_ is ConnectionError or not inspect.isclass(class_):
                raise ConnectionError
            subsystem = self.subsystems[subsystem]
        except ConnectionError:
            raise EnvironmentError('Invalid use of the class Connection')
        except TypeError:
            raise EnvironmentError('No such connection class')
        except KeyError:
            raise EnvironmentError('No such subsystem')
        try:
            user = subsystem.users[user]
        except KeyError:
            raise EnvironmentError('No such user')
        name = '{0}@{1}'.format(user.name, subsystem.name)
        if class_ is BUI:
            connection = class_(user.name, subsystem.address, user.password,
                                name, **kwargs)
            set(connection, 'bui')
        else:
            address = subsystem.address
            if class_ is Console:
                address = subsystem.name
            connection = class_(user.name, address, user.password,
                                user.prompt, name, **kwargs)
            connection.origin = []
            connection.current = (self, subsystem, user)
            method = types.MethodType(switch, connection)
            setattr(connection, 'switch', method)
            set(connection, user.type)
        if class_ is SSH:
            self.connections.append(connection)
        return connection

    def off(self, console=None, log=True, timeout=TIMEOUT):
        """Powers off a system. This is only valid if the system is setup
        correctly on the network. Closes all SSH connections to this system.
        """
        self._power(console=console, log=log, timeout=timeout)

    def on(self, console=None, log=True, timeout=TIMEOUT):
        """Powers on a system. This is only valid if the system is setup
        correctly on the network.
        """
        self._power(console=console, log=log, timeout=timeout)

    def cycle(self, console=None, log=True, timeout=TIMEOUT):
        """Power cycles a system. This is only valid if the system is setup
        correctly on the network. Closes all SSH connections to this system.
        """
        self._power(console=console, log=log, timeout=timeout)

    def _power(self, console=None, log=True, timeout=TIMEOUT):
        stack = inspect.stack()
        try:
            command = stack[1][3]
        except IndexError:
            raise EnvironmentError('Invalid command')
        if command != 'off' and command != 'on' and command != 'cycle':
            raise EnvironmentError('Invalid command')
        if self.VNC is None:
            raise EnvironmentError('VNC is not configured for this system')
        else:
            logging.info('Starting VNC ac ' + command)
            try:
                VNC_address, VNC_password, VNC_prompt = self.VNC
            except (ValueError, TypeError):
                raise EnvironmentError('VNC is not configured correctly')
            name = self.name + '@VNC'
            VNC = SSH(self.name, VNC_address, VNC_password, VNC_prompt, name,
                      log=log, timeout=VNC_TIMEOUT)
        if command == 'off' or command == 'cycle':
            for connection in self.connections[:]:
                connection.close(log=log)
        output = VNC.sendcmd('ac ' + command, timeout=120)
        # TODO: Check for failed command
        VNC.close(log=log)
        logging.info('Finished VNC ac ' + command)
        if console is not None and command != 'off':
            logging.info('Waiting for ac ' + command +
                         '. This might take a while...')
            prompt = ['(?i)Login:', TimeoutError]
            output = console.sync(prompt=prompt, timeout=timeout).strip()
            if not output:
                output = 'No output was available'
            log_empty(output, level=logging.INFO,
                      logger=[debug_logger, file_logger])
            if console.match_index == 1:
                raise EnvironmentError('Timed out in ac ' + command)
            logging.info('Finished waiting for ac ' + command)
        else:
            output = None
        return output

    def __str__(self):
        string = self.name
        if self.VNC is not None:
            VNC_address, VNC_password, VNC_prompt = self.VNC
            string += '\n  ' + 'VNC Address: ' + VNC_address
            string += '\n  ' + 'VNC Password: ' + VNC_password
            string += '\n  ' + 'VNC Prompt: ' + VNC_prompt
        if self.subsystems:
            string += '\n  ' + 'Subsystems:'
            subsystems = self.subsystems.values()
            for subsystem in subsystems:
                string += '\n    ' + str(subsystem).replace('\n', '\n    ')
        return string


class Subsystem(object):
    """Subsystem of a system.

    :ivar str name: The name of the subsystem.
    :ivar str address: The address of the subsystem.
    :ivar str type: The type of the subsystem.
    :ivar dict users: The users of the subsystem. The keys are usernames.
    :param str name: The name of the subsystem.
    :param str address: The address of the subsystem.
    :param str type: The type of the subsystem.
    """

    def __init__(self, name, address, type):
        self.name = name
        self.address = address
        self.type = type
        self.users = {}

    def __str__(self):
        string = self.name
        string += '\n  ' + 'Address: ' + self.address
        string += '\n  ' + 'Type: ' + self.type
        if self.users:
            string += '\n  ' + 'Users:'
            users = self.users.values()
            for user in users:
                string += '\n    ' + str(user).replace('\n', '\n    ')
        return string


class User(object):
    """User of a subsystem.

    :ivar str name: The username.
    :ivar str password: The password of the user.
    :ivar str prompt: The prompt of the user.
    :ivar str type: The type of the user.
    :param str name: The username.
    :param str password: The password of the user.
    :param str prompt: The prompt of the user.
    :param str type: The type of the user.
    """

    def __init__(self, name, password, prompt, type):
        self.name = name
        self.password = password
        self.prompt = prompt
        self.type = type

    def __str__(self):
        string = self.name
        string += '\n  ' + 'Password: ' + self.password
        string += '\n  ' + 'Prompt: ' + self.prompt
        string += '\n  ' + 'Type: ' + self.type
        return string


class Component(object):
    def __init__(self, name, **kwargs):
        self.name = name
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self):
        string = self.name
        dictionaries = {}
        for key, value in self.__dict__.items():
            if key == 'name' or key == 'values':
                pass
            elif type(value) is dict:
                dictionaries[key] = value
            else:
                string += '\n  ' + key.title() + ': ' + str(value)
        try:
            self.values
        except AttributeError:
            pass
        else:
            string += '\n  Values:'
            for key, value in self.values.items():
                string += '\n    ' + key + ': ' + value
        for key, value in dictionaries.items():
            string += '\n  ' + key.title() + ':'
            for v in value.values():
                string += '\n    ' + str(v).replace('\n', '\n    ')
        return string


def add_system(system, index=None):
    """Adds a system to the environment.

    :param System system: The system.
    :param int index: The index the system should be added to.
    """
    if index is None:
        index = len(SYSTEMS)
    SYSTEMS.insert(index, system)


def get_system(index=0):
    """Gets the system.

    :param int index: The index of the system. This is zero-based.
    :returns: The system.
    :rtype: System
    """
    try:
        system = SYSTEMS[index]
    except IndexError:
        raise EnvironmentError('No such system')
    return system


def set(connection, type):
    """Sets a connection to be a certain user type.

    :param Connection connection: The connection.
    :param str type: The type of the user on the connection.
    """
    if isinstance(connection, Connection) or isinstance(connection, BUI):
        try:
            module = import_module('pytest.' + type)
            functions = inspect.getmembers(module, inspect.isfunction)
            for function in functions:
                method = types.MethodType(function[1], connection)
                setattr(connection, function[0], method)
        except AttributeError:
            pass
        except TypeError:
            pass


def unset(connection, type):
    """Unsets a connection from a certain user type.

    :param Connection connection: The connection.
    :param str type: The type of the user on the connection.
    """
    if isinstance(connection, Connection) or isinstance(connection, BUI):
        try:
            module = import_module('pytest.' + type)
            functions = inspect.getmembers(module, inspect.isfunction)
            for function in functions:
                delattr(connection, function[0])
        except AttributeError:
            pass
        except TypeError:
            pass


def switch(self, subsystem=None, user=None, timeout=0, nopage=False):
    """Switches the connection to a certain user or reverts back to the original
    user. This function should only be used after being bound to a connection
    object by system's :func:`~System.get_connection`.

    :param str subsystem: The subsystem.
    :param str user: The username.
    :param int timeout: The timeout value for matching the new prompt.
    """
    if timeout == -1:
        timeout = self.timeout
    if subsystem is None and user is None:
        if not self.origin:
            return
        try:
            unset(self, self.current[2].type)
        except AttributeError:
            pass
        origin = self.origin.pop()
        self.current = origin
        username = origin[2].name
        address = origin[1].address
        password = origin[2].password
        prompt = origin[2].prompt
        type = origin[2].type
    elif user is not None:
        if user.lower() == 'openboot':
            username = USER
            address = ADDRESS
            password = PASSWORD
            prompt = PROMPT
            type = 'openboot'
            subsystem = Subsystem('OpenBoot', address, 'OpenBoot')
            user = User(user, password, prompt, type)
        else:
            if subsystem is None:
                subsystem = self.current[1]
            else:
                try:
                    subsystem = self.current[0].subsystems[subsystem]
                except KeyError:
                    raise EnvironmentError('No such subsystem')
            try:
                user = subsystem.users[user]
            except KeyError:
                raise EnvironmentError('No such user')
            username = user.name
            address = subsystem.address
            password = user.password
            prompt = user.prompt
            type = user.type
        # Need to unset here because the subsystem or user could be invalid
        try:
            unset(self, self.current[2].type)
        except AttributeError:
            pass
        case1 = (self.current[2].type == 'solaris' or
                 self.current[2].type == 'openboot')
        case2 = type == 'solaris' or type == 'openboot'
        if not (case1 and case2 and self.origin):
            self.origin.append(self.current)
        self.current = (self.current[0], subsystem, user)
    else:
        raise EnvironmentError('Invalid arguments')
    self.user = username
    self.address = address
    self.password = password
    self.prompt = prompt
    set(self, type)
    try:
        self.sync(timeout=timeout, debug=False)
    except Exception:
        pass
    if self.user == USER and nopage:
        try:
            self.sendcmd('no-page', debug=False)
        except Exception:
            pass
