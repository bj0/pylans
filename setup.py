# Copyright (C) 2010  Brian Parma (execrable@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
# setup.py - Generates a p2exe Executable.  


from distutils.core import setup
import py2exe, sys, glob

# If run without args, build executables, in quiet mode.
if len(sys.argv) == 1:
    sys.argv.append("py2exe")
    sys.argv.append("-q")

excludes = ['Tkconstants','Tkinter','tcl',"pywin", "pywin.debugger", "pywin.debugger.dbgcon",
             "pywin.dialogs", "pywin.dialogs.list",
             '_imagingtk','PIL._imagingtk','ImageTk','PIL.ImageTk','FixTk']


#
# The following will copy the MSVC run time dll's
# (msvcm90.dll, msvcp90.dll and msvcr90.dll) and
# the Microsoft.VC90.CRT.manifest which I keep in the
# "Py26MSdlls" folder to the dist folder
#
# depending on wx widgets you use, you might need to add
# gdiplus.dll to the above collection

py26MSdll = glob.glob(r"c:\Python26\msdlls\*.*")

# following works from Windows XP +
# if you need to deploy to older MS Win versions then I found that on Win2K
# it will also work if the files are put into the application folder without
# using a sub-folder.
data_files = [# ("Microsoft.VC90.CRT", py26MSdll),
               ("lib\Microsoft.VC90.CRT", py26MSdll),
              ]



options = {
                 'includes':['twisted.web.resource'],
                 'excludes':excludes,
                 'optimize':2,
# these options bundle everything into the .exe/.zip file (except msvcr71.dll)
                 'bundle_files':2, #cmd.Cmd.cmdloop() causes crashes on 'bundle_files':1
                 'compressed':1}


dest_base = 'Py2PyVPN'

setup(
    # The first three parameters are not required, if at least a
    # 'version' is given, then a versioninfo resource is built from
    # them and added to the executables.
    version = "0.0.1",
    description = "Python VPN Tunnel",
    name = "Py2PyVPN!",
    data_files = data_files,


    # targets to build
    console = [{'script':'main.py', 'dest_base':dest_base}],
#    windows = [{'script':'prompt.py','dest_base':dest_base}],
#                'icon_resources':[(1,'wicon.ico')]}],

    options = {'py2exe':options},
    # this makes everything bundle in the .exe instead of a zip file
    zipfile = None,
    )

# upx executable
#if not 'apps' in ''.join(sys.path):
#    sys.path += ['d:\\apps']
#import upx
#
#print 'Packing with UPX...\n'
#upx.upx(['--best', 'dist\\'+dest_base+'.exe'])
