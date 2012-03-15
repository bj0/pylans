

none:
	echo "options: piof piod cx bb"

piof: 
	rm -rf build pydist/pylans.exe
	wine python /home/bjp/code/oss/pyinstaller-1.5.1/Build.py *onefile.spec

piod:
	rm -rf build pidist/pylans
	wine python /home/bjp/code/oss/pyinstaller-1.5.1/Build.py *onedir.spec

cx:
	rm -rf build cxdist
	wine python cxfsetup.py build
	mv build/exe.win32-2.7 cxdist

bb:
	rm -rf bbdist
	wine python bbsetup.py

