# util.py

import threading
import socket
from struct import pack, unpack
from functools import wraps

def encode_mac(mac_str):
    '''Encode a string MAC address into 6 bytes.'''
    return pack('6B', *[int(x) for x in mac_str.split(':')])

def decode_mac(mac_bin):
    '''Decode a 6 byte MAC address into a string.'''
    return ':'.join([str(x) for x in unpack('6B', mac_bin)])


def encode_ip(ip_str):
    '''Encode a string IP into 4 bytes.'''
    return socket.inet_aton(ip_str)
        
def decode_ip(ip_bin):
    '''Decode a 4 byte IP into a string.'''
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
    ipn = encode_ip(ip_str)
    return unpack('!L',ipn)[0]
    
def ip_ltoa(ip_long):
    ipn = pack('!L',ip_long)
    return decode_ip(ipn)
    
def ip_to_net_host_subnet(addr_str, mask=None):
    '''Takes an address in either 'X.X.X.X/Mask' or with mask passed separately,
    and returns (net, host, subnet).'''
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
    
