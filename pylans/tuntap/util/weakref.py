from __future__ import absolute_import
import weakref
from types import MethodType
from inspect import ismethod
import logging

logger = logging.getLogger(__name__)

_DEBUG_REFS = True

def _debug_refs(ref):
    if _DEBUG_REFS:
        logger.debug('weakref referant {0} died.'.format(repr(ref)))
    
def _debug_refs_wrapper(f):
    def new_f(ref):
        _debug_refs(ref)
        f(ref)
    return new_f



class _WeakMethod(object):
    """
        Represent a weak bound method, i.e. a method doesn't keep alive the
    object that it is bound to. It uses WeakRef which, used on its own,
    produces weak methods that are dead on creation, not very useful.
    Typically, you will use the getRef() function instead of using
    this class directly. 
    
        Strong refs are kept to unbound methods, this keeps alive lambdas
    and locally defined functions (closures), but if a closure or lambda
    references an object, that object is kept alive too. TODO
    
    """

    def __init__(self, method, notifyDead = None):
        """
            The method must be bound. notifyDead will be called when
            object that method is bound to dies.
        """
        
        try:
            if method.im_self is not None:
                if notifyDead is None:
                    self.objRef = weakref.ref(method.im_self)
                else:
                    self.objRef = weakref.ref(method.im_self, notifyDead)
            else:
                # unbound method
                raise ValueError
            self.fun = method.im_func
            self.cls = method.im_class
            
        except AttributeError:
            # not a method            
            logger.error('_WeakMethod can only reference methods', exc_info=True)
            raise ValueError
        
    def __call__(self):
        obj = self.objRef()                 # prevent race conditions
        if obj is not None:
            # create instancemethod for bound method
            return MethodType(self.fun, obj, self.cls)
        else:
            return None
            
    def __eq__(self, method2):
        try:
            return      self.fun      is method2.fun \
                    and self.objRef() is method2.objRef() \
                    and self.objRef() is not None
        except:
            return False

    def __hash__(self):
        return hash(self.fun)

    def __repr__(self):
        dead = ''
        if self.objRef() is None:
            dead = '; DEAD'
        obj = '<%s at %s%s>' % (self.__class__, id(self), dead)
        return obj

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
            return f1 == f2
        except:
            return False

def get_weakref(obj, notifyDead=None):
    if ismethod(obj):
        createRef = _WeakMethod
    else:
        createRef = weakref.ref
        
    if notifyDead is None:
        return createRef(obj, _debug_refs)
    else:
        return createRef(obj, _debug_refs_wrapper(notifyDead))
           

def get_weakref_proxy(obj, notifyDead=None):
    """
        Get a weak reference to obj. If obj is a bound method, a _WeakMethod
        object, that behaves like a WeakRef, is returned, if it is
        anything else a WeakRef is returned. If obj is an unbound method,
        a ValueError will be raised.
    """
#    from . import event
    if ismethod(obj):
        createRef = _WeakMethodProxy
    else:
        createRef = weakref.proxy

    if notifyDead is None:
        return createRef(obj, _debug_refs)
    else:
        return createRef(obj, _debug_refs_wrapper(notifyDead))

