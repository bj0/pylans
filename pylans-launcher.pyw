#!/usr/bin/python 
# launcher for the gui

import platform
import os

def root_check():
    if platform.system() == 'Linux':
        return os.geteuid() == 0
        
    elif platform.system() == 'Windows':
        from win32com.shell import shell
        return shell.IsUserAnAdmin()
    else:
        raise OSError('unknown or unsupported OS')

def elevate():
    import sys
    froz = getattr(sys, 'frozen', False)
    if froz:
        exe = getattr( sys, 'executable', __file__)
    else:
        exe = __file__
        
    exe = os.path.realpath( exe )
    my_path = os.path.dirname( exe )
    
    print 'Trying to elevate {0}'.format(exe)
    if platform.system() == 'Linux':
        raise NotImplementedError("run sudo")
                
    elif platform.system() == 'Windows':
        import win32api
        args = [ 0, # parent window
            "runas", # need this to force UAC to act
            "C:\\python27\\pythonw.exe", 
            exe, 
            my_path, # base dir
            1 ] # window visibility - 1: visible, 0: background
        
        if froz:
            args[2] = exe
            args[3] = None
	
        win32api.ShellExecute(*args)
	
if __name__ == '__main__':
	
    if not root_check():
        import sys
        sys.exit(elevate())

    import pylans
    import sys
    if '--gui' not in sys.argv:
        sys.argv.append('--gui')
        
    pylans.main()
