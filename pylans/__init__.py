#!/usr/bin/python

import platform
import sys
import os
import optparse

# make sure settings file is here
import settings

# py2exe
if platform.system() == 'Windows':
    __file__ = sys.argv[0]

# Find out the location of pylan's working directory, and insert it to sys.path
basedir = os.path.dirname(os.path.realpath(__file__))
if not os.path.exists(os.path.join(basedir, "settings.py")):
    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, "settings.py")):
        basedir = cwd
sys.path.insert(0, basedir)

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
    (ops, args) = op.parse_args()
    
    # needs testing TODO
    if ops.log_file is not None:
        import logging
        logging.basicConfig(filename=ops.log_file)
    
    if ops.gui: #needs updating TODO
        import gui.main
        gui.main.main()
        
    elif ops.daemon: #needs testing TODO
        from interface import Interface
        from twisted.internet import reactor
        iface = Interface()
        iface.start_all_networks()
        reactor.run()
        
    elif ops.pbi: #needs implimenting and testing TODO
        import pbi
        pbi.main()
        
    else:
        import cli.prompt
        cli.prompt.main()


if __name__ == '__main__':
    main()
