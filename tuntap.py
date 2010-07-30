#! /usr/bin/env python

from zope.interface import implements
from twisted.internet import reactor, defer, utils
from twisted.internet.threads import deferToThread
from twisted.internet.protocol import DatagramProtocol
from twisted.internet.interfaces import IReadDescriptor, IPushProducer

import os, sys, platform
import logging
from binascii import hexlify
from struct import unpack
import getopt, struct

import util

logger = logging.getLogger(__name__)

class TunTapLinux(object):
    '''
        Access to the virtual tun/tap device.
    '''
        
    implements(IReadDescriptor)

    TUNSETIFF = 0x400454ca
    IFF_TUN   = 0x0001
    IFF_TAP   = 0x0002
    IFF_NO_PI = 0x1000

    TUNMODE = IFF_TUN
    
    def __init__(self, router):
        f = os.open("/dev/net/tun", os.O_RDWR)
        ifs = ioctl(f, self.TUNSETIFF, struct.pack("16sH", "pytun%d", self.TUNMODE|self.IFF_NO_PI))
        self.ifname = ifs[:16].strip("\x00")

        logger.info('opened tun device as interface {0}'.format(self.ifname))

        self.f = f
        self.router = router

    def start(self):
        '''Start monitoring tun/tap for input'''
        reactor.addReader(self)
        logger.info('linux tun/tap started')
        
    def stop(self):
        '''Stop monitoring tun/tap for input'''
        reactor.removeReader(self)
        logger.info('linux tun/tap stopped')
          
    def configure_iface(self, address):
        '''
            Configure the tun/tap interface with given address/mask (ie: '10.1.1.1/24')
        '''
        def response(retval):
            if retval != 0:
                logger.error('error configuring address {0} on interface {1}'.format(address, self.ifname))
            
        utils.getProcessValue('/sbin/ip',('addr','add',address,'dev',self.ifname)).addCallback(response)
        d = utils.getProcessValue('/sbin/ip',('link','set',self.ifname,'up'))
        d.addCallback(response)
        logger.info('configuring interface {1} to: {0}'.format(address, self.ifname))
        return d

    def doRead(self):
        '''
            New data is coming in on the tun/tap 'wire'.
        '''
        data = os.read(self.f, 2000) # max mtu is 1500
        self.router.send_packet(data)
        
    def doWrite(self, data):
        '''
            Write some data out to the tun/tap 'wire'.
        '''
        os.write(self.f, data)
        
    def fileno(self):
        '''Return the file identifier from os.open'''
        return self.f

    def logPrefix(self):
        return '.>'
        
    def connectionLost(self, reason):
        logger.warning('connectionLost called on tuntap')
        self.stop()
        
                
class TunTapWindows(object):
    def __init__(self, router):
        self._running = False
        
        self._tuntap = TunTapDevice()
        self.router = router
        
    def configure_iface(self, addr):
        self._tuntap.configure_iface(addr)
        
    def got_data(self, data):
#        print data[12:14].encode('hex'),unpack('H',data[12:14])[0]
#        if unpack('H',data[12:14])[0] == 0x8:
#            print 'ipv4 packet'
#        else:
#            print 'other packet'
#        print 'gotdata:','\n'.join(wrap(hexlify(data),4*2))
        self.router.send_packet(data)
        
    def doWrite(self, data):
        deferToThread(self._tuntap.write, data)
        
    def start(self):
        self._running = True
        self.run()
        logger.info('windows tun/tap started')
        
    def stop(self):
        self._running = False
        logger.info('windows tun/tap stopped')
        
    
    @util.threaded        
    def run(self):
        while self._running:
            data = self._tuntap.read()
            reactor.callFromThread(self.got_data, data)
        

if platform.system() == 'Linux':
    from fcntl import ioctl
    TunTap = TunTapLinux
    logger.info('Linux detected, using TapTunLinux')
elif platform.system() == 'Windows':
    from windows_tuntap import TunTapDevice
    TunTap = TunTapWindows
    logger.info('Windows detected, usingTapTunWindows')

        
if __name__ == '__main__':
    import platform
    if platform.system() == 'Windows':
        ttw = TunTapWindows(None)
        ttw.configure_iface('10.1.1.11/32')
        ttw.start()
        
        try:
            reactor.run()
        except KeyboardInterrupt:
            print 'closin'
            
    
    else:
        pass    
    

