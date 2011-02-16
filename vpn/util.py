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

from inspect import ismethod, isfunction
from new import instancemethod
from functools import wraps
from struct import pack, unpack
import socket
import threading
import weakref
import event

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
    
    
    
def get_adapters_info():
    '''Function for Getting the Address Information for local Network Interfaces in Windows
        * most of this is from an answer at: http://stackoverflow.com/questions/166506/finding-local-ip-addresses-in-python
    '''
    from ctypes import Structure, windll, sizeof
    from ctypes import POINTER, byref
    from ctypes import c_ulong, c_uint, c_ubyte, c_char
    
    #
    # setup ctypes definitions
    #
    MAX_ADAPTER_DESCRIPTION_LENGTH = 128
    MAX_ADAPTER_NAME_LENGTH = 256
    MAX_ADAPTER_ADDRESS_LENGTH = 8
    
    class IP_ADDR_STRING(Structure):
        pass
        
    LP_IP_ADDR_STRING = POINTER(IP_ADDR_STRING)
    IP_ADDR_STRING._fields_ = [
        ("next", LP_IP_ADDR_STRING),
        ("ipAddress", c_char * 16),
        ("ipMask", c_char * 16),
        ("context", c_ulong)]
        
    class IP_ADAPTER_INFO (Structure):
        pass
        
    LP_IP_ADAPTER_INFO = POINTER(IP_ADAPTER_INFO)
    IP_ADAPTER_INFO._fields_ = [
        ("next", LP_IP_ADAPTER_INFO),
        ("comboIndex", c_ulong),
        ("adapterName", c_char * (MAX_ADAPTER_NAME_LENGTH + 4)),
        ("description", c_char * (MAX_ADAPTER_DESCRIPTION_LENGTH + 4)),
        ("addressLength", c_uint),
        ("address", c_ubyte * MAX_ADAPTER_ADDRESS_LENGTH),
        ("index", c_ulong),
        ("type", c_uint),
        ("dhcpEnabled", c_uint),
        ("currentIpAddress", LP_IP_ADDR_STRING),
        ("ipAddressList", IP_ADDR_STRING),
        ("gatewayList", IP_ADDR_STRING),
        ("dhcpServer", IP_ADDR_STRING),
        ("haveWins", c_uint),
        ("primaryWinsServer", IP_ADDR_STRING),
        ("secondaryWinsServer", IP_ADDR_STRING),
        ("leaseObtained", c_ulong),
        ("leaseExpires", c_ulong)]
        
    GetAdaptersInfo = windll.iphlpapi.GetAdaptersInfo
    GetAdaptersInfo.restype = c_ulong
    GetAdaptersInfo.argtypes = [LP_IP_ADAPTER_INFO, POINTER(c_ulong)]
    
    adapter_list = (IP_ADAPTER_INFO * 10)()
    buflen = c_ulong(sizeof(adapter_list))
    
    # Make the API call
    rc = GetAdaptersInfo(byref(adapter_list[0]), byref(buflen))
    
    def iter_list(node):
        '''Turn a returned linked-list into a generator'''
        while node:
            yield node
            node = node.next

    # Parse the output into a more usable form dict of dicts    
    adapters = {}
    if rc == 0:
        for a in adapter_list:
            if a.adapterName == '':
                continue
            ad_info = {}
            ad_info['adapterName'] = a.adapterName
            ad_info['address'] = ':'.join('%x'%i for i in a.address[:a.addressLength])
            ad_info['addressLength'] = a.addressLength
            ad_info['comboIndex'] = a.comboIndex
            ad_info['currentIpAddress'] = (a.currentIpAddress.ipAddress, a.currentIpAddress.ipMask) if a.currentIpAddress else None
            ad_info['description'] = a.description
            ad_info['dhcpEnabled'] = bool(a.dhcpEnabled)
            ad_info['dhcpServer'] = (a.dhcpServer.ipAddress, a.dhcpServer.ipMask) if a.dhcpServer else None
            ad_info['gatewayList'] = [(node.ipAddress, node.ipMask) for node in iter_list(a.gatewayList)]
            ad_info['haveWins'] = bool(a.haveWins)
            ad_info['index'] = a.index
            ad_info['ipAddressList'] = [(node.ipAddress, node.ipMask) for node in iter_list(a.ipAddressList)]
            ad_info['leaseExpires'] = a.leaseExpires
            ad_info['leaseObtained'] = a.leaseObtained
            ad_info['next'] = a.next
            ad_info['primaryWinsServer'] = (a.primaryWinsServer.ipAddress, a.primaryWinsServer.ipMask) if a.primaryWinsServer else None
            ad_info['type'] = a.type
            
            adapters[ad_info['adapterName']] = ad_info
            
    return adapters


class _WeakMethod:
    """Represent a weak bound method, i.e. a method doesn't keep alive the
    object that it is bound to. It uses WeakRef which, used on its own,
    produces weak methods that are dead on creation, not very useful.
    Typically, you will use the getRef() function instead of using
    this class directly. """

    def __init__(self, method, notifyDead = None):
        """
            The method must be bound. notifyDead will be called when
            object that method is bound to dies.
        """
#        assert ismethod(method)

        try:
            if method.im_self is not None:
                if notifyDead is None:
                    self.objRef = weakref.ref(method.im_self)
                else:
                    self.objRef = weakref.ref(method.im_self, notifyDead)
            else:
                # unbound method
                self.objRef = None
            self.fun = method.im_func
            self.cls = method.im_class
        except AttributeError:
            # not a method            
            self.objRef = None
            self.fun = method
            self.cls = None

    def is_dead(self):
        return self.objRef is not None and self.objRef() is None
        
    def __call__(self):
        if self.is_dead():
            #raise ReferenceError, "weakref points to dead object"
            return None
        elif self.objRef is not None:
            # create instancemethod for bound method
            meth = instancemethod(self.fun, self.objRef(), self.cls)
        else:
            # unbound method
            meth = self.fun
        return meth

    def __eq__(self, method2):
        try:
            return      self.fun      is method2.fun \
                    and self.objRef() == method2.objRef() 
#                    and self.objRef() is not None
        except:
            return False

    def __hash__(self):
        return hash(self.fun)

#    def __repr__(self):
#        dead = ''
#        if self.objRef() is None:
#            dead = '; DEAD'
#        obj = '<%s at %s%s>' % (self.__class__, id(self), dead)
#        return obj

    def refs(self, weakRef):
        """Return true if we are storing same object referred to by weakRef."""
        return self.objRef == weakRef
        
class _WeakMethodProxy(_WeakMethod):
    def __call__(self, *args, **kwargs):
        fun = _WeakMethod.__call__(self)
        if fun is None:
            raise ReferenceError, "object is dead"
        else:
            return fun(*args, **kwargs)
        
    def __eq__(self, other):
        try:
            f1 = _WeakMethod.__call__(self)
            f2 = _WeakMethod.__call__(other)
            return type(f1) == type(f2) and f1 == f2
        except:
            return False
            
#    def __getattr__(self, attr):
#        return getattr(self.objRef(), attr)
        
#    def __setattr__(self, attr, value):
#        setattr(self.objRef(), attr, value)

#class _WeakFunctionProxy:
#    def __init__(self, obj):
#        if not isfunction(obj):
#            raise ValueError, "obj must be a function"
#            
#        self.objRef = weakref.ref(obj)
#        self._hash = hash(obj)
#        
#    def __call__(self, *args, **kwargs):
#        if self.objRef is not None and self.objRef is None:
#            raise
#        
#    def __hash__(self):
#        return self._hash

def get_weakref_proxy(obj, notifyDead=None):
    """
        Get a weak reference to obj. If obj is a bound method, a _WeakMethod
        object, that behaves like a WeakRef, is returned, if it is
        anything else a WeakRef is returned. If obj is an unbound method,
        a ValueError will be raised.
    """
    if ismethod(obj) or isfunction(obj) or isinstance(obj, event.Event):
        createRef = _WeakMethodProxy
#    elif isfunction(obj) or isinstance(obj, e:
##        createRef = _WeakFunctionProxy
#        return obj # if it's a normal function, don't bother with weakrefs
    else:
        createRef = weakref.proxy

    if notifyDead is None:
        return createRef(obj)
    else:
        return createRef(obj, notifyDead)


if __name__ == '__main__':
    import doctest
    doctest.testmod()
