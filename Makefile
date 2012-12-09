PYINST=../pyinstaller-2.0

SHELL := /bin/bash

none:
	@echo build options: 
	@echo  piof     - pyinstaller --onefile 
	@echo  piod     - pyinstaller --onedir
	@echo  cx       - cxfreeze
	@echo  bb       - bbfreeze
	@echo  piupdate - update pyinstaller from git repo

piof: 
	rm -rf build pydist/pylans.exe
	source /home/bjp/env-pylans.sh ;\
	wine python ${PYINST}/pyinstaller.py *onefile.spec

piod:
	rm -rf build pidist/pylans pidist/pylans.7z
	source /home/bjp/env-pylans.sh ;\
	wine python ${PYINST}/pyinstaller.py *onedir.spec
	cd pidist; 7z a pylans.7z pylans

cx:
	rm -rf build cxdist
	source /home/bjp/env-pylans.sh ;\
	wine python cxfsetup.py build
	mv build/exe.win32-2.7 cxdist

bb:
	rm -rf bbdist
	source /home/bjp/env-pylans.sh ;\
	wine python bbsetup.py

piupdate:
	pushd /home/bjp/download/pyinstaller; git pull

