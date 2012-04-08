# bb_setup2.py
from bbfreeze import Freezer
 
includes = []
excludes = ['_gtkagg', '_tkagg', 'bsddb', 'curses', 'email', 'pywin.debugger',
            'pywin.debugger.dbgcon', 'pywin.dialogs', 'tcl',
            'Tkconstants', 'Tkinter',
# in the folder
            'win32console',
            'win32ui',
            'dde',
            'multiprocessing','_multiprocessing',
            'win32sysloader','_win32sysloader',
            ]
 
bbFreeze_Class = Freezer('bbdist', includes=includes, excludes=excludes)
 
bbFreeze_Class.addScript("pylans-launcher.py")
bbFreeze_Class.addScript("pylans-launcher.pyw", gui_only=True)
 
bbFreeze_Class.use_compression = True
bbFreeze_Class.include_py = True
bbFreeze_Class()
