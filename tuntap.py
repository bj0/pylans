#! /usr/bin/env python
# 
# TUN mode - Layer 3, only IP packets are passed to the device:
# -- packet format is: 
# -- http://en.wikipedia.org/wiki/IPv4
# -- src ip address is at 12 (96)
# -- dst ip address is at 16 (128)
# 
# TAP mode - layer 2, ethernet packets, which sometimes (but not always)
#  embed IP packets.
# -- packet format is:
# -- [mac dst] [mac src] [type] [data] [crc]
# --     6         6       2       ?     4
# common types:
# -- 0x0800 - ipv4
# -- 0x0806 - arp
# 
# 

from zope.interface import implements
from twisted.internet import reactor, defer, utils
from twisted.internet.threads import deferToThread
from twisted.internet.protocol import DatagramProtocol
from twisted.internet.interfaces import IReadDescriptor, IPushProducer

import os, sys, platform
import logging
import socket
from binascii import hexlify
from struct import unpack
import getopt, struct

import util

logger = logging.getLogger(__name__)

class TunTapBase(object):
    '''
        Access to the virtual tun/tap device (Base Class).
    '''

    IFF_TUN   = 0x0001
    IFF_TAP   = 0x0002
    IFF_NO_PI = 0x1000

    TUNMODE = IFF_TUN
    TAPMODE = IFF_TAP

#    @classmethod
#    def is_ip6_discovery(mac):
#    '''ip6 neighbor discovery address are between 33:33:00:00:00:00 - 33:33:FF:FF:FF:FF (n2n et al)'''
#        if mac[0:2] == '\x33\x33':
#            return True
#        return False

    @classmethod
    def is_multicast(cls, mac):
        '''ethernet (ipv4) multicast addresses are 01:00:5E:??:??:??'''
        if mac[0:3] == '\x01\x00\x5e':
            return True
        return False

    @classmethod
    def is_broadcast(cls, mac):
        '''ethernet broadcast is typically FF:FF:FF:FF:FF:FF, but we can just check the LSB of the first octet (which includes multicast)'''
        if ord(mac[0]) & 1 == 1:
            return True
        return False

class TunTapLinux(TunTapBase):
    '''
        Access to the virtual tun/tap device.
    '''
        
    implements(IReadDescriptor)

    SIOCGIFHWADDR = 0x8927
    TUNSETIFF = 0x400454ca

    @property
    def is_tap(self):
        return (self.mode == self.TAPMODE)
        
    @property
    def is_tun(self):
        return not self.is_tap
    
    def __init__(self, router, mode):
        f = os.open("/dev/net/tun", os.O_RDWR)
        ifs = ioctl(f, self.TUNSETIFF, struct.pack("16sH", "pytun%d", mode|self.IFF_NO_PI))
        self.ifname = ifs[:16].strip("\x00")

        logger.info('opened tun device as interface {0}'.format(self.ifname))

        self.f = f
        self.router = router
        self.mode = mode

    def start(self):
        '''Start monitoring tun/tap for input'''
        reactor.addReader(self)
        logger.info('linux tun/tap started')
        
    def stop(self):
        '''Stop monitoring tun/tap for input'''
        reactor.removeReader(self)
        logger.info('linux tun/tap stopped')

    def get_mac(self):
        s = socket.socket(type=socket.SOCK_DGRAM)   
        ifr = self.ifname + '\0'*(32-len(self.ifname))    
        ifs = ioctl(s.fileno(), self.SIOCGIFHWADDR, ifr)
        mac = ifs[18:24]
        
        logger.debug('got mac address: {0}'.format(mac.encode('hex')))

        return mac
          
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
        
                
class TunTapWindows(TunTapBase):
    def __init__(self, router, mode):
        self._running = False
        
        self._tuntap = TunTapDevice(mode)
        self.router = router
        
    def configure_iface(self, addr):
        self._tuntap.configure_iface(addr)
        
    def get_mac(self):
        ai = util.get_adapters_info()
        did = self._tuntap._devid
        if did in ai:
            mac_str = ai[did]['address']
            mac = util.encode_mac(mac_str)
        else:
            logger.critical('selected adapter not in get_adapters_info()')
            raise Exception('selected adapter not returned by get_adapters_info()')

        logger.debug('got mac address: {0}'.format(mac_str))
        return mac

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
#        tt = TunTap()
        pass    
    

