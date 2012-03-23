PYINST=/home/bjp/download/pyinstaller

SHELL := /bin/bash

none:
	@echo build options: 
	@echo  piconf   - configure pyinstaller \(required once\)
	@echo  piof     - pyinstaller --onefile 
	@echo  piod     - pyinstaller --onedir
	@echo  cx       - cxfreeze
	@echo  bb       - bbfreeze
	@echo  piupdate - update pyinstaller from git repo

piconf:
	source /home/bjp/env-pylans.sh ;\
	wine python ${PYINST}/Configure.py

piof: 
	rm -rf build pydist/pylans.exe
	source /home/bjp/env-pylans.sh ;\
	wine python ${PYINST}/pyinstaller.py *onefile.spec

piod:
	rm -rf build pidist/pylans
	source /home/bjp/env-pylans.sh ;\
	wine python ${PYINST}/pyinstaller.py *onedir.spec

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

