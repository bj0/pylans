#! /usr/bin/env python

from zope.interface import implements
from twisted.internet import reactor, defer, utils
from twisted.internet.protocol import DatagramProtocol
from twisted.internet.interfaces import IReadDescriptor, IPushProducer

import os, sys
from binascii import hexlify
from fcntl import ioctl
import getopt, struct, textwrap


class TunTap(object):
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

        self.f = f
        self.router = router

    def start(self):
        reactor.addReader(self)
        
    def stop(self):
        reactor.removeReader(self)
          
    def configure_iface(self, ip):
        def response(retval):
            if retval != 0:
                print 'error configuring address'
            
        utils.getProcessValue('/sbin/ip',('addr','add',ip,'dev',self.ifname)).addCallback(response)
        d = utils.getProcessValue('/sbin/ip',('link','set',self.ifname,'up'))
        d.addCallback(response)
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
        return self.f

    def logPrefix(self):
        return ''
        
    def connectionLost(self, reason):
        print 'connectionLost called on tuntap'
        self.stop()

