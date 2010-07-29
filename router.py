#! /usr/bin/env python

from struct import pack, unpack
import logging
import sys
import uuid
import cPickle as pickle

from zope.interface import implements
from twisted.internet import reactor, protocol
from twisted.internet.protocol import DatagramProtocol, Factory, ClientFactory, Protocol
from twisted.internet.task import LoopingCall

import event
import util
from event import Event
from tuntap import TunTap
from crypto import Crypter
from pinger import Pinger
from peers import PeerManager

class UDPPeerProtocol(DatagramProtocol):
    '''Protocol or sending/receiving data to peers'''

    def send(self, data, address):
        '''Send data to address'''
        try:
            self.transport.write(data, address)
        except Exception, e:
            logger.warning('UDP send threw exception:\n  {0}'.format(e))
            ##TODO this is here because UDP socket fills up and just dies
            # but it's UDP so we can drop packets

    def datagramReceived(self, data, address):
        '''Called by twisted when data is received from address'''
#        self.receive(data, address)
        self.router.recv_udp(data, address)
        logger.debug('received data on UDP port')
                
    def connectionRefused(self):
        logger.debug('connectionRefused on UDP port')
            

class Router(object):
    '''The router object handles all the traffic between the virtual tun/tap
    device and the peers.  All traffic flows through the router, where it is 
    filtered (encryption/decryption) and sent to its destination or a handler
    for special packets.
    
    Packet format: TBD'''
    SIGNATURE = 'PV'+pack('H',0)
    
    # packet types
    DATA = 1
    CONTROL = 2
    
    USER = 0x80

    def __init__(self, network, proto=None, tuntap=None):
        if tuntap is None:
            tuntap = TunTap(self)
        if proto is None:
            proto = UDPPeerProtocol()
                        
        self.handlers = {}
                        
        self.network = network
        self.filter = Crypter(network.key)
        proto.router = self
        self.pm = PeerManager(self)
        
        self.pinger = Pinger(self)
        self.pinger.start()
                        
        self._proto = proto
        self._tuntap = tuntap
        self._port = None
    
    def start(self):
        '''Start the router.  Starts the tun/tap device and begins listening on
        the UDP port.'''
        
        self._tuntap.start()
        self._tuntap.configure_iface(self.network.virtual_address)
        self._port = reactor.listenUDP(self.network.port, self._proto)

        logger.info('router started, listening on UDP port {0}'.format(self._port))
    
        reactor.callLater(1, self.try_old_peers)
    
    def stop(self):
        '''Stop the router.  Stops the tun/tap device and stops listening on the 
        UDP port.'''
        self.tuntap.stop()
        # bring down iface?
        if self._port is not None:
            self._port.stopListening()
            self._port = None
            
        logger.info('router stopped')
    
    def try_old_peers(self):
        '''Try to connect to addresses that were peers in previous sessions.'''
        
        logger.debug('trying to connect to previously known addresses')
        
        for address in self.network.known_addresses:
            self.pm.try_register(address)    
            
        if len(self.network.known_addresses) > len(self.pm):
            # if there are some peers that are down, re-schedule a try
            #reactor.callLater(600, self.try_old_peers)
    
    def send(self, type, data, address):
        '''Send a packet of type with data to address'''
        
        data = pack('H', type) + data
        data = self.filter.encrypt(data)
        self._proto.send(data, address)
    
    def send_udp(self, data, address):
        self._proto.send(data, address)
    
    def send_packet(self, packet):
        '''Got a packet from the tun/tap device that needs to be sent out'''
        # check dest ip
#        src = unpack('4B',packet[12:16])
        dst = packet[16:20]
#        prot = unpack('1B',packet[9])[0]
#        src = '.'.join([str(i) for i in src])
#        dst = '.'.join([str(i) for i in dst])
#        print src, dst, prot,self._proto.ip_map
        
        # if ip in peer list
        if dst in self.pm.ip_map:
#            print 'in map'
            self.send(self.DATA, packet, self.pm.ip_map[dst])
#        else:
#            print 'notinmap',dst.encode('hex')
#        self.send(self.DATA, packet)
                
    def send_data(self, data):
        pass

    def recv_udp(self, data, address):
        '''Received a packet from the UDP port.  Parse it and send it on its way.'''
        data = self.filter.decrypt(data)
        # check if from known peer
        dt = unpack('H', data[:2])[0]
        data = data[2:]
        
        if dt == self.DATA:
            self.recv_packet(data)
        
        elif dt == 2:
            self.recv_data(data)
            
        else:
            if dt in self.handlers:
                self.handlers[dt](dt, data, address)
    
        
    def recv_packet(self, packet):
        '''Got a data packet from a peer, need to inject it into tun/tap'''
        # check?
        #print 'get packet'
        self._tuntap.doWrite(packet)
        
    def recv_data(self, data):
        pass
        
    def register_handler(self, type, callback):
        '''Register a handler for a specific packet type.  Handles will be
        called as 'callback(type, data, address)'.'''
        
        logger.debug('registering packet handler for packet type: {0}'.format(type))
        
        if type in self.handlers:
            self.handlers[type] += callback
        else:
           self.handlers[type] = Event()
           self.handlers[type] += callback
           
    def unregister_handler(self, type, callback):
        '''Remove a registered handler for a specific packet type.'''

        logger.debug('unregistering packet handler for packet type: {0}'.format(type))

        if type in self.handlers:
            self.handlers[type] -= callback


