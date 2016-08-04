#  For the sake of humanity here's a python script retrieving
#  ip information of the network interfaces.
#
#  Pay some tribute to my soul cause I lost a few years on this one
#
#  Based on code from jaraco and many other attempts
#  on internet
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

# modified for pylans
# * Brian Parma

import ctypes
import struct
# import ipaddress
import ctypes.wintypes
from ctypes.wintypes import DWORD, WCHAR, BYTE, BOOL
from socket import AF_INET

# from iptypes.h
import collections

MAX_ADAPTER_ADDRESS_LENGTH = 8
MAX_DHCPV6_DUID_LENGTH = 130

GAA_FLAG_INCLUDE_PREFIX = ctypes.c_ulong(0x0010)


class SOCKADDR(ctypes.Structure):
    _fields_ = [
        ('family', ctypes.c_ushort),
        ('data', ctypes.c_byte * 14),
    ]


LPSOCKADDR = ctypes.POINTER(SOCKADDR)


class SOCKET_ADDRESS(ctypes.Structure):
    _fields_ = [
        ('address', LPSOCKADDR),
        ('length', ctypes.c_int),
    ]


class _IP_ADAPTER_ADDRESSES_METRIC(ctypes.Structure):
    _fields_ = [
        ('length', ctypes.c_ulong),
        ('interface_index', DWORD),
    ]


class _IP_ADAPTER_ADDRESSES_U1(ctypes.Union):
    _fields_ = [
        ('alignment', ctypes.c_ulonglong),
        ('metric', _IP_ADAPTER_ADDRESSES_METRIC),
    ]


class IP_ADAPTER_UNICAST_ADDRESS(ctypes.Structure):
    pass


PIP_ADAPTER_UNICAST_ADDRESS = ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)
IP_ADAPTER_UNICAST_ADDRESS._fields_ = [
    ("length", ctypes.c_ulong),
    ("flags", ctypes.wintypes.DWORD),
    ("next", PIP_ADAPTER_UNICAST_ADDRESS),
    ("address", SOCKET_ADDRESS),
    ("prefix_origin", ctypes.c_int),
    ("suffix_origin", ctypes.c_int),
    ("dad_state", ctypes.c_int),
    ("valid_lifetime", ctypes.c_ulong),
    ("preferred_lifetime", ctypes.c_ulong),
    ("lease_lifetime", ctypes.c_ulong),
    ("on_link_prefix_length", ctypes.c_ubyte)
]


# it crashes when retrieving prefix data :(
class IP_ADAPTER_PREFIX(ctypes.Structure):
    pass


PIP_ADAPTER_PREFIX = ctypes.POINTER(IP_ADAPTER_PREFIX)
IP_ADAPTER_PREFIX._fields_ = [
    ("alignment", ctypes.c_ulonglong),
    ("next", PIP_ADAPTER_PREFIX),
    ("address", SOCKET_ADDRESS),
    ("prefix_length", ctypes.c_ulong)
]


class IP_ADAPTER_ADDRESSES(ctypes.Structure):
    pass


LP_IP_ADAPTER_ADDRESSES = ctypes.POINTER(IP_ADAPTER_ADDRESSES)

# for now, just use void * for pointers to unused structures
PIP_ADAPTER_ANYCAST_ADDRESS = ctypes.c_void_p
PIP_ADAPTER_MULTICAST_ADDRESS = ctypes.c_void_p
PIP_ADAPTER_DNS_SERVER_ADDRESS = ctypes.c_void_p
# PIP_ADAPTER_PREFIX = ctypes.c_void_p
PIP_ADAPTER_WINS_SERVER_ADDRESS_LH = ctypes.c_void_p
PIP_ADAPTER_GATEWAY_ADDRESS_LH = ctypes.c_void_p
PIP_ADAPTER_DNS_SUFFIX = ctypes.c_void_p

IF_OPER_STATUS = ctypes.c_uint  # this is an enum, consider http://code.activestate.com/recipes/576415/
IF_LUID = ctypes.c_uint64

NET_IF_COMPARTMENT_ID = ctypes.c_uint32
GUID = ctypes.c_byte * 16
NET_IF_NETWORK_GUID = GUID
NET_IF_CONNECTION_TYPE = ctypes.c_uint  # enum
TUNNEL_TYPE = ctypes.c_uint  # enum

IP_ADAPTER_ADDRESSES._fields_ = [
    # ('u', _IP_ADAPTER_ADDRESSES_U1),
    ('length', ctypes.c_ulong),
    ('interface_index', DWORD),
    ('next', LP_IP_ADAPTER_ADDRESSES),
    ('adapter_name', ctypes.c_char_p),
    ('first_unicast_address', PIP_ADAPTER_UNICAST_ADDRESS),
    ('first_anycast_address', PIP_ADAPTER_ANYCAST_ADDRESS),
    ('first_multicast_address', PIP_ADAPTER_MULTICAST_ADDRESS),
    ('first_dns_server_address', PIP_ADAPTER_DNS_SERVER_ADDRESS),
    ('dns_suffix', ctypes.c_wchar_p),
    ('description', ctypes.c_wchar_p),
    ('friendly_name', ctypes.c_wchar_p),
    ('byte', BYTE * MAX_ADAPTER_ADDRESS_LENGTH),
    ('physical_address_length', DWORD),
    ('flags', DWORD),
    ('mtu', DWORD),
    ('interface_type', DWORD),
    ('oper_status', IF_OPER_STATUS),
    ('ipv6_interface_index', DWORD),
    ('zone_indices', DWORD),
    ('first_prefix', PIP_ADAPTER_PREFIX),
    ('transmit_link_speed', ctypes.c_uint64),
    ('receive_link_speed', ctypes.c_uint64),
    ('first_wins_server_address', PIP_ADAPTER_WINS_SERVER_ADDRESS_LH),
    ('first_gateway_address', PIP_ADAPTER_GATEWAY_ADDRESS_LH),
    ('ipv4_metric', ctypes.c_ulong),
    ('ipv6_metric', ctypes.c_ulong),
    ('luid', IF_LUID),
    ('dhcpv4_server', SOCKET_ADDRESS),
    ('compartment_id', NET_IF_COMPARTMENT_ID),
    ('network_guid', NET_IF_NETWORK_GUID),
    ('connection_type', NET_IF_CONNECTION_TYPE),
    ('tunnel_type', TUNNEL_TYPE),
    ('dhcpv6_server', SOCKET_ADDRESS),
    ('dhcpv6_client_duid', ctypes.c_byte * MAX_DHCPV6_DUID_LENGTH),
    ('dhcpv6_client_duid_length', ctypes.c_ulong),
    ('dhcpv6_iaid', ctypes.c_ulong),
    ('first_dns_suffix', PIP_ADAPTER_DNS_SUFFIX),
]


def GetAdaptersAddresses():
    """
    Returns an iteratable list of adapters
    """
    size = ctypes.c_ulong()
    GetAdaptersAddresses = ctypes.windll.iphlpapi.GetAdaptersAddresses
    GetAdaptersAddresses.argtypes = [
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.POINTER(IP_ADAPTER_ADDRESSES),
        ctypes.POINTER(ctypes.c_ulong),
    ]
    GetAdaptersAddresses.restype = ctypes.c_ulong
    res = GetAdaptersAddresses(AF_INET, 0, None, None, size)
    if res != 0x6f:  # BUFFER OVERFLOW
        raise RuntimeError("Error getting structure length (%d)" % res)
    pointer_type = ctypes.POINTER(IP_ADAPTER_ADDRESSES)
    size.value = 15000
    buffer = ctypes.create_string_buffer(size.value)
    struct_p = ctypes.cast(buffer, pointer_type)
    res = GetAdaptersAddresses(AF_INET, 0, None, struct_p, size)
    if res != 0x0:  # NO_ERROR:
        raise RuntimeError("Error retrieving table (%d)" % res)
    while struct_p:
        yield struct_p.contents
        struct_p = struct_p.contents.next


py_ifaddrs = collections.namedtuple('py_ifaddrs',
                                    'name description type family addr netmask network broadcast physical mask_len')


def get_addrs():
    # todo: fix for mutliple addresses per interface
    import ipaddress
    result = {}
    for i in GetAdaptersAddresses():
        fu = i.first_unicast_address.contents
        ad = fu.address.address.contents
        ip_int = struct.unpack('>2xI8x', ad.data)[0]
        ip = ipaddress.IPv4Address(ip_int)
        ip_if = ipaddress.IPv4Interface(u"{0}/{1}".format(ip, fu.on_link_prefix_length))

        yield py_ifaddrs(
            name=i.adapter_name,
            description=i.description,
            type=i.interface_type,
            family=ad.family,
            addr=str(ip),
            netmask=str(ip_if.netmask),
            network=str(ip_if.network.network_address),
            broadcast=str(ip_if.network.broadcast_address),
            physical=':'.join('{0:02x}'.format(x & 0xff) for x in i.byte[:6]),
            mask_len=fu.on_link_prefix_length
        )


def get_win_ifaddrs():
    """
    A method for retrieving (and displaying) info of the network
    interfaces. Returns a nested dictionary of
    interfaces in Windows. Currently supports
    only IPv4 interfaces
    """
    import ipaddress
    result = {}
    for i in GetAdaptersAddresses():
        print("--------------------------------------")
        print("IF: {0}".format(i.description))
        print('\tadapter ({}): {}'.format(i.interface_index, i.adapter_name))
        print("\tdns_suffix: {0}".format(i.dns_suffix))
        print("\tinterface type: {0}".format(i.interface_type))
        print('\tphysical: {}'.format(':'.join('{0:02x}'.format(x & 0xff) for x in i.byte[:6])))
        fu = i.first_unicast_address.contents
        ad = fu.address.address.contents
        print("\tfamily: {0}".format(ad.family))
        ip_int = struct.unpack('>2xI8x', ad.data)[0]
        ip = ipaddress.IPv4Address(ip_int)
        ip_if = ipaddress.IPv4Interface(u"{0}/{1}".format(ip, fu.on_link_prefix_length))
        print("\tipaddress: {0}".format(ip))
        print("\tnetmask: {0}".format(ip_if.netmask))
        print("\tnetwork: {0}".format(ip_if.network.network_address))
        print("\tbroadcast: {0}".format(ip_if.network.broadcast_address))
        print("\tmask length: {0}".format(fu.on_link_prefix_length))
        d = {}
        d['addr'] = "{0}".format(ip)
        d['netmask'] = "{0}".format(ip_if.netmask)
        d['broadcast'] = "{0}".format(ip_if.network.broadcast_address)
        d['network'] = "{0}".format(ip_if.network.network_address)
        result[i.description] = {ad.family: d}
    return result


if __name__ == "__main__":
    from json import dumps

    get_win_ifaddrs()

    print(dumps([vars(x) for x in get_addrs()], indent=2))
