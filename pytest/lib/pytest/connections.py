"""
This module provides connection classes.
"""

import time
import logging
import traceback
from pexpect import spawn, EOF
from pexpect import TIMEOUT as TimeoutError
from pytest.globals import log_empty, str_error


TIMEOUT = 10


class ConnectionError(Exception):
    """Raised when the class :class:`Connection` or any of its subclasses
    encounter an error that is not from :class:`~pexpect.spawn`.
    """


class Connection(spawn):
    """Base class that inherits from :class:`~pexpect.spawn`. This class should
    not be used directly.

    :ivar str user: The user for the connection.
    :ivar str address: The address for the connection.
    :ivar str password: The password of the user.
    :ivar str prompt: The prompt of the user.
    :param str command: The connection command to spawn.
    :param str user: The user for the connection.
    :param str address: The address for the connection.
    :param str password: The password of the user.
    :param str prompt: The prompt of the user.
    :param str name: The printable name of the connection.
    :param kwargs: The keyword arguments of :class:`~pexpect.spawn`.
    """
    CONNECTIONS = []

    def __init__(self, command, user, address, password, prompt,
                 name=None, log=True, **kwargs):
        super(Connection, self).__init__(command, **kwargs)
        self.user = user
        self.address = address
        self.password = password
        self.prompt = prompt
        if name is None:
            name = '{0}@{1}'.format(user, address)
        self.name = name
        self.__class__.CONNECTIONS.append(self)
        if type(self) is not Connection:
            Connection.CONNECTIONS.append(self)
            if log:
                logging.info('Started ' + type(self).__name__ +
                             ' connection ' + self.name)
        else:
            if log:
                logging.info('Started connection ' + self.name)

    def close(self, log=True):
        """Closes the connection.
        """
        if not self.closed:
            super(Connection, self).close()
            self.__class__.CONNECTIONS.remove(self)
            if type(self) is not Connection:
                Connection.CONNECTIONS.remove(self)
            if type(self) is SSH:
                try:
                    system = self.current[0]
                    system.connections.remove(self)
                except Exception:
                    pass
            if type(self) is Connection:
                message = 'Closed connection ' + self.name
            else:
                message = ('Closed ' + type(self).__name__ +
                           ' connection ' + self.name)
        else:
            if type(self) is Connection:
                message = 'Connection ' + self.name + ' already closed'
            else:
                message = (type(self).__name__ + ' connection ' +
                           self.name + ' already closed')
        if log:
            logging.info(message)

    @classmethod
    def close_all(cls, log=True):
        """Closes all connections currently open. If this method is called from
        a subclass, then only the connections of the subclass are closed.
        """
        if cls is Connection:
            logging.debug('Closing all connections')
        else:
            logging.debug('Closing all ' + cls.__name__ + ' connections')
        for connection in cls.CONNECTIONS[:]:
            connection.close(log=log)
        if cls is Connection:
            logging.debug('Closed all connections')
        else:
            logging.debug('Closed all ' + cls.__name__ + ' connections')

    def sync(self, prompt=None, index=0, timeout=-1, log=False, debug=True,
             empty=False, after=False):
        """Syncs with the prompt and returns the output.

        :param str prompt: The prompt to expect. If this is `None`, the
            connection's default prompt is used.
        :param int index: The index of the line number of the output that is
            filtered from the start of the output.
        :param int timeout: The timeout value of expecting the prompt.
        :param bool log: The flag for allowing info messages.
        :param bool debug: The flag for allowing debug messages.
        :param bool empty: The flag for logging messages without the prefix.
        :returns: The output until the prompt.
        :rtype: str
        """
        if prompt is None:
            prompt = self.prompt
        self.expect(prompt, timeout=timeout)
        value = self.before.replace('\r', '')
        if after:
            if type(self.after) is str:
                value += self.after.replace('\r', '')
            values = value.split('\n')[index:]
        else:
            values = value.split('\n')[index:-1]
        string = '\n'.join(values)
        if log:
            if empty:
                log_empty(string, level=logging.INFO)
            else:
                logging.info('\n' + string)
        if debug and not log:
            if empty:
                log_empty(string, level=logging.DEBUG)
            else:
                logging.debug('\n' + string)
        return string

    def sendcmd(self, command='', prompt=None, index=1, timeout=-1, log=False,
                output=True, debug=True, after=False):
        """Sends the command and returns the output.

        :param str command: The command to send.
        :param str prompt: The prompt to expect. If this is `None`, the
            connection's default prompt is used.
        :param int index: The index of the line number of the output that is
            filtered from the start of the output.
        :param int timeout: The timeout value of expecting the prompt.
        :param bool log: The flag for allowing info messages.
        :param bool output: The flag for allowing output messages if logging is
            enabled.
        :param bool debug: The flag for allowing debug messages.
        :returns: The output of the command.
        :rtype: str
        """
        self.send(command)
        self.expect_exact(command, timeout=timeout)
        self.sendline()
        if log:
            logging.info(command)
        if debug and not log:
            logging.debug(command)
        string = self.sync(prompt=prompt, index=index, timeout=timeout,
                           log=(log and output), debug=debug, empty=True,
                           after=after)
        return string


class SSH(Connection):
    """SSH connection that inherits from :class:`Connection`.

    :ivar str user: The user for the connection.
    :ivar str address: The address for the connection.
    :ivar str password: The password of the user.
    :ivar str prompt: The prompt of the user.
    :param str user: The user for the connection.
    :param str address: The address for the connection.
    :param str password: The password of the user.
    :param str prompt: The prompt of the user.
    :param str name: The printable name of the connection.
    :param kwargs: The keyword arguments of :class:`~pexpect.spawn`
    :raises: ConnectionError
    """

    CONNECTIONS = []

    def __init__(self, user, address, password, prompt, name=None, log=True,
                 **kwargs):
        command = ('/usr/bin/ssh -o UserKnownHostsFile=/dev/null ' +
                   '-o StrictHostKeyChecking=no ' +
                   '-l {0} {1}'.format(user, address))
        super(SSH, self).__init__(command, user, address, password, prompt,
                                  name=name, log=log, **kwargs)
        if log:
            logging.debug(command)
        login_list = [prompt,
                      '(?i)Are you sure you want to continue connecting',
                      '(?i)Password:',
                      '(?i)Permission denied',
                      '(?i)Connection closed by remote host',
                      '(?i)Connection refused',
                      '(?i)Maximum number of sessions exhausted',
                      '(?i)Could not resolve hostname',
                      '(?i)Connection timed out',
                      TimeoutError,
                      EOF]
        i = self.expect(login_list)
        if i == 1:
            if log:
                logging.debug('Are you sure you want to continue connecting?')
            self.sendline('yes')
            if log:
                logging.debug('yes')
            i = self.expect(login_list)
        if i == 2:
            if log:
                logging.debug('Password:')
            self.sendline(password)
            if log:
                logging.debug(password)
            i = self.expect(login_list)
        if i == 0:
            if log:
                logging.debug('Logged in successfully')
        elif i == 1:
            if log:
                logging.info('Received connection prompt again. Closing...')
            self.close(log=log)
            raise ConnectionError('Received connection prompt again')
        elif i == 2:
            if log:
                logging.info('Received password prompt again. Closing...')
            self.close(log=log)
            raise ConnectionError('Received password prompt again')
        elif i == 3:
            if log:
                logging.info('Permission denied. Closing...')
            self.close(log=log)
            raise ConnectionError('Permission denied')
        elif i == 4:
            if log:
                logging.info('Connection closed by remote host. Closing...')
            self.close(log=log)
            raise ConnectionError('Connection closed by remote host')
        elif i == 5:
            if log:
                logging.info('Connection refused. Closing...')
            self.close(log=log)
            raise ConnectionError('Connection refused')
        elif i == 6:
            if log:
                logging.info('Maximum number of sessions. Closing...')
            self.close(log=log)
            raise ConnectionError('Maximum number of sessions')
        elif i == 7:
            if log:
                logging.info('Could not resolve hostname. Closing...')
            self.close(log=log)
            raise ConnectionError('Could not resolve hostname')
        elif i == 8:
            if log:
                logging.info('Received EOF. Closing...')
            self.close(log=log)
            raise ConnectionError('Received EOF')
        elif i == 9:
            if log:
                logging.info('Connection timed out. Closing...')
            self.close(log=log)
            raise ConnectionError('Connection timed out')
        elif i == 10:
            if log:
                logging.info('Connection timed out. Closing...')
            self.close(log=log)
            raise ConnectionError('Connection timed out')
        if log:
            logging.info('Established SSH connection ' + self.name)


class Console(Connection):
    CONNECTIONS = []

    def __init__(self, user, address, password, prompt, name=None, force=True,
                 login=True, log=True, **kwargs):
        # TODO: Allow connecting from the west coast
        command = '/net/aegis/export/ltconsole/bin/ltconsole ' + address
        super(Console, self).__init__(command, user, address, password, prompt,
                                      name=name, log=log, **kwargs)
        if log:
            logging.debug(command)
        i = self.expect('(?i)Enter')
        if force:
            self.sendcontrol('e')
            self.send('cf')
            if login:
                self.send('#.')
                self.sendline()
                login_list = ['(?i)Login:', TimeoutError]
                done = False
                tries = 0
                while not done and tries < 3:
                    i = self.expect(login_list, timeout=TIMEOUT)
                    if i == 0:
                        done = True
                    else:
                        self.sendline('exit')
                    tries += 1
                if not done:
                    if log:
                        logging.debug('Could not get to login prompt')
                    self.close(log=log)
                    raise ConnectionError('Could not get to login prompt')
                try:
                    self.login(log=log)
                except ConnectionError as e:
                    if log:
                        logging.debug(str(e) + '. Closing...')
                    self.close(log=log)
                    raise e
        if log:
            logging.info('Established Console connection ' + self.name)

    def close(self, log=True):
        try:
            self.sendcontrol('e')
            self.send('c.')
        except Exception:
            pass
        super(Console, self).close(log=log)

    def login(self, log=True):
        self.sendline()
        login_list = ['(?i)Login:', TimeoutError]
        i = self.expect(login_list)
        if i == 0:
            if log:
                logging.debug('Login:')
            self.sendline(self.user)
            if log:
                logging.debug(self.user)
        else:
            if log:
                logging.debug('Could not get to login prompt')
            raise ConnectionError('Could not get to login prompt')
        login_list = [self.prompt, '(?i)Password:', '(?i)Login incorrect']
        i = self.expect(login_list)
        if i == 1:
            if log:
                logging.debug('Password:')
            self.sendline(self.password)
            if log:
                logging.debug(self.password)
            i = self.expect(login_list)
        if i == 0:
            if log:
                logging.debug('Logged in successfully')
        elif i == 1:
            if log:
                logging.debug('Received password prompt again')
            raise ConnectionError('Received password prompt again')
        elif i == 2:
            if log:
                logging.debug('Login incorrect')
            raise ConnectionError('Login incorrect')


class BUI(object):
    CONNECTIONS = []

    def __init__(self, user, address, password, name, log=True):
        self.username = user
        self.password = password
        self.address = 'https://' + address
        self.trace = []
        try:
            self.driver = webdriver.Firefox()
            self.driver.set_page_load_timeout(10)
            self.driver.set_script_timeout(10)
            self.driver.command_executor.set_timeout(10)
            self.wait = WebDriverWait(self.driver, 10)
            self.driver.get(self.address)
            Connection.CONNECTIONS.append(self)
            self.__class__.CONNECTIONS.append(self)
        except Exception as e:
            print(str_error(e))
            raise ConnectionError("Failed to Establish BUI connection " + name)
        else:
            if log:
                logging.info('Established BUI connection ' + name)

    def close(self, log=True):
        try:
            Connection.CONNECTIONS.remove(self)
            self.__class__.CONNECTIONS.remove(self)
            self._logout()
            self.driver.quit()
        except:
            pass

    @classmethod
    def close_all(cls):
        logging.debug('Closing all ' + cls.__name__ + ' connections')

        for connection in cls.CONNECTIONS[:]:
            connection.close()

        logging.debug('Closed all ' + cls.__name__ + ' connections')

    def _logout(self):
        self.driver.get(self.address + '/logout.asp')
        self.wait.until(EC.presence_of_element_located((By.NAME, "username")))
