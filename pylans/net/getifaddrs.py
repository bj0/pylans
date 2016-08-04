#!/usr/bin/env python

from ctypes import (
    Structure, Union, POINTER,
    pointer, get_errno, cast,
    c_ushort, c_char, c_byte, c_void_p, c_char_p, c_uint, c_int, c_uint16, c_uint32
)
from socket import inet_ntop, AF_INET, AF_INET6, ntohs, ntohl
import collections
import ctypes.util
import ctypes
import pdb

IFF_LOOPBACK = 0x8
IFF_BROADCAST = 0x2

sa_family_t = c_ushort


# TODO these C structs should mention the header they're defined in

class struct_sockaddr(Structure):
    _fields_ = [
        ('sa_family', c_ushort),
        ('sa_data', c_byte * 14), ]


struct_in_addr = c_byte * 4


class struct_sockaddr_in(Structure):
    _fields_ = [
        ('sin_family', sa_family_t),
        ('sin_port', c_uint16),
        ('sin_addr', struct_in_addr)]


struct_in6_addr = c_byte * 16


class struct_sockaddr_in6(Structure):
    _fields_ = [
        ('sin6_family', c_ushort),
        ('sin6_port', c_uint16),
        ('sin6_flowinfo', c_uint32),
        ('sin6_addr', struct_in6_addr),
        ('sin6_scope_id', c_uint32)]


class union_ifa_ifu(Union):
    _fields_ = [
        ('ifu_broadaddr', POINTER(struct_sockaddr)),
        ('ifu_dstaddr', POINTER(struct_sockaddr)), ]


class struct_ifaddrs(Structure):
    pass


struct_ifaddrs._fields_ = [
    ('ifa_next', POINTER(struct_ifaddrs)),
    ('ifa_name', c_char_p),
    ('ifa_flags', c_uint),
    ('ifa_addr', POINTER(struct_sockaddr)),
    ('ifa_netmask', POINTER(struct_sockaddr)),
    ('ifa_ifu', union_ifa_ifu),
    ('ifa_data', c_void_p), ]

py_ifaddrs = collections.namedtuple('py_ifaddrs', 'name flags family addr netmask broadcast')


class struct_in_pktinfo(Structure):
    _fields_ = [
        ('ipi_ifindex', ctypes.c_uint),
        ('ipi_spec_dst', struct_in_addr),
        ('ipi_addr', struct_in_addr)]


libc = ctypes.CDLL(ctypes.util.find_library('c'))
_getifaddrs = libc.getifaddrs
_getifaddrs.restype = c_int
_getifaddrs.argtypes = [POINTER(POINTER(struct_ifaddrs))]
_freeifaddrs = libc.freeifaddrs
_freeifaddrs.restype = None
_freeifaddrs.argtypes = [POINTER(struct_ifaddrs)]


def ifap_iter(ifap):
    '''Iterate over linked list of ifaddrs'''
    ifa = ifap.contents
    while True:
        yield ifa
        if not ifa.ifa_next:
            break
        ifa = ifa.ifa_next.contents


def getfamaddr(sa):
    ''' get family address'''
    family = sa.sa_family
    addr = None
    if family == AF_INET:
        sa = cast(pointer(sa), POINTER(struct_sockaddr_in)).contents
        addr = inet_ntop(family, sa.sin_addr)
    elif family == AF_INET6:
        sa = cast(pointer(sa), POINTER(struct_sockaddr_in6)).contents
        addr = inet_ntop(family, sa.sin6_addr)
    return family, addr


def pythonize_sockaddr(sa):
    '''Convert ctypes Structure of sockaddr into the Python tuple used in the socket module'''
    family = sa.sa_family
    if family == AF_INET:
        sa = cast(pointer(sa), POINTER(struct_sockaddr_in)).contents
        addr = (
            inet_ntop(family, sa.sin_addr),
            ntohs(sa.sin_port))
    elif family == AF_INET6:
        sa = cast(pointer(sa), POINTER(struct_sockaddr_in6)).contents
        addr = (
            inet_ntop(family, sa.sin6_addr),
            ntohs(sa.sin6_port),
            ntohl(sa.sin6_flowinfo),
            sa.sin6_scope_id)
    else:
        addr = None
    return family, addr


def getifaddrs():
    '''Wraps the C getifaddrs call, returns a list of pythonic ifaddrs'''
    ifap = POINTER(struct_ifaddrs)()
    result = _getifaddrs(pointer(ifap))
    if result == -1:
        raise OSError(get_errno())
    elif result == 0:
        pass
    else:
        assert False, result
    del result
    try:
        retval = []
        for ifa in ifap_iter(ifap):
            maddr = None
            baddr = None
            family, addr = None, None
            if bool(ifa.ifa_addr):  # non-null pointer
                family, addr = pythonize_sockaddr(ifa.ifa_addr.contents)
            if bool(ifa.ifa_netmask):  # non-null pointer
                mfam, maddr = pythonize_sockaddr(ifa.ifa_netmask.contents)
            if ifa.ifa_flags & IFF_BROADCAST != 0 and bool(ifa.ifa_ifu.ifu_broadaddr):
                bfam, baddr = pythonize_sockaddr(ifa.ifa_ifu.ifu_broadaddr.contents)

            retval.append(py_ifaddrs(
                name=ifa.ifa_name,
                family=family,
                flags=ifa.ifa_flags,
                addr=addr,
                netmask=maddr,
                broadcast=baddr))
        return retval
    finally:
        _freeifaddrs(ifap)


if __name__ == '__main__':
    from pprint import pprint

    pprint(getifaddrs())
