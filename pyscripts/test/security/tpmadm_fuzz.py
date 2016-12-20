import re
import os
import ssl
import sys
import time
import atexit
import random
import string
import socket
import logging
import traceback
import exceptions
import paramiko
from paramiko.ssh_exception import SSHException
from paramiko.ssh_exception import BadHostKeyException
from paramiko.ssh_exception import AuthenticationException
import paramiko_expect
from pyscript.configs import get_system
from pyscript import ilom
from pyscript import solaris

TESTCASES = ['tpm_response_time', 'tpm_fuzz']

logging.getLogger("paramiko").setLevel(logging.INFO)

ssh_ilom = paramiko.SSHClient()
ssh_host = paramiko.SSHClient()

class TestError(Exception):
    """Raised when the class :class:`Test` or any of its subclasses
    encounters an error.
    """
class FuzzableString():

    def add_long_strings(self, sequence):
        '''
        Given a sequence, generate a number of selectively chosen strings
        lengths of the given sequence and add to the string heuristic library.

        @@type  sequence: String
        @@param sequence: Sequence to repeat for creation of fuzz strings.
        '''
        for length in [10, 20, 50, 128, 255]:
            long_string = sequence * length
            self.fuzz_library.append(long_string)

    def num_mutations(self):
        '''
        Calculate and return the total number of mutations for this
        individual primitive.

        @@rtype:  Integer
        @@return: Number of mutated forms this primitive can take
        '''

        return len(self.fuzz_library)

    def __init__(self, value):
        self.value = value

        self.fuzz_library = \
        [
            self.value * 2,
            self.value * 10,
            self.value * 100,
            "",

            # strings ripped from spike (and some others I added)
            "/.../.../.../.../.../.../.../.../.../.../",
            "/../../../../../../../../../../../../etc/passwd",
            "/../../../../../../../../../../../../boot.ini",
            "..:..:..:..:..:..:..:..:..:..:..:..:..:",
            "\\\\*",
            "\\\\?\\",
            "/\\" * 50,
            "!@@#$%%^#$%#$@@#$%$$@@#$%^^**(()",
            "%01%02%03%04%0a%0d%0aADSF",
            "%01%02%03@@%04%0a%0d%0aADSF",
            "/%00/",
            "%00/",
            "%00",
            "%u0000",

            # format strings.
            "%n"     * 75,
            "%s"     * 75,
            # added
            "\"%s\"" * 20,

            # command injection.
            "|touch /tmp/SULLEY",
            ";touch /tmp/SULLEY;",
            "|notepad",
            ";notepad;",
            "\nnotepad\n",

            # SQL injection.
            "1;SELECT%20*",
            "'sqlattempt1",
            "(sqlattempt2)",
            "OR%201=1",

            # miscellaneous.
            "\r\n" * 100,
            "A" * 159,   # sendmail crackaddr
                         # (http://lsd-pl.net/other/sendmail.txt)
            "<>" * 50,   # sendmail crackaddr
                         # (http://lsd-pl.net/other/sendmail.txt)
        ]

        # add some long strings.
        self.add_long_strings("A")
        self.add_long_strings("B")
        self.add_long_strings("1")
        self.add_long_strings("2")
        self.add_long_strings("3")
        self.add_long_strings("<")
        self.add_long_strings(">")
        self.add_long_strings("'")
        self.add_long_strings("\"")
        self.add_long_strings("/")
        self.add_long_strings("\\")
        self.add_long_strings("?")
        self.add_long_strings("=")
        self.add_long_strings("a=")
        self.add_long_strings("&")
        self.add_long_strings(".")
        self.add_long_strings(",")
        self.add_long_strings("(")
        self.add_long_strings(")")
        self.add_long_strings("]")
        self.add_long_strings("[")
        self.add_long_strings("%")
        self.add_long_strings("*")
        self.add_long_strings("-")
        self.add_long_strings("+")
        self.add_long_strings("{")
        self.add_long_strings("}")
        # self.add_long_strings("\x14")
        # self.add_long_strings("\xFE")   # expands to 4 characters under utf16
        # self.add_long_strings("\xFF")   # expands to 4 characters under utf16

        # add some long strings with null bytes thrown in the middle of it.
        # deleted null bytes cause they put term in odd mode
        for length in [128, 256, 1024, 2048, 4096, 32767, 0xFFFF]:
            s = "B" * length
            s = s[:len(s)/2] + "hi" + s[len(s)/2:]
            # s = s[:len(s)/2] + "\x00" + s[len(s)/2:]
            self.fuzz_library.append(s)

    def get_library(self):

        return self.fuzz_library

    def get_library(self):

        return self.fuzz_library


class FuzzingTest():
    """
    This is a base test for fuzzing an interface
    """
    # def __init__(self):

    def _setup(self):
        """
        This needs to be called from setup()
        """

        self.testcases = self.build_testcases()

    def build_testcases(self):

        password = FuzzableString('anything')

        index = 0
        testcases = {}
        # build a testcase dictionary

        # truncate passwords over 256 since they put the terminal in odd state
        truncated = 0
        for password in password.fuzz_library:
            if len(password) > 256:
                password = password[:256]
                truncated += 1
            testcases[index] = (password)
            index += 1
        logging.info("Testcases created: " + str(index))
        if truncated:
            logging.info("truncated " + str(truncated) + " passwords")

        for x in range(0, 2):
        #for x in range(0, 2048):
            password = ''.join(random.choice(string.letters + string.digits +
                                             "_" + string.punctuation)
                               for i in range(0, random.randint(1, 255)))
            testcases[index] = password
            index += 1

        return testcases

    def browse_testcases(self):

        testcases = self.build_testcases()

        input = ""
        while input != 'q':
            input = raw_input("Enter tc number(q to quit): ")
            if input == "":
                continue
            try:
                params = testcases[int(input)]
                if len(params) <= 2047:
                    log.info("data = '" + params + "'")
                else:
                    log.info("Data field length = " + str(len(params)))
                    temp = params[:2047] + "<TRUNCATED>"
                    log.info("data = '" + temp + "'")
            except:
                log.info("Bad Testcase.")
                continue


def cleanup():
    global ssh_ilom
    global ssh_host

    ssh_ilom.close()
    ssh_host.close()


def tpm_test():

    passed = 0
    failed = 0
    issues = 0
    messages = []
    global ssh_ilom

    prompt = ['-> ']
    system = get_system()
    try:
        ssh_ilom = ilom.login(system)
    except Exception as e:
        raise TestError('loggin failed' + str(e))
        #logging.info("login failed:\n" + str(e))
        
    interact_ilom = paramiko_expect.SSHClientInteraction(ssh_ilom, timeout=10,
                                                         display=True)
    # get output from logging in; clears the expect buffer
    try:
        match = interact_ilom.expect(prompt)
    except socket.timeout:
        raise TestError('login: timeout')
    ilom.start_sys(interact_ilom)
    try:
        ps = ilom.ilom_get_prop(interact_ilom, '/SYS', 'power_state')
    except Exception as e:
        logging.info(str(e))
    try:
        ps = ilom.ilom_set_prop(interact_ilom, '/HOST/tpm', 'forceclear=true')
    except Exception as e:
        logging.info(str(e))


def tpm_response_time():
    """
    Verifies that if invalid passwords are entered for tpmadm auth
    the system response time slows down causing a timeout
    """

    passed = 0
    failed = 0
    issues = 0
    messages = []
    count = 0
    passwords = ("aaa", "bbbb", "ccc", "ddd", "eee", "ffff", "ggggZ")
    prompt = ['.*#.', '.*Enter PIN:', '.*Verify PIN:']
    global ssh_host

    atexit.register(cleanup)
    system = get_system()

    try:
        tpmadm_init()
    except ilom.IlomError:
        logging.info("tpmadm init failed")
        raise TestError('tpmadm init: failed')
    ssh_host = solaris.login(system)
    interact_host = paramiko_expect.SSHClientInteraction(ssh_host,
                          timeout=10, display=False)
    match = interact_host.expect(prompt)
    logging.info("Looping tpmadm auth: 700 iterations with invalid PINS")
    while (count < 100):
        for password in passwords:
            interact_host.send('tpmadm auth')
            try:
                match = interact_host.expect(prompt)
            except socket.timeout:
                logging.info("tpmadm auth: timeout")
                sys.exit(1)

            if (match == 1):
                interact_host.send(password)
                try:
                    match = interact_host.expect(prompt)
                except socket.timeout:
                    msg = "passed: tpmadm auth: timeout as expected"
                    logging.info(msg)
                    passed += 1
                while(True):
                    if (match == 1):
                        interact_host.send('12345')
                    elif (match == 2):
                        interact_host.send('12345')
                    elif (match == 0):
                        if ('fail' in
                            interact_host.current_output_clean.lower()
                            or 'error'
                            'defending against dictionary attacks' in
                             interact_host.current_output_clean.lower()):
                            break
                        else:
                            msg = "tpm auth should have failed"
                            logging.info(msg)
                            if (msg not in self.messages):
                                messages.append(msg)
                            failed += 1
                            break
                    try:
                        match = interact_host.expect(prompt)
                    except socket.timeout:
                        logging.info("tpmadm auth: timeout")
                        passed += 1
                        break
            else:
                msg = "tpmadm auth: missing PIN prompt" + \
                      interact_host.current_output_clean
                logging.info(msg)
                if msg not in messages:
                    messages.append(msg)
                issues += 1
                break
            if (passed):
                break
            count += 1

    if passed:
        logging.info("tpmadm auth slowed response time with invalid logins")
    else:
        msg = "BUG 25072156:response is not slowed after failed auth attempts"
        logging.info(msg)
        messages.append(msg)
        failed += 1
    ssh_host.close()
    return(passed, failed, issues, messages)

def tpm_fuzz():
    """
    """
    passed = 0
    failed = 0
    issues = 0
    cores = 0
    messages = []
    count = 0
    t = FuzzingTest()
    testcases = t.build_testcases()
    testlist = testcases.keys()
    prompt = ['.*#.', '.*Enter PIN:', '.*Verify PIN:']
    global ssh_host
    atexit.register(cleanup)

    try:
        tpmadm_init()
    except ilom.IlomError:
        logging.info("tpmadm init failed")
        raise TestError('tpmadm_init:failed')
    system = get_system()
    ssh_host = solaris.login(system)
    interact_host = paramiko_expect.SSHClientInteraction(ssh_host, timeout=10,
                                                         display=False)
    match = interact_host.expect(prompt)
    for tc in testlist:
        count += 1
        (password) = testcases[int(tc)]
        logging.info('\n{0:=^79}'.format('password'))
        logging.info(password)
        rm_core_files(interact_host)
        interact_host.send('tpmadm auth')
        try:
            match = interact_host.expect(prompt)
        except socket.timeout:
            issues += 1
            msg = "issue: owner Enter PIN: timeout"
            logging.info(msg)
            if (msg not in messages):
                messages.append(msg)
            continue
        if (match == 1):
            interact_host.send(password)
            try:
                match = interact_host.expect(prompt)
            except socket.timeout:
                if (len(password) > 256):
                    logging.debug("password > 256 chars, timeout expected")
                    continue
                else:
                    msg = "issue: New owner Enter PIN: timeout"
                    logging.info(msg)
                    issues += 1
                    if (msg not in messages):
                        messages.append(msg)
                    continue
            while(True):
                if (match == 1):
                    interact_host.send('8765')
                elif (match == 2):
                    interact_host.send('8765')
                elif (match == 0):
                    # some testcases inject carrriage retrns which cause
                    # different tpmadm auth cmd behavior and sync issues
                    # with the prompt
                    if ('no secret information' in
                       interact_host.current_output_clean.lower()):
                        # needs to clear carriage returns from buffer
                        # for long passwds with multiple carriage returns
                        while(True):
                            try:
                                interact_host.expect(prompt)
                                logging.debug("Clearing buffer")
                            except socket.timeout:
                                break
                        passed += 1
                        logging.info("passed: passwd with len, "
                                     + str(len(password)))
                        break
                    if ('authentication failed' in
                            interact_host.current_output_clean.lower()):
                        passed += 1
                        logging.info("passed: passwd with len "
                                     + str(len(password)))
                        break
                    else:
                        logging.info("failed: passwd with len "
                                     + str(len(password)))
                        logging.info("passwd = " + password)
                        res = check_for_core_file(interact_host)
                        if res:
                            cores += 1
                            logging.info("See BUG ID: BUG ID 25072958")
                        else:
                            logging.info("false success")
                            logging.info("output = " + interact.current_output)
                            logging.info("password = \n" + password)
                            msg = "false success"
                            if msg not in messages:
                                messages.append(msg)
                        failed += 1
                        break
                try:
                    match = interact_host.expect(prompt)
                except socket.timeout:
                    msg = "issue: Verify PIN or prompt timeout"
                    logging.info(msg)
                    if msg not in messages:
                        messages.append(msg)
                    issues += 1
                    break
        else:
            msg = "issue: prompt missing, buffer = " + \
                  interact_host.current_output_clean
            issues += 1
            logging.info(msg)
            if msg not in messages:
                messages.append(msg)
            continue
    if cores > 0:
        messages.append("BUG ID 25072958: " + str(cores) +
                        " core files(s) found")
    ssh_host.close()
    return(passed, failed, issues, messages)


def tpmadm_init():

    system = get_system()
    global ssh_ilom
    global ssh_host
        
    ssh_ilom = ilom.login(system)
    interact_ilom = paramiko_expect.SSHClientInteraction(ssh_ilom,
                            timeout=10, display=True)
    try:
        match = interact_ilom.expect('-> ')
    except socket.timeout:
        logging.info('ilom login: timeout')
        raise TestError('ilom login: timeout')

    try:
        ssh_host = solaris.login(system)
    except:
        ilom.start_sys(interact_ilom)
        ssh_host = solaris.login(system)

    interact_host = paramiko_expect.SSHClientInteraction(ssh_host,
                                timeout=10, display=True)
    try:
        match = interact_host.expect('.*#.')
    except socket.timeout:
        logging.info('host login: timeout')
        raise TestError('start sp console: timeout')

    interact_host.send('svcadm enable tcsd')
    try:
        interact_host.expect('.*#.')
    except socket.timeout:
        logging.info('svcsadm enable tcsd: timeout')
        raise TestError('svcadm enable: timeout')


    # try to clean up old tpmadm instances using common PIN 87654321
    interact_host.send('tpmadm status')
    try:
        match = interact_host.expect('.*#.')
    except socket.timeout:
        logging.info('tpmadm status: timeout')
        raise TestError('tpmadm status: timeout')
    if 'Platform Configuration Registers' in interact_host.current_output:
        interact_host.send('tpmadm clear owner')
        try:
            interact_host.expect('Enter PIN:')
        except socket.timeout:
            logging.info('tpmadm clear owner: timeout')
            raise TestError('tpmadm clear owner: timeout')
        interact_host.send('87654321')
        try:
            interact_host.expect('.*#.')
        except socket.timeout:
            logging.info('tpmadm clear owner: timeout')
            raise TestError('tpmadm clear owner: timeout')
        
    interact_host.send('svcadm disable tcsd')
    ssh_host.close()
    logging.info("Stopping SYS")
    prompt = ['-> ']
    interact_ilom.send('stop -f -script /SYS')
    try:
        match = interact_ilom.expect(prompt)
    except socket.timeout:
        raise TestError('stop sys: timeout')
    time.sleep(5)
    ilom.ilom_set_prop(interact_ilom, '/HOST/tpm ', 'forceclear=true')
    ilom.ilom_set_prop(interact_ilom, '/HOST/bootmode ',
                  "script=\'setenv auto-boot? true\'")
    interact_ilom.send('start -f -script /SYS')
    try:
        match = interact_ilom.expect(prompt)
    except socket.timeout:
        raise TestError('start sys: timeout')
    logging.info("Starting SYS")
    prompt = ['.*(?i)console login: ']
    interact_ilom.send('start -f -script /SP/console')
    try:
        match = interact_ilom.expect(prompt, timeout=600)
    except socket.timeout:
        logging.info('start sp console: timeout')
        raise TestError('start sp console: timeout')

    prompt = ['.*#.']
    ssh_host = solaris.login(system)
    interact_host = paramiko_expect.SSHClientInteraction(ssh_host, timeout=10,
                                                         display=True)
    # get output from logging in; clears the expect buffer
    try:
        match = interact_host.expect(prompt)
    except socket.timeout:
        logging.info('host login: timeout')
        raise TestError('start sp console: timeout')

    interact_host.send('svcadm enable tcsd')
    try:
        interact_host.expect('.*#.')
    except socket.timeout:
        logging.info('svcsand enable tcsd: timeout')
        raise TestError('start sp console: timeout')
        
    prompt = ['.*#.', '.*Enter TPM Owner PIN:', '.*Confirm TPM Owner PIN:',
              '.*\[y|N\]\?.', '.*\[y\/N\]\?.']
    logging.info("Initializing tpmadm init")
    interact_host.send('tpmadm init')
    match = interact_host.expect(prompt)
    while (match == 1 or match == 2):
        logging.info("Sending PIN **************")
        interact_host.send('87654321')
        match = interact_host.expect(prompt)
    if match == 3 or match == 4:
        logging.info("\nSending y ")
        interact_host.send('y')
        match = interact_host.expect(prompt)
    if match != 0:
        logging.info("tpmadm init failed: " + interact_host.current_output)
        raise TestError('start sp console: timeout')
    else:
        if ('fail' in interact_host.current_output_clean.lower() or 'error' in
                interact_host.current_output_clean.lower()):
            logging.info("tpmadm init: " + interact_host.current_output_clean)
            raise TestError('tpmadm_init:failed')
        else:
            logging.info('tpmadm init succeeded')
    ssh_host.close()


def rm_core_files(interact_host):

    interact_host.send('ls')
    try:
        match = interact_host.expect('.*#.', timeout=20)
    except socket.timeout:
        pass
    if 'core' in interact_host.current_output_clean:
        interact_host.send('rm core')
        match = interact_host.expect('.*#.', timeout=20)


def check_for_core_file(interact_host):

    interact_host.send('ls')
    try:
        match = interact_host.expect('.*#.')
    except socket.timeout:
        pass
    if 'core' in interact_host.current_output_clean:
        return(1)
    else:
        return(0)


def set_log_format(format):
    hdlr.setFormatter(format)
    stream_handler.setFormatter(format)
