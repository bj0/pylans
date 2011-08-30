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

import logging
import util

logger = logging.getLogger(__name__)

class Event:
    def __init__(self):
        self.handlers = set()

    def handle(self, handler):
        '''Stores weakrefs to bound methods to allow gc'''
        self.handlers.add(util.get_weakref_proxy(handler))
        return self

    def unhandle(self, handler):
        try:
            self.handlers.remove(util.get_weakref_proxy(handler))
        except IndexError:
            raise ValueError("Handler is not handling this event, so cannot unhandle it.")
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

class EventManager(object):

    def __init__(self):
        self._handlers = {}

    def register_handler(self, type, obj, handler):
        _id = id(obj)

        if type not in self._handlers:
            self._handlers[type] = {}
            self._handlers[type][id(None)] = Event()

        if _id not in self._handlers[type]:
            self._handlers[type][_id] = Event()

        self._handlers[type][_id] += handler

    def unregister_handler(self, type, obj, handler):
        self._handlers[type][id(obj)] -= handler

    def emit(self, type, obj, *args, **kwargs):
        if type in self._handlers:
            if obj is not None and \
             id(obj) in self._handlers[type]:
                self._handlers[type][id(obj)](obj, *args, **kwargs)

            self._handlers[type][id(None)](obj, *args, **kwargs)
            logger.info('event {0} emitted to {1} handlers'.format(type, len(self._handlers[type])))

MANAGER = EventManager()
register_handler = MANAGER.register_handler
unregister_handler = MANAGER.unregister_handler
emit = MANAGER.emit
