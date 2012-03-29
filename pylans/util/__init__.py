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
from twisted.internet.utils import getProcessOutput
from twisted.internet import defer, reactor
from struct import pack, unpack
import subprocess as sp
import shlex
import socket
import threading
import logging
from binascii import hexlify, unhexlify

logger = logging.getLogger(__name__)

from ..tuntap.util import (
    encode_mac,
    decode_mac,
    encode_ip,
    decode_ip,
    threaded,
    ip_atol,
    ip_ltoa,
    ip_to_net_host_subnet,
    get_weakref_proxy,
    get_weakref
)

#from .weakref import get_weakref_proxy

from .ipshell import shell

def emit_async(*x):
    reactor.callLater(0, event.emit, *x)
    
def sleep(secs):
    '''Twisted async sleep call'''
    d = defer.Deferred()
    reactor.callLater(secs, d.callback, None)
    return d

    
def run_cmd(cmd):
    '''
        Run an external command/program using twisted's getProcessOutput
    
        :param cmd: a string of the command to run.
    '''
    if isinstance(cmd, list):
        # command already split up for subprocess
        pass
    elif isinstance(cmd, str):
        # command all in one string
        cmd = shlex.split(cmd)
    else:
        raise ValueError, "invalid cmd parameter, require string or list"
    
    logger.debug('running command: {0}'.format(cmd))
    return getProcessOutput(cmd[0], cmd[1:])
    
@defer.inlineCallbacks
def run_cmds(cmds):
    '''Run multiple command/programs.'''
    res = []
    for cmd in cmds:
        ret = yield run_cmd(cmd)
        res.append(ret)
    defer.returnValue(res)

def enum(name, _type, *lst, **enums):
    '''
        Dynamically create enum-like class
        
        :param name: name of the class
        
        :param _type: inherited base class (like int)
        
        :param *lst: list of names to enumerate (ie: ONE, TWO)
        
        :param **enums: dict enumerations (ie: ONE=1,TWO=2)
    '''
    
    class Type(type):
        '''
            metaclass for new enum type, to support casting
        '''
        def __call__(cls, *args):
            if len(args) > 1:
                return super(Type, cls).__call__(*args)
            else:
                x = args[0]
                if isinstance(x, str):
                    if x in T._enums.values():
                        return getattr(T, x)
                    else:
                        return _type(x)
                elif isinstance(x, _type):
                    return getattr(T, T._enums[x])
                else:
                    raise TypeError("invalid argument type, must be str or {0}"
                                        .format(_type.__name__))

                    
    def _new(cls, k, v):
        obj = super(T, cls).__new__(cls, v)
        obj._name = k
        return obj

    def _str(self):
        return self._name
        
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

    T = Type(name, (_type,), {'__new__':_new,
#                              '__metaclass__':Meta,
                              '__str__':_str,
                              '__repr__':_repr,
                              'add':add})
            
    T._enums = {}
    T.add(*lst, **enums)                       
    
    return T

@defer.inlineCallbacks
def retry_func(fun, args, kwargs=None, tries=3, delay=0):
    '''Retry a deferred function until it succeeds or fails 'tries' times.'''
    if kwargs is None:
        kwargs = {}
    i = 1
    while True:
        try:
            x = yield fun(*args, **kwargs)
            defer.returnValue(x)
        except Exception, e:
            if i == tries:
                raise
            i += 1
            if delay > 0:
                yield sleep(delay)



if __name__ == '__main__':
    import doctest
    doctest.testmod()

