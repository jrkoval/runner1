#!/usr/bin/env python


"""
"""

import time
import logging
from pytest.test import Test
from pytest.environment import get_system
from pytest.globals import str_error
from pytest.ilom import ILOMError
from pexpect import TIMEOUT as TimeoutError

CMD_TIMEOUT = 120
OWNER_PIN = '87654321'
ALT_OWNER_PIN = '12345678'
MIGRATION_PIN = '12345678'
PASSPHRASE = '87654321'
#PASSPHRASE = '45678901'
MRK_KEY = '00000000-0000-0000-0000-00000000000b'
NewKeyUUID_1 = '00000000-0000-0000-0000-00000000000c'
NewKeyUUID_2 = '00000000-0000-0000-0000-00000000000d'
InvalidUUID = '00000000-0000-0000-0000-00000000000f'
TESTS = ['FPGA', 'TPMADM']


class FPGA(Test):
    """
    """

    #TESTCASES = ['fpga_disable', 'fpga_enable']
    TESTCASES = ['fpga_enable']

    def __init__(self):
        super(FPGA, self).__init__()
        self.system = get_system()
        self.sunservice = self.system.get_connection('SSH', 'SP', 'sunservice')
        self.ilom = self.system.get_connection('SSH', 'SP', 'root')
        self.ilom.sendcmd('version', log=True)
        self.ilom.show('/HOST/tpm', 'mode', log=True)
        self.sunservice.sendcmd('fpga version', log=True)
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.ilom.start_system()
            try:
                solaris = self.system.get_connection('SSH', 'HOST', 'root')
            except:
                self.abort('Failed to connect to Solaris')
        solaris.sendcmd('uname -a', log=True)
        solaris.sendcmd('svcs tcsd', log=True)
        solaris.sendcmd('svcadm disable tcsd', log=True)
        solaris.close()
        factory_defaults(self)


    def fpga_disable(self):

        # px = [fpga_val, ilom_val, fpga_status, post_status]
        p1 = ['disable', 'off', 'disabled', 'disabled']
        p2 = ['disable', 'activated', 'disabled', 'disabled']
        p3 = ['disable', 'deactivated', 'disabled', 'disabled']
        p4 = ['enable', 'off', 'enabled', 'off']
        p5 = ['enable', 'deactivated', 'enabled', 'disabled']
        testcases = {'tc1': p1}
        #testcases = {'tc1': p1, 'tc2': p2, 'tc3': p3, 'tc4': p4, 'tc5': p5}

        for tc in testcases:
            p = testcases[tc]
            logging.info('Testing: fpga = '+p[0] + ',' + 'ilom = '+p[1])
            #prereq tpm enabled
            tpm_enable(self)
            try:
                solaris = self.system.get_connection('SSH',\
                                         'HOST', 'root')
            except:
                self.ilom.start_system()
                try:
                    solaris = self.system.get_connection('SSH',\
                             'HOST', 'root')
                except:
                    self.issue('Failed to connect to Solaris')
            solaris.sendcmd('svcadm disable tcsd', log=True)
            for i in range(10):
                if 'disable' in self.ilom.sendcmd('svcs tcsd', log=True):
                    break
                time.sleep(2)
            if i == 9:
                self.abort('tcsd not disable')
            post_status = True
            self.ilom.stop_system(force=True)
            self.ilom.show('/HOST/', 'status')
            cmd_str = 'fpga tpm {0}'.format(p[0])
            self.sunservice.sendcmd(cmd_str, log=True)
            status = self.sunservice.sendcmd('fpga tpm status',
                                             log=True).strip()
            if status.lower() != p[2]:
                self.failed('TPM status is {0}'.format(status))
                continue
            ret = set_and_verify(self, '/HOST/tpm', mode=p[1])
            if ret:
                self.failed('TPM mode is {0}'.format(ret))
                continue
            ret = set_and_verify(self, '/HOST/tpm', forceclear='true')
            if ret:
                self.failed('TPM forceclear is {0}'.format(ret))
                continue
            # get output from console
            (s_out, b_out, e) = self.ilom.start_system(console=True,
                                          user='root', verbose=False)
            for line in s_out.splitlines():
                if 'TPMinitialized' in line.replace(' ', ''):
                    continue
                if 'NOTICE:CurrentTPM' in line.replace(' ', '') or \
                        'NOTICE:TPM' in line.replace(' ', '') or \
                        'WARNING:TPM' in line.replace(' ', ''):
                    if p[3] not in line.lower():
                        self.failed('POST output incorrect\n' +
                                    line[line.index('>')+2:])
                        post_status = False
            if post_status == False:
                self.ilom.sendcmd('svcadm disable tcsd', log=True)
                for i in range(10):
                    if 'disable' in self.ilom.sendcmd('svcs tcsd', log=True):
                        break
                    time.sleep(2)
                if i == 9:
                    self.issue('tcsd not disable')
                self.ilom.logout()
                self.ilom.stop_console()
                continue
            self.ilom.sendcmd('svcadm disable tcsd', log=True)
            for i in range(10):
                if 'disable' in self.ilom.sendcmd('svcs tcsd', log=True):
                    break
                time.sleep(2)
            if i == 9:
                self.issue('tcsd not disable')
            self.ilom.logout()
            self.ilom.stop_console()
            self.passed()

    def fpga_enable(self):

        # enables tpm in ilom and in sunservice (fpga)
        # starts system and verifies tpm firmware is initialized

        # prereq: tpm is disabled 
        tpm_disable(self)
        self.ilom.stop_system(force=True)
        cmd_str = 'fpga tpm enable'
        self.sunservice.sendcmd(cmd_str, log=True)
        status = self.sunservice.sendcmd('fpga tpm status', log=True).strip()
        if status.lower() != 'enabled':
            self.failied('TPM status is {0}'.format(status), stop=True)
        ret = set_and_verify(self, '/HOST/tpm', mode='activated')
        if ret:
            self.failed('TPM mode is {0}'.format(ret), stop=True)
        (s_out, b_out, e) = self.ilom.start_system(console=True, user='root')
        for line in s_out.splitlines():
            if 'TPMinitialized' in line.replace(' ', ''):
                continue
            if 'NOTICE:CurrentTPM' in line.replace(' ', '') or \
                'WARNING:TPM' in line.replace(' ', ''):
                if 'enabled' not in line.lower():
                    self.failed('POST output incorrect\n' +
                           line[line.index('>')+2:], stop=True)
                    break
        self.ilom.sendcmd('svcs tcsd', log=True)
        self.ilom.sendcmd('svcadm enable tcsd', log=True)
        for i in range(10):
            self.info("Polling tcsd status")
            if 'online' in self.ilom.sendcmd('svcs tcsd', log=True):
                break
            time.sleep(2)
        if i == 9:
            self.failed('tcsd not online', stop=True)
        else:
            self.passed("tcsd is online")
        self.ilom.logout()
        #self.ilom.sendline()
        #self.ilom.sync(debug=True, log=True)
        #self.ilom.sendcmd('exit', prompt='(?i)Console login: ', log=True)
        self.ilom.stop_console()

    def testcase_cleanup(self):
        self.info("Entering testcase cleanup")
        # catch the case where a tc aborts with the console active
        if hasattr(self.ilom, 'stop_console'):
            self.ilom.stop_console()
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.ilom.start_system()
            try:
                solaris = self.system.get_connection('SSH', 'HOST', 'root')
            except:
                self.issue('Failed to connect to Solaris')
        solaris.sendcmd('svcadm disable tcsd', log=True)
        for i in range(10):
            self.info("Polling tcsd status")
            if 'disable' in solaris.sendcmd('svcs tcsd', log=True):
                break
            time.sleep(2)
        if i == 9:
            self.issue('tcsd not disable', stop=True)
        else:
            self.info("tcsd is disable")
        solaris.close()
        self.info("Exiting testcase cleanup")


class TPMADM(Test):
    """
    """

    TESTCASES = ['tpmadm_init', 'tpmadm_status',
                 'tpmadm_migrate', 'tpmadm_forceclear',
                 'tpmadm_keyinfo', 'tpmadm_deletekey', 'tpmadm_clearowner',
                 'tpmadm_clear_lock']

    def __init__(self):
        super(TPMADM, self).__init__()
        self.system = get_system()
        self.sunservice = self.system.get_connection('SSH', 'SP', 'sunservice')
        self.ilom = self.system.get_connection('SSH', 'SP', 'root')
        self.ilom.sendcmd('version', log=True)
        self.ilom.show('/HOST/tpm', 'mode', log=True)
        self.sunservice.sendcmd('fpga version', log=True)
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.ilom.start_system()
            try:
                solaris = self.system.get_connection('SSH', 'HOST', 'root')
            except:
                self.abort('Failed to connect to Solaris')
        solaris.sendcmd('uname -a', log=True)
        solaris.sendcmd('svcs tcsd', log=True)
        solaris.sendcmd('svcadm disable tcsd', log=True)
        solaris.close()
        factory_defaults(self, force=True)
        self.info("Exiting __init__")


    def tpmadm_init(self):

        self.info("Initialize tpm with tpmadm init")
        tpm_init(self)
        if self.current_issue_count != 0:
            self.failed('tpmadm init failed')
        self.passed()

    def tpmadm_status(self):

        self.info("Initialize tpm with tpmadm init")
        tpm_init(self)
        if self.current_issue_count != 0:
            self.abort('tpmadm init failed')

        # test tpmadm status
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.ilom.start_system()
            try:
                solaris = self.system.get_connection('SSH', 'HOST', 'root')
            except:
                self.issue('Failed to connect to Solaris')

        output = solaris.sendcmd('tpmadm status', log=True)
        if 'Platform Configuration Registers' in output:
            self.passed()
        else:
            self.failed('tpmadm status failed:' + output)
        solaris.close()

    def tpmadm_migrate_import(self):

        self.info("Initialize tpm with tpmadm init")
        tpm_init(self)
        if self.current_issue_count != 0:
            self.failed('tpmadm init failed')
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.abort('Could not make connection to Solaris')
        output = solaris.sendcmd('tpmadm keyinfo', log=True)
        cmd = 'tpmadm deletekey ' + MRK_KEY
        prompt = ['\[y|N\]]\?', '\[y\/N\]\?']
        solaris.sendcmd(cmd, prompt=prompt, log=True)
        solaris.sendcmd('y', log=True)

        # in the case where iwe are migrating the System MRK UUID to
        # the current SRK the migration pin = owner pin
        cmd = 'tpmadm migrate import'
        output = send_command(self, solaris, cmd,
                                migration_pin='owner', log=True)
        output = solaris.sendcmd('tpmadm keyinfo', log=True)
        self.passed()

    def tpmadm_migrate(self):

        self.info("Initialize tpm with tpmadm init")
        #create the .dat and .key files in /root
        tpm_init(self)
        if self.current_issue_count != 0:
            self.abort('Could not init tpmadm, abort')
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.abort('Could not make connection to Solaris')
        #test export
        self.info('Test: Export of the default Migratable Root Key') 
        cmd = 'tpmadm migrate export ' + MRK_KEY 
        output = send_command(self, solaris, cmd, log=True)
        if output is None:
            self.failed("tpmadm migrate export timed out", stop=True)
        elif ('fail' in output.lower() or 'error' in output.lower()):
            self.failed(stop=True)
        if not ('Enter PIN' in output and
                'Confirm PIN' in output):
            self.failed("tpmadm migrate export failed", stop=True)
        for f in ['tpm-migration.dat', 'tpm-migration.key']:
            cmd_str = 'ls -las /root/' + f
            output = solaris.sendcmd(cmd_str, log=True)
            len = solaris.sendcmd(cmd_str, log=True)[5]
            if 'No such file or directory' in output:
                self.failed(f + 'not found', stop=True)
            if len == 0:
                self.failed(f + 'is zero length', stop=True)

        # Now test import
        cmd = 'tpmadm deletekey ' + MRK_KEY
        try:
             prompt = ['\[y|N\]]\?', '\[y\/N\]\?']
             solaris.sendcmd(cmd, prompt=prompt, log=True)
             solaris.sendcmd('y', log=True)
        except TimeoutError:
             self.failed("tpmadm deletekey timed out", stop=True)
        solaris.sendcmd('rm -rf /root/tpm-migration.dat', log=True)
        solaris.sendcmd('rm -rf /root/tpm-migration.key', log=True)
        # test the importing of the default MRK 
        # the owner pin is the migration pin in this case
        self.info('Test: the importing of the default Migratable Root Key') 
        output = send_command(self, solaris, 'tpmadm migrate import',
                                           migration_pin='owner', log=True)
        if output is None:
            self.failed("tpmadm migrate export timed out", stop=True)
        elif ('fail' in output.lower() or 'error' in output.lower()):
            self.failed(output)
        if not ('TPM Owner PIN' in output and
                'the migration key' in output):
            self.failed("tpmadm migrate import default args failed",
                                                          stop=True)
        output = solaris.sendcmd('tpmadm keyinfo', log=True)
        match_str = '[SYSTEM] ' + MRK_KEY
        if not (match_str in output):
            self.failed("tpmadm keyinfo for import with no args failed",
                                                              stop=True)

        # execute export to create the migration files 
        # to test additional imports
        cmd = 'tpmadm migrate export ' + MRK_KEY 
        output = send_command(self, solaris, cmd, log=True)

        # import key and make it the child of the MRK 
        # we will call this key NewKeyUUID_1; we can use it later to
        # as a parentUUID.
        self.info('Test: import a key and make it the child of the MRK') 
        cmd_str = 'tpmadm migrate import /root/tpm-migration.dat /root/tpm-migration.key '
        cmd = cmd_str + MRK_KEY + ' ' + NewKeyUUID_1 
        output = send_command(self, solaris, cmd, log=True)
        print("migrate output = " + output)
        if output is None:
            self.failed("tpmadm migrate export timed out", stop=True)
        elif ('fail' in output.lower() or 'error' in output.lower()):
            self.failed(stop=True)
        if not ('TPM Owner PIN' in output and
                'the migration key' in output and
                'the migrated key' in output):
            self.failed("key import of a child of the MRK key failed",
                                                         stop=True)
        output = solaris.sendcmd('tpmadm keyinfo', log=True)
        match_str = '[USER] ' + NewKeyUUID_1
        if not (match_str in output):
            self.failed("key import of a child of the MRK key failed",
                                                           stop=True)
        #cleanup tpm files 
        solaris.sendcmd('rm -rf /root/tpm-migration.dat', log=True)
        solaris.sendcmd('rm -rf /root/tpm-migration.key', log=True)

        self.info('Test: import a key and make it the child of a User Key') 
        cmd = 'tpmadm migrate export ' +  NewKeyUUID_1 
        output = send_command(self, solaris, cmd, log=True)
        tpm_mig_files = '/root/tpm-migration.dat /root/tpm-migration.key '
        cmd_str = 'tpmadm migrate import '
        cmd = cmd_str + tpm_mig_files + NewKeyUUID_1 + ' ' + NewKeyUUID_2
        output = send_command(self, solaris, cmd, log=True)
        print("migrate output = " + output)
        if output is None:
            self.failed("tpmadm migrate export timed out", stop=True)
        elif ('fail' in output.lower() or 'error' in output.lower()):
            self.failed(stop=True)
        if not ('TPM Owner PIN' in output and
                'the migration key' in output and
                'the migrated key' in output):
            self.failed("key import of a child of the MRK key failed",
                                                          stop=True)
        output = solaris.sendcmd('tpmadm keyinfo', log=True)
        match_str = '[USER] ' + NewKeyUUID_2 
        if not (match_str in output):
            self.failed("key import of a child of a USER  key failed",
                                                            stop=True)
        else:
            self.passed()
        #cleanup
        out = solaris.sendcmd('tpmadm keyinfo', log=True)
        print("output = ")
        print(out)
        print("outputi over")

        for line in out.strip().splitlines():
            if ('tpmadm keyinfo' in line):
                continue;
            key = line.split()[1]
            cmd = 'tpmadm deletekey ' + key
            prompt = ['\[y|N\]]\?', '\[y\/N\]\?']
            try:
                solaris.sendcmd(cmd, prompt=prompt, log=True)
                solaris.sendcmd('y', log=True)
            except TimeoutError:
                self.issue("tpmadm deletekey timed out")
        for f in ['tpm-migration.dat', 'tpm-migration.key']:
            cmd_str = 'rm /root/' + f
            solaris.sendcmd(cmd_str, log=True)
            cmd_str = 'rm /var/tpm/system/' + f
            solaris.sendcmd(cmd_str, log=True)
        
        solaris.close()

    def tpmadm_forceclear(self):

        found = False

        tpm_init(self)
        if self.current_issue_count != 0:
            self.abort('Could not init tpmadm, abort')

        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.issue('Failed to connect to Solaris')
        solaris.sendcmd('rm -rf /root/tpm-migration.dat', log=True)
        solaris.sendcmd('rm -rf /root/tpm-migration.key', log=True)
        #solaris.sendcmd('rm -rf /var/tpm/system/tpm-migration.dat', log=True)
        #solaris.sendcmd('rm -rf /var/tpm/system/tpm-migration.key', log=True)
        solaris.sendcmd('svcadm disable tcsd', log=True)
        for i in range(10):
            self.info("Polling svcs tcsd")
            if 'disable' in solaris.sendcmd('svcs tcsd', log=True):
                break
            time.sleep(2)
        if i == 9:
            self.abort('tcsd not disabled')
        time.sleep(5)   
        solaris.close()

        # Oats says to check if forceclear is at default of false.
        # should we check in automation
        # we really don't know the previous status of the system?
        # Skipping for now.
        # Bring the system down and set forceclear to true.
        self.ilom.stop_system()

        # test 1; verify forceclear clears the tpm owner
        ret = set_and_verify(self, '/HOST/tpm', forceclear='true')
        if ret:
            self.failed('TPM forceclear is {0}'.format(ret))

        # Bring system up and look for forceclear message
        (s_out, b_out, e) = self.ilom.start_system(console=True, user='root')
        for line in s_out.splitlines():
            if 'TPM ForceClear issued.Resetting TPM ForceClear' \
                                                    in line.replace(' ', ''):
                found = True
                break
        self.ilom.logout()
        self.ilom.stop_console()
        if not found:
            self.failed('POST output missing forceclear reset, BUG 24375157')
        else:
            # test 2; tpmadm init after a forceclear
            tpm_init(self)
            if self.current_issue_count != 0:
                self.failed('Could not init tpmadm after forceclear')
            else:
                self.passed()

    def tpmadm_keyinfo(self):

        tpm_init(self)
        if self.current_issue_count != 0:
            self.abort('Could not init tpmadm, abort')
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.issue('Could not make connection to Solaris')
        else:
            output = solaris.sendcmd('tpmadm keyinfo', log=True)
        if output is None:
            self.failed("tpmadm keyinfo timed out")
        elif MRK_KEY not in output:
            self.failed("incorrect tpmadm keyinfo:" + output)
        else:
            self.passed('keyinfo passed')
        solaris.close()

    def tpmadm_deletekey(self):

        tpm_init(self)
        if self.current_issue_count != 0:
            self.abort('Could not init tpmadm, abort')

	# test 1 - Attempt to delete an invalid key
        prompt = ['\[y|N\]]\?', '\[y\/N\]\?']
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.issue('Could not make connection to Solaris')
        else:
            cmd = 'tpmadm deletekey ' + InvalidUUID 
            try:
                solaris.sendcmd(cmd, prompt=prompt, log=True)
                output = solaris.sendcmd('y', log=True)
            except TimeoutError:
                 self.failed("tpmadm keyinfo timed out", stop=True)
        if "Key not found in persistent storage" not in output:
            self.failed("incorrect tpmadm keyinfo:" + output)
        else:
            self.passed()

        #test 2: delete MRK
        prompt = ['\[y|N\]]\?', '\[y\/N\]\?']
        cmd = 'tpmadm deletekey ' + MRK_KEY
        try:
            out = solaris.sendcmd(cmd, prompt=prompt, log=True)
            out = solaris.sendcmd('y', log=True)
        except TimeoutError:
              self.failed("tpmadm deletekey timed out: " + out)

        #verify the key was deleted
        output = solaris.sendcmd('tpmadm keyinfo', log=True)
        match_str = '[SYSTEM] ' + MRK_KEY
        if (match_str in output):
            self.failed("the MRK was not deleted")
        solaris.sendcmd('rm -rf /root/tpm-migration.dat', log=True)
        solaris.sendcmd('rm -rf /root/tpm-migration.key', log=True)

        self.passed()
        solaris.close()

    def tpmadm_clearowner(self):

        # All initialization steps will abort the testcase.

        tpm_init(self)
        if self.current_issue_count != 0:
            self.abort('Could not init tpmadm, abort')

        # Now clear the owner
        tpmadm_clear_owner(self)
        if self.current_issue_count != 0:
            self.failed("tpmadm clear owner failed")
        else:
            self.passed()

    def tpmadm_clear_lock(self):

        # All initialization steps will abort the testcase.
        tpm_init(self)
        if self.current_issue_count != 0:
            self.abort('Could not init tpmadm, abort')
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.issue('Could not make connection to Solaris')
        else:
            output = send_command(self, solaris, 'tpmadm clear lock', log=True)
        if output is None:
            self.failed("tpmadm clear lock timed out")
        elif ('fail' in output.lower() or 'error' in output.lower()):
            self.failed()
        else:
            self.passed()
        solaris.close()

    def tpmadm_auth(self):

        tpm_init(self)
        if self.current_issue_count != 0:
            self.abort('Could not init tpmadm, abort')
        tpm_auth(self, OWNER_PIN, ALT_OWNER_PIN)
        if self.current_issue_count != 0:
            self.fail('tpmadm auth failed')
        else:
            self.passed('tpmadm auth passed')
        #restore pin
        tpm_auth(self, ALT_OWNER_PIN, OWNER_PIN)

    def testcase_cleanup(self):
        self.info("Entering testcase cleanup")
        # catch the case where a tc aborts with the console active
        if hasattr(self, 'stop_console'):
            self.ilom.stop_console()
        factory_defaults(self, force=True)
        self.info("Exiting testcase cleanup")

    def cleanup(self):
        self.info("Entering TPMADM Class cleanup")
        # catch the case where a tc aborts with the console active
        if hasattr(self, 'stop_console'):
            self.ilom.stop_console()
        #factory_defaults(self, force=True)

def tpm_auth(self, primary_pin, alt_pin):
 
    exp_list = ['.*#.', '.*Enter PIN:', '.*Verify PIN:', TimeoutError]
    try:
        solaris = self.system.get_connection('SSH', 'HOST', 'root')
    except:
        self.abort('Could not make connection to Solaris')
    else:
        string = ''
        solaris.sendline('tpmadm auth')
        out = solaris.sync(exp_list, debug=True, log=True, after=True)
        if solaris.match_index == 1:
            solaris.sendline(primary_pin)
        else:
            self.failed('tpmadm auth failed: ' + out)
        while True:
            out = solaris.sync(exp_list, debug=True, log=True, after=True)
            string += out
            if solaris.match_index == 0:
               break
            elif (solaris.match_index == 1 or solaris.match_index == 2):
                solaris.sendline(alt_pin)
            elif (solaris.match_index == 3):
                string = None
                break

        if string is None:
            self.issue("tpmadm auth timed out")
        elif 'Verify PIN:' not in string or '#' not in string:
            self.issue("tpmadm auth failed:" + string)
        elif ('fail' in string.lower() or 'error' in string.lower()):
            self.issue('tpmadm auth failed:' + string)

def set_and_verify(self, target, **values):
    self.ilom.set(target, **values)
    prop_dict = self.ilom.show(target, log=True).properties
    for key, val in values.iteritems():
        if prop_dict[key].lower() != val.lower():
            return val
    return 0


def tpm_enable(self):

    # enables tpm in ilom and in sunservice (fpga)
    # starts system and verifies tpm firmware is initialized

    online = False
    # prereq: svcadm disable tcsd 
    self.info("Entering TPM enable")
    try:
        solaris = self.system.get_connection('SSH', 'HOST', 'root')
    except:
        self.ilom.start_system()
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.issue('Failed to connect to Solaris', stop=True)
    solaris.sendcmd("svcadm disable tcsd", log=True)
    for i in range(10):
        self.info("Polling tcsd status")
        if 'disable' in solaris.sendcmd('svcs tcsd', log=True):
            break
        time.sleep(2)
    if i == 9:
        self.issue('tcsd not disable')
    else:
        self.info("tcsd is disable")
    solaris.close()
    self.ilom.stop_system(force=True)
    cmd_str = 'fpga tpm enable'
    self.sunservice.sendcmd(cmd_str, log=True)
    status = self.sunservice.sendcmd('fpga tpm status', log=True).strip()
    if status.lower() != 'enabled':
        self.failed('TPM status is {0}'.format(status), stop=True)
    ret = set_and_verify(self, '/HOST/tpm', mode='activated')
    if ret:
        self.issue('TPM mode is {0}'.format(ret), stop=True)
    ret = set_and_verify(self, '/HOST/tpm', forceclear='true')
    if ret:
        self.issue('TPM mode is {0}'.format(ret), stop=True)
    (s_out, b_out, e) = self.ilom.start_system(console=True, user='root')
    for line in s_out.splitlines():
        if 'TPMinitialized' in line.replace(' ', ''):
            continue
        if 'NOTICE:CurrentTPM' in line.replace(' ', '') or \
            'WARNING:TPM' in line.replace(' ', ''):
            if 'enabled' not in line.lower():
                self.issue('POST output incorrect\n' + \
                       line[line.index('>')+2:], stop=True)
                break
    self.ilom.sendcmd('svcs tcsd', log=True)
    self.ilom.sendcmd('svcadm enable tcsd', log=True)
    for i in range(10):
        self.info("Polling tcsd status")
        if 'online' in self.ilom.sendcmd('svcs tcsd', log=True):
            online = True
            break
        time.sleep(2)
    if i == 9:
        self.issue('tcsd not online', stop=True)
    else:
        self.info("tcsd is online")
    self.ilom.logout()
    self.ilom.stop_console()
    return online

    self.info("Exiting TPM enable")


def tpm_disable(self):
    self.info("Entering tpm_disable")
    # disables tpm in ilom and sunservice (fpga)
    # start host and verifies tpm is disabled
    # since this code is used for testcase initialization
    # failures abort the testcase.

    self.ilom.stop_system(force=True)
    self.ilom.show('/HOST/', 'status')
    cmd_str = 'fpga tpm disable'
    self.sunservice.sendcmd(cmd_str, log=True)
    status = self.sunservice.sendcmd('fpga tpm status', log=True).strip()
    if status.lower() != 'disabled':
        self.abort('TPM status is {0}'.format(status))
    ret = set_and_verify(self, '/HOST/tpm', mode='deactivated')
    if ret:
        self.abort('TPM mode is {0}'.format(ret))
    ret = set_and_verify(self, '/HOST/tpm', forceclear='true')
    if ret:
       self.issue('TPM forceclear is {0}'.format(ret))
    (s_out, b_out, e) = self.ilom.start_system(console=True, user='root')
    for line in s_out.splitlines():
        if 'NOTICE:CurrentTPM' in line.replace(' ', '') or \
           'WARNING:TPM' in line.replace(' ', ''):
            if 'disabled' not in line.lower():
                self.ilom.stop_console()
                self.abort('POST output incorrect\n' +
                           line[line.index('>')+2:])
                break
    for i in range(10):
        self.info("Polling tcsd status")
        if 'disable' in self.ilom.sendcmd('svcs tcsd', log=True):
            break
        time.sleep(2)
    if i == 9:
        self.issue('tcsd not disable')
    else:
        self.info("tcsd is disable")
    self.ilom.logout()
    self.ilom.stop_console()
    self.info("Exiting tpm_disable")


def tpmadm_clear_owner(self):

    try:
        solaris = self.system.get_connection('SSH', 'HOST', 'root')
    except:
        self.ilom.start_system()
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.issue('Failed to connect to Solaris')
    output = send_command(self, solaris, 'tpmadm clear owner', log=True)
    if output is None:
        self.issue("tpmadm clear owner timed out")
    elif "Enter PIN:" not in output:
        self.issue("missing TPM PIN prompt")
    elif "fail" in output.lower():
        self.issue("tpadm clear owner failed")
    elif "error" in output.lower():
        self.issue("tpmadm clear owner error")
    solaris.close()


def factory_defaults(self, force=False):
    self.info("Entering factory defaults")
    reset_flag = False
    #try to enable tcsd
    try:
        solaris = self.system.get_connection('SSH', 'HOST', 'root')
    except:
        self.ilom.start_system()
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.issue('Failed to connect to Solaris')
    solaris.sendcmd('svcadm enable tcsd', log=True)
    time.sleep(20) 
    if 'online' not in solaris.sendcmd('svcs tcsd', log=True):
        online = tpm_enable(self)
        if not online:
            self.abort('can not get tcsd online')

    output = solaris.sendcmd('tpmadm status', log=True)
    if 'Platform Configuration Registers' in \
        send_command(self, solaris, 'tpmadm status', log=True):

        tpmadm_clear_owner(self)
        reset_flag = True
    solaris.sendcmd('tpmadm keyinfo', log=True)
    solaris.sendcmd('rm -rf /root/tpm-migration.dat', log=True)
    solaris.sendcmd('rm -rf /root/tpm-migration.key', log=True)
    solaris.sendcmd('rm -rf /var/tpm/system/tpm-migration.dat', log=True)
    solaris.sendcmd('rm -rf /var/tpm/system/tpm-migration.key', log=True)

    # cleanup old keys
    output = solaris.sendcmd('tpmadm keyinfo', log=True)
    for line in output.splitlines():
        key = line.split()[1]
        cmd = 'tpmadm deletekey ' + key 
        prompt = ['\[y|N\]]\?', '\[y\/N\]\?']
        solaris.sendcmd(cmd, prompt, log=True)
        solaris.sendcmd('y', log=True)

    #added because the after the next reboot the system came up disabled
    solaris.sendcmd('svcadm disable tcsd', log=True)
    time.sleep(20)
    for i in range(10):
        self.info("Polling tcsd status")
        if 'disable' in solaris.sendcmd('svcs tcsd', log=True):
            break
        time.sleep(2)
    if i == 9:
        self.info('tcsd not set to disable')
    solaris.close()
    if reset_flag or force:
        self.ilom.stop_system(force=True)
        ret = set_and_verify(self, '/HOST/tpm', forceclear='true')
        if ret:
            self.issue('TPM forceclear is {0}'.format(ret))
        self.ilom.start_system()

    self.info("Exiting factory defaults")

def tpm_init(self):

    self.info("Entering tpm_init")
    try:
        solaris = self.system.get_connection('SSH', 'HOST', 'root')
    except:
        self.ilom.start_system()
        try:
            solaris = self.system.get_connection('SSH', 'HOST', 'root')
        except:
            self.issue('Failed to connect to Solaris')

    self.info("Initialize tpm with tpmadm init")
    solaris.sendcmd('svcadm enable tcsd', log=True)
    self.info("Polling svcs tcsd")
    for i in range(10):
        if 'online' in solaris.sendcmd('svcs tcsd', log=True):
            break
        time.sleep(2)
    if i == 9:
        self.issue('tcsd not online')
        solaris.close()
        return 1
    output = send_command(self, solaris, 'tpmadm init', log=True)
    if output is None:
        self.issue("tpmadm init timed out")
        solaris.close()
        return 1
    if "Enter TPM Owner PIN" not in output:
        self.issue("missing TPM Owner PIN prompt")
        solaris.close()
        return 1
    elif "Migratable Root Key file(s) already exist" in output:
        self.issue("Migratable Root Key already exists")
        solaris.close()
        return 1
    elif "fail" in output.lower() or "error" in output.lower():
        self.issue("error, fail, or Communication failure")
        solaris.close()
        return 1
    elif solaris.prompt in output:
        self.info("tpadm init succeeded")
    output = solaris.sendcmd('tpmadm status', log=True)
    if 'Platform Configuration Registers' in output:
        self.info("tpadm init succeeded")
    else:
        self.issue('tpmadm init/status failed:' + output)
    solaris.sendcmd('tpmadm keyinfo', log=True)
    solaris.close()
    self.info("Exiting tpm_init")


def send_command(self, conn, cmd, timeout=CMD_TIMEOUT,
                                     migration_pin='', log=True):
    string = ''
    if migration_pin == 'owner':
        m_pin = OWNER_PIN
    else:
        m_pin = MIGRATION_PIN
        
    conn.sendline(cmd)
    exp_list = ['Migratable Root Key file(s) already exist',
                'Enter TPM Owner PIN:',
                'Confirm TPM Owner PIN:',
                'Enter PIN:',
                'Enter PIN for the migration key:',
                'Enter PIN for the migrated key:',
                'Confirm PIN for the migration key:',
                'TPM owner passphrase:',
                'Enter passphrase for key',
                conn.prompt, TimeoutError]
    while True:
        out = conn.sync(exp_list, timeout=timeout, debug=True, log=True,\
                                                                    after=True)
        string += out
        if conn.match_index == 0:
            conn.sendline('y')
        elif conn.match_index == 1:
            conn.sendline(OWNER_PIN)
        elif conn.match_index == 2:
            conn.sendline(OWNER_PIN)
        elif conn.match_index == 3:
            conn.sendline(OWNER_PIN)
        elif conn.match_index == 4:
            conn.sendline(m_pin)
        elif conn.match_index == 5:
            conn.sendline(OWNER_PIN)
        elif conn.match_index == 6:
            conn.sendline(m_pin)
        elif conn.match_index == 7:
            conn.sendline(PASSPHRASE)
        elif conn.match_index == 8:
            conn.sendline(PASSPHRASE)
        elif conn.match_index == 10:
            string = None
            break
        else:
            break
    if log:
        if string is None:
            self.warning(cmd + ' failed')
        else:
            self.info(string)
    return string
