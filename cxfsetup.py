from cx_Freeze import setup, Executable


options = dict(
        excludes = 
            ['_gtkagg', '_tkagg', 'bsddb', 'email', 'pywin.debugger',
             'pywin.debugger.dbgcon', 'pywin.dialogs', 'tcl',
             'Tkconstants', 'Tkinter','tk','tkinter','ttk','curses','email',
             ],
        )

exe = Executable(
    script="pylans-launcher.py", 
    initScript = None,
    base = None,
#    targetDir = r"cxdist",
    targetName = "pylans.exe",
    compress = True,
#    copyDependentFiles = True,
    appendScriptToExe = False,
    appendScriptToLibrary = False,
    icon = None
    )

setup(
    name = "pylans!",
    version = "0.0.2",
    author = 'Brian Parma',
    description = "Python p2p VPN Tunnel",
    executables = [exe],
    options = {'build_exe': options},
    )
