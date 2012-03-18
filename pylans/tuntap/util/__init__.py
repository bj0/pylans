# Copyright (C) 2010  Brian Parma (execrable@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
# util.py
# utility functions

from __future__ import absolute_import
from inspect import ismethod, isfunction
from new import instancemethod
from functools import wraps
from struct import pack, unpack
import subprocess as sp
import shlex
import socket
import threading
import weakref
import logging
from binascii import hexlify, unhexlify

from .weakref import get_weakref_proxy, get_weakref

logger = logging.getLogger(__name__)

def encode_mac(mac_str):
    '''Encode a string MAC address into 6 bytes.
    
    >>> encode_mac('0a:00:27:00:00:00').encode('hex')
    '0a0027000000'
    '''
    return pack('6B', *[int(x,16) for x in mac_str.split(':')])

def decode_mac(mac_bin):
    '''Decode a 6 byte MAC address into a string.
    
    >>> decode_mac('0a0027000000'.decode('hex'))
    '0a:00:27:00:00:00'
    '''
    return ':'.join(['{0:02x}'.format(x) for x in unpack('6B', mac_bin)])


def encode_ip(ip_str):
    '''Encode a string IP into 4 bytes.
    
    >>> encode_ip('192.1.128.3').encode('hex')
    'c0018003'
    '''
    return socket.inet_aton(ip_str)
        
def decode_ip(ip_bin):
    '''Decode a 4 byte IP into a string.
    
    >>> decode_ip('c0018003'.decode('hex'))
    '192.1.128.3'
    '''
    return socket.inet_ntoa(ip_bin)

def threaded(f):
    """
        A decorator that will make any function run in a new thread
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=f, args=args, kwargs=kwargs)
        t.daemon = True
        t.start()

    return wrapper


def ip_atol(ip_str):
    '''Encode a string IP into a long integer
    
    >>> ip_atol('10.1.2.15')
    167838223
    '''
    ipn = encode_ip(ip_str)
    return unpack('!L',ipn)[0]
    
def ip_ltoa(ip_long):
    '''Decode a long integer into a string IP
    
    >>> ip_ltoa(167838223)
    '10.1.2.15'
    '''
    ipn = pack('!L',ip_long)
    return decode_ip(ipn)
    
def ip_to_net_host_subnet(addr_str, mask=None):
    '''Takes an address in either 'X.X.X.X/Mask' or with mask passed separately,
    and returns (net, host, subnet).
    
    >>> ip_to_net_host_subnet('10.1.3.5/24')
    ('0.0.0.5', '10.1.3.0', '255.255.255.0')
    
    >> ip_to_net_host_subnet('10.1.3.5', 24)
    ('0.0.0.5', '10.1.3.0', '255.255.255.0')
    '''
    if mask is not None:
        if isinstance(mask, str):
            mask = long(mask)
        
    else:
        addr_str, mask = addr_str.split('/')
        mask = long(mask)
        #check mask
    
    mask = (1L<<(32-mask))-1
    add = ip_atol(addr_str)

    net = add & mask
    host = add - net
    
    return (ip_ltoa(net), ip_ltoa(host), ip_ltoa(0xFFFFFFFF-mask))


def enum(name, _type, *lst, **enums):
    '''
        Dynamically create enum-like class
        
        :param name: name of the class
        
        :param _type: inherited base class (like int)
        
        :param *lst: list of names to enumerate (ie: ONE, TWO)
        
        :param **enums: dict enumerations (ie: ONE=1,TWO=2)
    '''
    def _new(cls, k, v):
        obj = super(T, cls).__new__(cls, v)
        obj._name = k
        return obj

    def _repr(self):
        return '<enum {0}={3} of type {1}({2})>'.format(self._name, name,
                                                _type.__name__, _type(self))
        
    @staticmethod
    def add(*lst, **enums):
        vals = list(T._enums.keys())
        for key,val in enums.items():
            if val in vals:
                raise ValueError, "{0}'s value {1} already assigned to {2}"\
                                .format(key, val, T._enums[val])
            T._enums[val] = key
            setattr(T, key, T(key,val))
            vals.append(val)
        mx = max(vals+[0,])
        for key in lst:
            val = mx+1
            T._enums[val] = key
            setattr(T, key, T(key,val))
            vals.append(val)
            mx = val

    T = type(name, (_type,), {'__new__':_new,
                              '__repr__':_repr,
                              'add':add})
            
    T._enums = {}
    T.add(*lst, **enums)                       
    
    return T



if __name__ == '__main__':
    import doctest
    doctest.testmod()
