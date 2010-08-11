# util.py

import threading
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
    return pack('4B', *[int(x) for x in ip_str.split('.')])
        
def decode_ip(ip_bin):
    '''Decode a 4 byte IP into a string.'''
    return '.'.join([str(x) for x in unpack('4B', ip_bin)])

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

