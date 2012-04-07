from __future__ import absolute_import
import logging

short_format = '[%(levelname)-10s]: \"%(message)s\"'
long_format = '%(asctime)s:[%(levelname)-10s]>%(name)s:<%(funcName)s>::=> \"%(message)s\"'

#exaile's (modified) magic
class FilterLogger(logging.Logger):
    '''A simple logger class that supports filtering'''
    class Filter(logging.Filter):
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

        log_filter = self.Filter(name)
        log_filter.level = FilterLogger.level
        self.addFilter(log_filter)
        logging.addLevelName(100, 'ALWAYS')
        logging.addLevelName(5, 'TRACE')

    def always(self, msg):
        self.log(100, msg)

    def trace(self, msg):
        self.log(5, msg)
        

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

