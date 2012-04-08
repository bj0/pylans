# -*- mode: python -*-
import sys
import os

def do_script(name, exename):
    path = os.path.dirname( os.path.realpath( __file__ ) )
    
    a = Analysis([os.path.join(HOMEPATH,'support\\_mountzlib.py'), os.path.join(HOMEPATH,'support\\useUnicode.py'), name],
                 pathex=['Z:'+path.replace('/','\\')])
    pyz = PYZ(a.pure)

    exe = EXE(pyz,
              a.scripts,
              exclude_binaries=1,
              name=os.path.join('build\\pyi.win32\\pylans', exename),
              debug=False,
              strip=False,
              upx=True,
              console=True )
              
    return exe, a


# exclude files from dist
excludes = ['_tkinter',
            'user32.dll',
            'kernel32.dll',
            'msvcrt.dll',
            'iphlpapi.dll',
            'tcl85.dll','tk85.dll',
            'win32ui',
            'win32trace',
            '_win32sysloader',
            ]

exe1, a1 = do_script('pylans-launcher.py','pylans.exe')
exe2, a2 = do_script('pylans-launcher.pyw','pylans-gui.exe')

bins = a1.binaries + a2.binaries
zips = a1.zipfiles + a2.zipfiles
datas = a1.datas + a2.datas

print 'Excluding:'
include = []
for x in sorted(bins, key=lambda x: x[1]):
    if x[0] not in excludes:
        include.append(x)
    else:
        print ' {0:20}: {1}'.format(*x)

print '\nIncluding:'
for x in sorted(include, key=lambda x: x[1]):
    print ' {0:20}: {1}'.format(*x)
bins = include

#print 'AB',[x[0] for x in a.binaries if 'system' in x[1]]
#print 'AB',[x for x in a.binaries]
#exit()

# add data files
datas += [('main.ui','pylans\\gui\\main.ui','DATA')]

coll = COLLECT( exe1,
                exe2,
                bins,
                zips,
                datas,
               strip=False,
               upx=True,
               name=os.path.join('pidist', 'pylans'))
