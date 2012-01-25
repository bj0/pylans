from fcntl import ioctl
import atexit
import os
import subprocess as sp
import struct
import logging
import socket
from . import TunTapBase

logger = logging.getLogger(__name__)

# definitions from linux driver
IFF_TUN   = 0x0001
IFF_TAP   = 0x0002
IFF_NO_PI = 0x1000

SIOCGIFHWADDR = 0x8927
SIOCGIFMTU = 0x8921
SIOCSIFMTU = 0x8922
TUNSETIFF = 0x400454ca

class TunTapLinux(TunTapBase):
    '''
        Access to the virtual tun/tap device.
    '''

    # modes for settings
    TUNMODE = IFF_TUN
    TAPMODE = IFF_TAP


    def __init__(self, mode="TAP", name=None, dev='/dev/net/tun'):
    
        # open tun/tap device controller
#        f = os.open(dev, os.O_RDWR|os.O_NONBLOCK)
        f = os.open(dev, os.O_RDWR)

        # check mode, should come in as 'TUN' or 'TAP'
        if isinstance(mode, str):
            mode = self.TUNMODE if mode == 'TUN' else self.TAPMODE
            
        if name is None:
            if mode == self.TAPMODE:
                name = 'pytap%d'
            else:
                name = 'pytun%d'
        elif not name.endswith('%d'):
            name = name + '%d'

        # ioctl call to create adapter, retuns adapter name
        ifs = ioctl(f, TUNSETIFF, struct.pack("16sH", name, 
                                                    mode|IFF_NO_PI))

        # get iface name
        self.ifname = ifs[:16].strip("\x00")

        logger.info('opened tun device as interface {0}'.format(self.ifname))

        self._f = f
        self._file = os.fdopen(f)
        self.mode = mode
        self.mtu = 1500 # default mtu

        # close device on exit
        atexit.register(self.close)

    def __del__(self):
        '''close device on object gc'''
        self.close()

    def close(self):
        '''Make sure device is closed.'''
        logger.info('closing tun device {0}'.format(self.ifname))
        os.close(self._f)

    def start(self):
        '''Start monitoring tun/tap for input'''
        logger.info('linux tun/tap started')

    def stop(self):
        '''Stop monitoring tun/tap for input'''
        logger.info('linux tun/tap stopped')

    def _shell(self, cmd):
        return sp.call(cmd)

    def up(self):
        '''Bring up interface'''
        ret = self._shell(['ip','link','set',self.ifname,'up'])
        if ret != 0:
            raise Exception()
       
    def down(self):
        '''Bring down interface'''
        ret = self._shell(['ip','link','set',self.ifname,'down'])
        if ret != 0:
            raise Exception()
        
    def configure_iface(self, **options):
        '''
            addr - string of the form "127.0.0.1/32"
            mtu - 
            hwaddr - string of the form "AA:BB:CC:DD:EE:FF"
        '''
        
        # check for spurious args
        err = [arg for arg in options.keys() 
                            if arg not in ['addr','mtu','hwaddr']]
        if len(err) > 0:
            logger.error('configure_iface passed unrecognized arguments: {0}'
                    .format(err))

        if 'addr' in options:
            addr = options['addr']
            if '/' not in addr:
                addr = addr+'/32'

            ret = self._shell(['ip','addr','add',addr,'dev',self.ifname])
            if ret != 0:
                raise Exception()
                
        if mtu in options:
            mtu = options['mtu']
            self.set_mtu(mtu)                
        
        if 'hwaddr' in options:
            hwaddr = options['hwaddr']
            
            ret = self._shell(['ip','link','set','dev',self.ifname,'address',hwaddr])
            if ret != 0:
                raise Exception()
        

    def get_mtu(self):
        '''Use socket ioctl call to get MTU size'''
        s = socket.socket(type=socket.SOCK_DGRAM)
        ifr = self.ifname + '\x00'*(32-len(self.ifname))
        try:
            ifs = ioctl(s, SIOCGIFMTU, ifr)
            mtu = struct.unpack('<H',ifs[16:18])[0]
        except Exception, s:
            logger.critical('socket ioctl call failed: {0}'.format(s))
            raise

        logger.debug('get_mtu: mtu of {0} = {1}'.format(self.ifname, mtu))
        self.mtu = mtu
        return mtu

    def set_mtu(self, mtu):
        '''Use socket ioctl call to set MTU size'''
        s = socket.socket(type=socket.SOCK_DGRAM)
        ifr = struct.pack('<16sH', self.ifname, mtu) + '\x00'*14
        try:
            ifs = ioctl(s, SIOCSIFMTU, ifr)
            self.mtu = struct.unpack('<H',ifs[16:18])[0]
        except Exception, s:
            logger.critical('socket ioctl call failed: {0}'.format(s))
            raise

        logger.debug('set_mtu: mtu of {0} = {1}'.format(self.ifname, self.mtu))

        return self.mtu


    def read(self):
        '''
            New data is coming in on the tun/tap 'wire'.  Called by twisted.
        '''
#        return self._file.read()
        return os.read(self._f, 5120) #TODO wat is max size, what should it be?

    def write(self, data):
        '''
            Write some data out to the tun/tap 'wire'.
        '''
        os.write(self._f, data)

    def fileno(self):
        '''Return the file identifier from os.open.  Required for twisted to
        select() our stream.'''
        return self._f

