SYSTEMS = []

class System(object):
    """System object

    :ivar str os_ipaddr: The address of the host.
    :ivar str os_username: The username of the host.
    :ivar str os_password: The password of the host.
    :ivar str sp_ipaddr: The address of the sp.
    :ivar str sp_username: The username of the sp.
    :ivar str sp_password: The password of the sp.
    :param str os_ipaddr: The address of the host.
    :param str os_username: The username of the host.
    :param str os_password: The password of the host.
    :param str sp_ipaddr: The address of the sp.
    :param str sp_username: The username of the sp.
    :param str sp_password: The password of the sp.
    """

    def __init__(self, os_ip, os_username, os_password, 
                  sp_ip, sp_username, sp_password):
        self.os_ipaddr = os_ip
        self.os_username = os_username
        self.os_password = os_password
        self.sp_ipaddr = sp_ip
        self.sp_username = sp_username
        self.sp_password = sp_password

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
    system = SYSTEMS[index]
    return system

