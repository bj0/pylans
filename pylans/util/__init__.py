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
)

def emit_async(*x):
    reactor.callLater(0, event.emit, *x)
    
def sleep(secs):
    '''Twisted async sleep call'''
    d = defer.Deferred()
    reactor.callLater(secs, d.callback, None)
    return d
    
def prompt(vars, message="Entering Interactive Python Interpreter", 
        prompt="pylans", exit_msg="Returning to pylans cli"):
    '''
        Start an interactive (i)python interpreter on the commandline.
        This blocks, so don't call from twisted, but in a thread or from Cmd is fine.
        
        :param vars: variables to make available to interpreter
        :type vars: dict
    '''
    try:
        from IPython.Shell import IPShellEmbed
        ipshell = IPShellEmbed(argv=['-pi1','pylans:\\#>','-p','sh'],
            banner=message,exit_msg=exit_msg)
        return  ipshell
    except ImportError:
        ## this doesn't quite work right, in that it doesn't go to the right env
        ## so we just fail.
        import code
        import rlcompleter
        import readline
        readline.parse_and_bind("tab: complete")
        # calling this with globals ensures we can see the environment
        print message
        shell = code.InteractiveConsole(vars)
        return shell.interact

    
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
    from . import event
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

