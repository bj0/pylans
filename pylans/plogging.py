from __future__ import absolute_import
import logging

short_format = \
'[%(levelname)-10s]: \"%(message)s\"'
long_format = \
'%(asctime)s:[%(levelname)-10s]>%(name)s:<%(funcName)s>::=> \"%(message)s\"'

class BraceMessage(object):
    '''BraceMessage from logutils'''
    def __init__(self, fmt, *args, **kwargs):
        self.fmt = fmt
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        return self.fmt.format(*self.args, **self.kwargs)

#exaile's (modified) magic
class FilterLogger(logging.Logger):
    '''A simple logger class that supports filtering'''
    class ReFilter(logging.Filter):
        '''A regex based filter for logging'''
        def filter(self, record):
            msg = record.getMessage()
            def check(s):
                '''function for checking if s is in record'''
                return s.search(''.join((msg,
                                    record.name,
                                    record.levelname,
                                    record.funcName))) is not None
                    
            # first show only stuff that passes filter
            if settings.FILTER:
                for s in settings.FILTER:
                    if check(s):
                        break
                else:
                    return False
            
            # second, ignore stuff that passed filter if it's in ignore
            if settings.IGNORE:
                for s in settings.IGNORE:
                    if check(s):
                        return False
            
            return True
            

    level = logging.NOTSET

    def __init__(self, name):
        logging.Logger.__init__(self, name)

        log_filter = self.ReFilter(name)
        log_filter.level = FilterLogger.level
        self.addFilter(log_filter)
        logging.addLevelName(100, 'ALWAYS')
        logging.addLevelName(5, 'TRACE')

    def always(self, *args, **kwargs):
        self.log(100, *args, **kwargs)

    def trace(self, *args, **kwargs):
        if self.level > 5:
            self.log(5, BraceMessage(*args, **kwargs))

    def warning(self, *args, **kwargs):
        if self.level > logging.WARNING:
            super(FilterLogger, self).warning(BraceMessage(*args, **kwargs))
        
    def warn(self, *args, **kwargs):
        if self.level > logging.WARNING:
            super(FilterLogger, self).warn(BraceMessage(*args, **kwargs))

    def error(self, *args, **kwargs):
        if self.level > logging.ERROR:
            super(FilterLogger, self).error(BraceMessage(*args, **kwargs))
        
    def debug(self, *args, **kwargs):
        if self.level > logging.DEBUG:
            super(FilterLogger, self).debug(BraceMessage(*args, **kwargs))
        
    def fatal(self, *args, **kwargs):
        if self.level > logging.FATAL:
            super(FilterLogger, self).fatal(BraceMessage(*args, **kwargs))
        
    def critical(self, *args, **kwargs):
        if self.level > logging.CRITICAL:
            super(FilterLogger, self).critical(BraceMessage(*args, **kwargs))
        
        

def short():
    '''switch to short logging format'''
    logging.getLogger().handlers[0].setFormatter(
                        logging.Formatter(short_format))

def long():
    '''switch to long logging format'''
    logging.getLogger().handlers[0].setFormatter(
                        logging.Formatter(long_format))

# replace default logging class with our filtered variant
logging.setLoggerClass(FilterLogger)

# settings instantiates a logger (so we setLoggerClass first)
from . import settings

# non-persistant global settings
settings.FILTER = []
settings.IGNORE = []

logging.basicConfig(level=settings.get_option('settings/loglevel', 40),
    format=long_format)

def _new_exc_handler(exc_type, exc_value, exc_traceback):
    '''log unhandled exceptions'''
    import traceback
    logger = logging.getLogger('unhandled exception')
    logger.always(''.join(traceback.format_exception(exc_type, exc_value, 
                                                        exc_traceback)))
        
    _exc_handler(exc_type, exc_value, exc_traceback)
    
import sys    
_exc_handler, sys.excepthook = sys.excepthook ,_new_exc_handler
