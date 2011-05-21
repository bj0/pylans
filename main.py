#!/usr/bin/python

import platform
import sys
import os
import optparse

# make sure settings file is here
from vpn import settings

# py2exe
if platform.system() == 'Windows':
    __file__ = sys.argv[0]

# Find out the location of exaile's working directory, and insert it to sys.path
basedir = os.path.dirname(os.path.realpath(__file__))
if not os.path.exists(os.path.join(basedir, "main.py")):
    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, "main.py")):
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
    op.add_option('--gui', action='store_true', default=False, help='Run with gui (default uses cli')
    (ops, args) = op.parse_args()
    
    if ops.gui:
        import gui.main
        gui.main.main()
    else:
        import cli.prompt
        cli.prompt.main()



if __name__ == '__main__':
    main()
