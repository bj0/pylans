#!/usr/bin/python

import platform
import sys
import os
import optparse
import logging
import re

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

settings.FILTER = []
settings.IGNORE = []

def root_check():
    import platform
    if platform.system() == 'Linux':
        return os.geteuid() == 0
    elif platform.system() == 'Windows':
        from win32com.shell import shell
        return shell.IsUserAnAdmin()
    else:
        sys.stderr.write('Warning: unknown or unsupported OS\n')


def main():
    if not root_check():
        sys.stderr.write('Warning: not running as root, probably wont be able to access tun/tap device or control the adapters...\n')


    op = optparse.OptionParser()
    op.add_option('--gui', action='store_true', default=False, help='Run with gui (default uses cli)')
    op.add_option('--daemon', '-D', action='store_true', default=False, help='Run in daemon mode (no input)')
    op.add_option('--pbi', action='store_true', default=False, help='Run in daemon mode with perspective broker interface')
    op.add_option('--log-file', '-l', help='Specify log file')
    op.add_option('--filter', '-F', action="append", type="string", help='add string to log filter')
    op.add_option('--ignore', action="append", type='string', help='add string to log anti-filter')
    op.add_option('--short', action='store_true', default=True, help='show shorter log msgs')
    op.add_option('--long', action='store_false', dest="short", help='show full log msgs')
    (ops, args) = op.parse_args()
    
    if ops.filter is not None:
        settings.FILTER += [re.compile(s) for s in ops.filter]
    if ops.ignore is not None:
        settings.IGNORE += [re.compile(s) for s in ops.ignore]
        
    #exaile's (modified) magic
    class FilterLogger(logging.Logger):
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

    if ops.short:
        fmt = '[%(levelname)-10s]: \"%(message)s\"'
    else:
        fmt = '%(asctime)s:[%(levelname)-10s]>%(name)s:<%(funcName)s>::=> \"%(message)s\"'

    logging.setLoggerClass(FilterLogger)
    logging.basicConfig(level=settings.get_option('settings/loglevel', 40),
        format=fmt)

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
