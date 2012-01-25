#!/usr/bin/python

import platform
import sys
import os
import optparse
import logging

# make sure settings file is here
from . import settings

# py2exe TODO: fix this, it's breaking the path in windows
#if platform.system() == 'Windows':
#    __file__ = sys.argv[0]

# Find out the location of pylan's working directory, and insert it to sys.path
#basedir = os.path.dirname(os.path.realpath(__file__))
#if not os.path.exists(os.path.join(basedir, "settings.py")):
#    cwd = os.getcwd()
#    if os.path.exists(os.path.join(cwd, "settings.py")):
#        basedir = cwd
#sys.path.insert(0, basedir)

settings.FILTER = None

def root_check():
    try:
        uid = os.geteuid()
    except:
        pass
    else:
        if uid != 0:
            sys.stderr.write('Warning: not running as root, probably wont be able to access tun device or control the adapters...')

def main():
    root_check()

    op = optparse.OptionParser()
    op.add_option('--gui', action='store_true', default=False, help='Run with gui (default uses cli)')
    op.add_option('--daemon', '-D', action='store_true', default=False, help='Run in daemon mode (no input)')
    op.add_option('--pbi', action='store_true', default=False, help='Run in daemon mode with perspective broker interface')
    op.add_option('--log-file', '-l', help='Specify log file')
    op.add_option('--filter', '-F', type="string", help='filter log with')
    (ops, args) = op.parse_args()
    
    if ops.filter is not None:
        settings.FILTER = ops.filter
    #exaile magic
    class FilterLogger(logging.Logger):
        class Filter(logging.Filter):
            def filter(self, record):
                if settings.FILTER is None:
                    return True
                msg = record.getMessage()
                string = settings.FILTER
                return (
                    string in msg
                    or string in record.name
                    or string in record.levelname
                    or string in record.funcName )
                

        level = logging.NOTSET

        def __init__(self, name):
            logging.Logger.__init__(self, name)

            log_filter = self.Filter(name)
#                log_filter.module = FilterLogger.module
            log_filter.level = FilterLogger.level
            self.addFilter(log_filter)

#       FilterLogger.module = self.options.ModuleFilter
    logging.setLoggerClass(FilterLogger)

    logging.basicConfig(level=settings.get_option('settings/loglevel', 40),
        format='%(asctime)s:[%(levelname)-10s]>%(name)s:<%(funcName)s>::=> \"%(message)s\"')

    # needs testing TODO
    if ops.log_file is not None:
        logging.basicConfig(filename=ops.log_file)
    
    
    if ops.gui: #needs updating TODO
        import gui.main
        gui.main.main()
        
    elif ops.daemon: #needs testing TODO
        from interface import Interface
        from twisted.internet import reactor
        iface = Interface()
        reactor.callLater(iface.start_all_networks)
#        iface.start_all_networks()
        reactor.run()
        
    elif ops.pbi: #needs implimenting and testing TODO
        import pbi
        pbi.main()
        
    else:
        import cli.prompt
        cli.prompt.main()


if __name__ == '__main__':
    main()
