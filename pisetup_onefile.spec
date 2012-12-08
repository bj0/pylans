# -*- mode: python -*-
a = Analysis([os.path.join(HOMEPATH,'support\\_mountzlib.py'), os.path.join(HOMEPATH,'support\\useUnicode.py'), 'pylans-launcher.py'],
             pathex=['Z:\\home\\bjp\\pylans'])
pyz = PYZ(a.pure)

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

print 'Excluding:'
include = []
for x in sorted(a.binaries, key=lambda x: x[1]):
    if x[0] not in excludes:
        include.append(x)
    else:
        print ' {0:20}: {1}'.format(*x)
print '\nIncluding:'
for x in sorted(include, key=lambda x: x[1]):
    print ' {0:20}: {1}'.format(*x)
a.binaries = include
#print 'AB',[x[0] for x in a.binaries if 'system' in x[1]]
#print 'AB',[x for x in a.binaries]
#exit()

# add data files
a.datas += [('main.ui', 'pylans\\gui\\main.ui', 'DATA')]
a.datas += [('menu.png','pylans\\gui\\menu.png','DATA')]
a.datas += [('pylans-icon.png','pylans\\gui\\pylans-icon.png','DATA')]

exe = EXE( pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name=os.path.join('pidist', 'pylans.exe'),
          debug=False,
          strip=False,
          upx=True,
          console=True )
