#!/usr/bin/python

import platform
import sys
import os
import optparse
import re
import logging

# to get initial logging setup
from . import plogging
# make sure settings file is here
from . import settings

logger = logging.getLogger(__name__)

# py2exe TODO: fix this, it's breaking the path in windows
#if platform.system() == 'Windows':
#    __file__ = sys.argv[0]

settings.is_admin = True
settings.tap_access = True

def root_check():
    import platform
    if platform.system() == 'Linux':
        settings.is_admin = (os.geteuid() == 0)
        return settings.is_admin
    elif platform.system() == 'Windows':
        from win32com.shell import shell
        settings.is_admin = shell.IsUserAnAdmin()
        return settings.is_admin
    else:
        logger.warning('Warning: unknown or unsupported OS\n')


def main():
    if not root_check():
        logger.warning('Warning: not running as root, probably wont be able to access tun/tap device or control the adapters...\n')


    op = optparse.OptionParser()
    op.add_option('--gui', action='store_true', default=False, 
                        help='Run with gui (default uses cli)')
    op.add_option('--daemon', '-D', action='store_true', default=False, 
                        help='Run in daemon mode (no input)')
    op.add_option('--pbi', action='store_true', default=False, 
                        help='Run in daemon mode with perspective broker interface')
    op.add_option('--logfile', '-l', 
                        help='Specify log file')
    op.add_option('--nologfile', action='store_true', default=False,
                        help='disable logging to file')
    op.add_option('--filter', '-F', action="append", type="string", 
                        help='add string to log filter')
    op.add_option('--ignore', action="append", type='string', 
                        help='add string to log anti-filter')
    op.add_option('--short', action='store_true', default=True, 
                        help='show shorter log msgs')
    op.add_option('--long', action='store_false', dest="short", 
                        help='show full log msgs')
    (ops, args) = op.parse_args()
    
    if ops.filter is not None:
        settings.FILTER += [re.compile(s) for s in ops.filter]
    if ops.ignore is not None:
        settings.IGNORE += [re.compile(s) for s in ops.ignore]
        

    
    if ops.short:
        # switch to short formatting
        plogging.short()
        
    if not ops.nologfile:
        from logging import handlers
        import datetime

        log_file = ops.logfile if ops.logfile is not None else 'pylans.log'
        handler = logging.handlers.RotatingFileHandler(log_file, 
                                                        mode='ab', 
                                                        backupCount=3)
        # create a new logfile each startup
        handler.doRollover()
        handler.setFormatter(logging.Formatter(long_format))
        lgr = logging.getLogger()
        lgr.addHandler(handler)
        lgr.log(100, 'Starting logfile at %s', str(datetime.datetime.now()))
        
        
    if ops.gui: #needs updating TODO
        import gui.main
        gui.main.main()
        
    elif ops.daemon: #needs testing TODO
        from interface import Interface
        from twisted.internet import reactor
        iface = Interface()
        reactor.callLater(iface.start_all_networks)
        reactor.run()
        
    elif ops.pbi: #needs implimenting and testing TODO
        import pbi
        pbi.main()
        
    else:
        import cli.prompt
        cli.prompt.main()


if __name__ == '__main__':
    main()
