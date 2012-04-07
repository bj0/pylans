#!/usr/bin/python 
# launcher for the gui

if __name__ == '__main__':
    import pylans
    import sys
    if '--gui' not in sys.argv:
        sys.argv.append('--gui')
        
    pylans.main()
