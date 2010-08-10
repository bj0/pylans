#! /usr/bin/env python

from struct import pack, unpack
import logging
import sys
import cPickle as pickle
import random

from zope.interface import implements
from twisted.internet import reactor, protocol, defer
from twisted.internet.protocol import DatagramProtocol, Factory, ClientFactory, Protocol
from twisted.internet.task import LoopingCall

import event
import util
from event import Event
from tuntap import TunTap
from crypto import Crypter
from pinger import Pinger
from peers import PeerManager

logger = logging.getLogger(__name__)

class UDPPeerProtocol(DatagramProtocol):
    '''Protocol or sending/receiving data to peers'''

    def send(self, data, address):
        '''Send data to address'''
        try:
#            logger.debug('sending data on UDP port to {0}'.format(address))
            self.transport.write(data, address)
        except Exception, e:
            logger.warning('UDP send threw exception:\n  {0}'.format(e))
            ##TODO this is here because UDP socket fills up and just dies
            # but it's UDP so we can drop packets

    def datagramReceived(self, data, address):
        '''Called by twisted when data is received from address'''
#        self.receive(data, address)
        self.router.recv_udp(data, address)
        logger.debug('received data on UDP port from {0}'.format(address))
                
    def connectionRefused(self):
        logger.debug('connectionRefused on UDP port')
            

class Router(object):
    '''The router object handles all the traffic between the virtual tun/tap
    device and the peers.  All traffic flows through the router, where it is 
    filtered (encryption/decryption) and sent to its destination or a handler
    for special packets.
    
    Packet format: TBD'''
    SIGNATURE = 'PV'+pack('H',0)
    
    TIMEOUT = 5 # 5s
    # packet types
    DATA = 1
    ACK = 2
    
    USER = 0x80

    def __init__(self, network, proto=None, tuntap=None):
        if tuntap is None:
            tuntap = TunTap(self)
        if proto is None:
            proto = UDPPeerProtocol()
                        
        self.handlers = {}
        self._requested_acks = {}
                        
        self.network = network
        self.filter = Crypter(network.key)
        proto.router = self
        self.pm = PeerManager(self)
        self.ip_map = self.pm.ip_map
        
        self.pinger = Pinger(self)
        self.pinger.start()
                        
        self._proto = proto
        self._tuntap = tuntap
        self._port = None
        
        self.register_handler(self.ACK, self.handle_ack)
    
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
        
        logger.info('trying to connect to previously known peers')
        
        for pid in self.network.known_addresses:
            if pid not in self.pm:
                addrs = self.network.known_addresses[pid]
                self.pm.try_register(addrs)
            

        # re-schedule            
        reactor.callLater(60*5, self.try_old_peers)
    
    def relay(self, data, vip):
        if vip in self.pm:
            logger.debug('relaying packet to {0}'.format(vip.encode('hex')))
            self.send_udp(data, self.ip_map[vip])

#    def send_peer(self, type, data, peer, id=0):
#        if peer in self.pm:
#            return self.send(type, data, self.pm[peer].address, id)
    
    def send(self, type, data, dest, ack=False, id=0):
        '''Send a packet of type with data to address.  Address should be a vip if the peer is known, since address tuples aren't unique with relaying'''
        if type == self.DATA:
            data = pack('H', type) + data
            self.send_udp(data, dest)
        else:
            if dest in self.pm: # known peer dst
                peer = self.pm[dest]
                vip = peer.vip
                dest = peer.address
            else: # unknown peer dst (like for reg's)
                if isinstance(dest, str):
                    logger.warning('unknown dest {0} not an address tuple'.format(dest.encode('hex')))
                    return
                vip = pack('4B',0,0,0,0)

            if ack or id > 0: # want ack
                if id == 0:
                    id = random.randint(0, 0xFFFF)
                d = defer.Deferred()
                timeout_call = reactor.callLater(self.TIMEOUT, self._timeout, id)
                self._requested_acks[id] = (d, timeout_call)
            else:
                d = None            

            data = pack('2H', type, id) + vip + self.pm._self.vip + data
            
            #TODO exception handling for bad addresses
            self.send_udp(data, dest)
            
            return d

    def handle_ack(self, type, data, address, src):
        id = unpack('H', data)[0]
        logger.info('got ack with id {0}'.format(id))
        if id in self._requested_acks:
            d, timeout_call = self._requested_acks[id]
            del self._requested_acks[id]
            timeout_call.cancel()
            d.callback(None)

    def _timeout(self, id):
        if id in self._requested_acks:
            d = self._requested_acks[id][0]
            del self._requested_acks[id]
            d.errback(Exception('call {0} timed out'.format(id)))
            logger.info('ack timeout')
        else:
            logger.info('timeout called with bad id??!!?')
    
    def send_udp(self, data, address):
        data = self.filter.encrypt(data)
        self._proto.send(data, address)
    
    def send_packet(self, packet):
        '''Got a packet from the tun/tap device that needs to be sent out'''
#        src = unpack('4B',packet[12:16])
        dst = packet[16:20]
#        prot = unpack('1B',packet[9])[0]
        
        # if ip in peer list
        if dst in self.ip_map:
            self.send(self.DATA, packet, self.ip_map[dst])
        else:
            logger.debug('got packet on wire to unknown destination: {0}'.format(dst.encode('hex')))
                
    def recv_udp(self, data, address):
        '''Received a packet from the UDP port.  Parse it and send it on its way.'''
        data = self.filter.decrypt(data)
        # check if from known peer
        dt = unpack('H', data[:2])[0]
        
        if dt == self.DATA:
            self.recv_packet(data[2:])
            
        else:
            id = unpack('H', data[2:4])[0]
            dst = data[4:8]
            src = data[8:12]
            if dst == self.pm._self.vip or dst == '\x00\x00\x00\x00': #handle
                if dt in self.handlers:
                    # need to check if this is from a known peer?
                    self.handlers[dt](dt, data[12:], address, src)
                if id > 0: # ACK requested
                    logger.debug('sending ack')
                    self.send(self.ACK, data[2:4], src)
                logger.debug('handling {0} packet from {1}'.format(dt, src.encode('hex')))
            else: 
                self.relay(data, dst)
                logger.debug('relaying {0} packet to {1}'.format(dt, dst.encode('hex')))
    
        
    def recv_packet(self, packet):
        '''Got a data packet from a peer, need to inject it into tun/tap'''
        # check?
        #print 'get packet'
        dst = packet[16:20]
        if dst == self.pm._self.vip:
            self._tuntap.doWrite(packet)
        else:
            self.send_packet(packet)
            logger.debug('got packet with different dest ip, relay packet?')
           
        
    def recv_data(self, data):
        pass
        
    def register_handler(self, type, callback):
        '''Register a handler for a specific packet type.  Handles will be
        called as 'callback(type, data, address, vip)'.'''
        
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


