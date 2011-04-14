#! /usr/bin/env python
#
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
# tuntap.py
# tuntap device interface
#
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

from twisted.internet import reactor, utils
from twisted.internet.interfaces import IReadDescriptor
from twisted.internet.threads import deferToThread
from zope.interface import implements
import settings
import logging
import os
import platform
import socket
import struct
import util



logger = logging.getLogger(__name__)

class TunTapBase(object):
    '''
        Access to the virtual tun/tap device (Base Class).
    '''

    # definitions from linux driver
    IFF_TUN   = 0x0001
    IFF_TAP   = 0x0002
    IFF_NO_PI = 0x1000

    # modes for settings
    TUNMODE = IFF_TUN
    TAPMODE = IFF_TAP
    
    #

#    @classmethod
#    def is_ip6_discovery(mac):
#    '''ip6 neighbor discovery address are between 33:33:00:00:00:00 - 33:33:FF:FF:FF:FF (n2n et al)'''
#        if mac[0:2] == '\x33\x33':
#            return True
#        return False

    @property
    def is_tap(self):
        '''Is this a TAP device?'''
        return (self.mode == self.TAPMODE)
        
    @property
    def is_tun(self):
        '''Is this a TUN device?'''
        return not self.is_tap
    
    @classmethod
    def is_multicast(cls, mac):
        '''ethernet (ipv4) multicast addresses are 01:00:5E:??:??:??
        
        >>> import util
        >>> TunTapBase.is_multicast(util.encode_mac('01:00:5e:a1:00:3c'))
        True

        >>> TunTapBase.is_multicast(util.encode_mac('FF:00:5e:a1:00:3c'))
        False
        '''
        if mac[0:3] == '\x01\x00\x5e':
            return True
        return False

    @classmethod
    def is_broadcast(cls, mac):
        '''ethernet broadcast is typically FF:FF:FF:FF:FF:FF, but we can just check the LSB of the first octet (which includes multicast)

        >>> import util
        >>> TunTapBase.is_broadcast(util.encode_mac('01:00:5e:a1:00:3c'))
        True

        >>> TunTapBase.is_broadcast(util.encode_mac('FF:00:5e:a1:00:3c'))
        True

        >>> TunTapBase.is_broadcast(util.encode_mac('FE:00:5e:a1:00:3c'))
        False
        '''
        if ord(mac[0]) & 1 == 1:
            return True
        return False

class TunTapLinux(TunTapBase):
    '''
        Access to the virtual tun/tap device.
    '''
        
    implements(IReadDescriptor)

    SIOCGIFHWADDR = 0x8927
    SIOCGIFMTU = 0x8921
    SIOCSIFMTU = 0x8922
    TUNSETIFF = 0x400454ca

    def __init__(self, router, mode):
        f = os.open("/dev/net/tun", os.O_RDWR)
        ifs = ioctl(f, self.TUNSETIFF, struct.pack("16sH", "pytun%d", mode|self.IFF_NO_PI))
        self.ifname = ifs[:16].strip("\x00")

        logger.info('opened tun device as interface {0}'.format(self.ifname))

        self.f = f
        self.router = util.get_weakref_proxy(router)
        self.mode = mode

    def __del__(self):
        '''Make sure device is closed.'''
        logger.info('closing tun device {0}'.format(self.ifname))
        os.close(self.f)

    def start(self):
        '''Start monitoring tun/tap for input'''
        reactor.addReader(self)
        logger.info('linux tun/tap started')
        
    def stop(self):
        '''Stop monitoring tun/tap for input'''
        reactor.removeReader(self)
        logger.info('linux tun/tap stopped')

    def get_mtu(self):
        '''Use socket ioctl call to get MTU size'''
        s = socket.socket(type=socket.SOCK_DGRAM)
        ifr = self.ifname + '\x00'*(32-len(self.ifname))
        try:
            ifs = ioctl(s, self.SIOCGIFMTU, ifr)
            mtu = struct.unpack('<H',ifs[16:18])[0]
        except Exception, s:
            logger.error('socket ioctl call failed: {0}'.format(s))
            # re-throw?
        
        logger.debug('get_mtu: got mtu: {0}'.format(mtu))
        
        return mtu
        
    def set_mtu(self, mtu):
        '''Use socket ioctl call to set MTU size'''
        s = socket.socket(type=socket.SOCK_DGRAM)
        ifr = struct.pack('<16sH', self.ifname, mtu) + '\x00'*14
        try:
            ifs = ioctl(s, self.SIOCSIFMTU, ifr)
            mtu = struct.unpack('<H',ifs[16:18])[0]
        except Exception, s:
            logger.error('socket ioctl call failed: {0}'.format(s))
            # re-throw?
        
        logger.debug('set_mtu: new mtu value: {0}'.format(mtu))
        
        return mtu

    def get_mac(self):
        '''Use socket ioctl call to get MAC address'''
        s = socket.socket(type=socket.SOCK_DGRAM)   
        ifr = self.ifname + '\0'*(32-len(self.ifname))    
        ifs = ioctl(s.fileno(), self.SIOCGIFHWADDR, ifr)
        mac = ifs[18:24]
        
        logger.debug('got mac address: {0}'.format(util.decode_mac(mac)))

        return mac
          
    def get_ips(self):
        '''Use subprocess+ifconfig+grep to get ip addresses on the interface'''
        import subprocess as sp
        
        out = sp.Popen(["ifconfig {0} |grep 'inet add'".format(self.ifname)], shell=True, stdout=sp.PIPE).communicate()[0]
        out = out.strip().split()
        ips = [ x[5:] for x in out if x.startswith('addr:') ]
        masks = [ x[5:] for x in out if x.startswith('Mask:') ]
                        
        logger.debug('got {0} ip addresses: {1}'.format(len(ips),ips))
        return ips

    def configure_iface(self, address):
        '''
            Configure the tun/tap interface with given address/mask (ie: '10.1.1.1/24')
        '''
        def response(retval):
            if retval != 0:
                logger.error('error configuring address {0} on interface {1}'.format(address, self.ifname))
            
        # re-do this to chain deferreds?TODO
        utils.getProcessValue('/sbin/ip',('addr','add',address,'dev',self.ifname)).addCallback(response)
        d = utils.getProcessValue('/sbin/ip',('link','set',self.ifname,'up'))
        d.addCallback(response)
        
        # set mtu
        mtu = settings.get_option(self.router.network.name+'/set_mtu', None)
        if mtu is not None:
            mtu = settings.get_option('settings/set_mtu', None)
            if mtu is not None:
                mtu = self.set_mtu(mtu)
                logger.info('setting {0} mtu to: {1}'.format(self.ifname, mtu))
        
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
#        try:
        os.write(self.f, data)
#        except:
#            import traceback
#            traceback.print_exc()
#            logger.warning('Got Exception trying to os.write()\nself.f: {0}\ndata: {1} ({2})'.format(
#                        self.f, data.encode('hex'), len(data)))
        
    def fileno(self):
        '''Return the file identifier from os.open'''
        return self.f

    def logPrefix(self):
        '''Required but not used?'''
        return '.>'
        
    def connectionLost(self, reason):
        logger.warning('connectionLost called on tuntap')
        self.stop()
        
                
class TunTapWindows(TunTapBase):
    def __init__(self, router, mode):
        self._running = False
        
        self._tuntap = TunTapDevice(mode)
        self.router = util.get_weakref_proxy(router)
        self.mode = mode
        
    def configure_iface(self, addr):
        return self._tuntap.configure_iface(addr)

    def get_ips(self):
        ai = util.get_adapters_info()
        did = self._tuntap._devid
        if did in ai:
            ips = ai[did]['ipAddressList']
        else:
            logger.critical('selected adapter not in get_adapters_info()')
                    
        logger.debug('got {0} ip addresses: {1}'.format(len(ips),ips))
#        import pprint
#        pprint.pprint( ai[did])
        return [ x[0] for x in ips ]

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
        IPV4_HIGH = 0x08
        IPV4_LOW = 0x00
        IPV4_UDP = 17
        while self._running:
            data = self._tuntap.read()
            if data[12] == IPV4_HIGH and data[13] == IPV4_LOW and data[14+9] == IPV4_UDP:
                logger.warning('IPV4 udp: {0}'.format(util.decode_ip(data[26:30])))
                
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
    

