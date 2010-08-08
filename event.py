
import logging

logger = logging.getLogger(__name__)

class Event:
    def __init__(self):
        self.handlers = set()

    def handle(self, handler):
        self.handlers.add(handler)
        return self

    def unhandle(self, handler):
        try:
            self.handlers.remove(handler)
        except:
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
