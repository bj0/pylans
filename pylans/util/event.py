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
# event.py
from __future__ import absolute_import
import logging
from . import get_weakref_proxy, get_weakref

logger = logging.getLogger(__name__)

class Event(object):
    '''
        An event object holds a list of callback functions that get called
        in the order they are added when fire() is called.  Return values are
        discarded.  C#-like += and -= syntax supported.
        
        Strong references to functions are held, so bound instance methods
        will keep an object from being garbage collected unless removed.
        This means that closures and lambdas are also valid.
        
    '''
    def __init__(self):
        self.handlers = []

    def handle(self, handler):
        if handler not in self.handlers:
            self.handlers.append(handler)
        else:
            logger.warning('adding same handler multiple times')
            
        return self

    def unhandle(self, handler):
        try:
            self.handlers.remove(handler)
        except IndexError:
            raise ValueError("Handler is not handling this event, "
                             + "so cannot unhandle it.")
        return self

    def fire(self, *args, **kargs):
        for handler in self.handlers:
            handler(*args, **kargs)

    def getHandlerCount(self):
        return len(self.handlers)

    __iadd__ = handle
    __isub__ = unhandle
    __call__ = fire
    __len__  = getHandlerCount

class Callback(object):
    def __init__(self, function):
        self.valid = True
        self.wfunction = get_weakref(function, self.vanished)
        
    def __call__(self, *args, **kwargs):
        f = self.wfunction()
        if f is None:
            return None
        return f(*args, **kwargs)
        
    def vanished(self, ref):
        self.valid = False        
    

class EventManager(object):
    '''
        EventManager manages events and handlers.
        
        Handlers are stored as weakrefs, so anything added with register_handler 
        will not increase the refcount.  This means that objects can be freed
        after registering a callback (it will be skipped).  This prevents 
        using lambdas or closures unless external references to them are kept.
    '''
    def __init__(self):
        self._handlers = {}

    def register_handler(self, type, obj, handler):
        _id = id(obj)

        objs = self._handlers.setdefault(type, {})
        event = objs.setdefault(_id, Event())
        
        event += Callback(handler)
        
    def unregister_handler(self, type, obj, handler):
        self._handlers[type][id(obj)] -= handler

    def emit(self, type, obj, *args, **kwargs):
        if type in self._handlers:
        
            def _do_fire(event):
                if event is not None:
                    # remove stale weakrefs
                    for cb in event.handlers:
                        if not cb.valid:
                            handlers -= cb
                    
                    event.fire(obj, *args, **kwargs)

                    logger.info('event {0} emitted to {1} handlers'
                                .format(type, len(event)))

            # fire to object specific handlers
            event = self._handlers.get(type, {}).get(id(obj), None)
            _do_fire(event)
            # fire non-specific handlers
            if obj is not None:
                event = self._handlers.get(type, {}).get(id(None), None)
                _do_fire(event)

            
                
MANAGER = EventManager()
register_handler = MANAGER.register_handler
unregister_handler = MANAGER.unregister_handler
emit = MANAGER.emit
