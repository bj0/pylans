#! /usr/bin/env python

from struct import pack, unpack
import sys
import uuid
import cPickle as pickle

from OpenSSL import SSL
from zope.interface import implements
from twisted.internet import reactor, defer, utils, protocol, ssl
from twisted.internet.protocol import DatagramProtocol, Factory, ClientFactory, Protocol
from twisted.internet.task import LoopingCall

from event import Event
from tuntap import TunTap
from crypto import Crypter
from pinger import Pinger
import config

class PeerInfo(object):
    
    def __init__(self):
        self.id = 0                     # unique peer id
        self.name = 'wop'
        self.address = ('ip','port')
        self.vip = 0                    # virtual ip
        self.real_ips = []              # list of known real ips
        self.is_direct = False          # is this peer direct connected?
        self.relay_id = 0               # if not, who is the relay
        self.ping_time = 0              #
        self.timeouts = 0               # tracking ping timeouts
        
        
class PeerManager(object):
    
    def __init__(self, router):
        self.peer_list = {}
        self.ip_map = {}
        
        self.router = router
        router.register_handler(Router.PEER_XCHANGE, self.handle_px)
        router.register_handler(Router.PEER_XCHANGE_ACK, self.handle_px_ack)
        router.register_handler(Router.REGISTER, self.handle_reg)
        router.register_handler(Router.REGISTER_ACK, self.handle_reg_ack)
        
        # Events
        self.peer_added = Event()
        self.peer_removed = Event()

    def add_peer(self, peer):
        if peer.id not in self.peer_list:
            self.peer_list[peer.id] = peer
            self.ip_map[peer.vip] = peer.address
            
            # fire event
            self.peer_added(peer)
            
    def remove_peer(self, peer):
        if peer.id in self.peer_list:
            del self.peer_list[peer.id]
            del self.ip_map[peer.vip]
            
            # fire event
            self.peer_removed(peer)
            
    def get_by_name(self, name):
        for p in self.peer_list.values():
            if p.name == name:
                return p
        return None
            
    def get_by_vip(self, vip):
        for p in self.peer_list.values():
            if p.vip == vip:
                return p
        return None
            
    def get_by_address(self, address):
        for p in self.peer_list.values():
            if p.address == address:
                return p
        return None
        
    def timeout(self, peer):
        print 'peer timed out', Router.decode_ip(peer.vip)
        self.remove_peer(peer)
        
        
        
    ###### Peer XChange Functions
    
    def handle_px(self, type, packet, address):
        peer_list = pickle.loads(packet)
            
        # reply
        self.router.send(Router.PEER_XCHANGE_ACK, pickle.dumps(self.peer_list), address)
        self.parse_peer_list(peer_list)
            

    def handle_px_ack(self, type, packet, address):
        peer_list = pickle.loads(packet)
        self.parse_peer_list(peer_list)
    
    def parse_peer_list(self, peer_list):
        pass
    
    
    
    ###### Peer Register Functions
    
    def try_register(self, address):
        if not (address in self.router.pm):
            print 'here'
            
            def send_register(i):
                print 'sendreg',i
                if i > 10 or address in self.router.pm:
                    return
                else:
                    self.router.send(Router.REGISTER, self.router._my_pickle, address)
                    reactor.callLater(1, send_register, i+1)
                    
            reactor.callLater(1, send_register, 0)
        else:
            print 'wtf'
                    
    def handle_reg(self, type, packet, address):
        pi = pickle.loads(packet)    
        if pi.id not in self.peer_list:
            print 'register from new peer',pi.id
            pi.address = address
            self.add_peer(pi)

        self.router.send(Router.REGISTER_ACK, self.router._my_pickle, address)
        print 'sent ack to ',address
                
        
    def handle_reg_ack(self, type, packet, address):
        pi = pickle.loads(packet)
        print 'got a register ack from',address

        if pi.id not in self.peer_list:
            print 'ack with new peer',pi.id
            pi.address = address
            self.add_peer(pi)
                
                
                
    ###### Container Type Overloads
    
    def iterkeys(self):
        for peer in self.peer_list:
            yield peer
    
    def __iter__(self):
        return self.iterkeys()
    
    def __len__(self):
        return len(self.peer_list)
    
    def __getitem__(self, item):
        if isinstance(item, tuple):                     # address
            peer = self.get_by_address(item)
                
        elif isinstance(item, uuid.UUID):               # peer id
            peer = self.peer_list[item]
            
        elif isinstance(item, str) and len(item) == 4:  # IP
            peer = self.get_by_vip(item)
        else:
            raise TypeError('Unrecognized key type')

        if peer is None:
            raise KeyError('Address not in peer list.')
        else:
            return peer

    
    def __contains__(self, item):
        if isinstance(item, tuple):                     # address
            return self.get_by_address(item) is not None
        elif isinstance(item, uuid.UUID):               # peer id
            return (item in self.peer_list)
        elif isinstance(item, str) and len(item) == 4:  # IP
            return (item in self.ip_map)
    

class UDPPeerProtocol(DatagramProtocol):
#    def __init__(self):
#    def __init__(self, router):
#        self.router = router
#        self.receive = Event()

    def send(self, data, address):
        try:
            self.transport.write(data, address)
        except:##TODO this is here because UDP socket fills up and just dies
            pass

    def datagramReceived(self, data, address):
#        self.receive(data, address)
        self.router.recv_udp(data, address)
#        print 'got:', data
#        print address
                
    def connectionRefused(self):
        pass
            

class Router(object):
    SIGNATURE = 'p2p'
    
    # packet types
    DATA = 1
    CONTROL = 2
    REGISTER = 4
    REGISTER_ACK = 5
    PEER_XCHANGE = 6
    PEER_XCHANGE_ACK = 7
    
    USER = 0x80

    def __init__(self, proto=None, tuntap=None):
        if tuntap is None:
            tuntap = TunTap(self)
        if proto is None:
            proto = UDPPeerProtocol()
                        
        self._self = PeerInfo()
        self._self.id = uuid.uuid4()
        self._self.name = config.name
        self._self.vip = self.encode_ip(config.address.split('/')[0])
        self._my_pickle = pickle.dumps(self._self)
              
#        self.handle_packet = Event()
        self.handlers = {}
                        
        self.filter = Crypter(config.key)
#        proto.receive += self.recv_udp
        proto.router = self
        self.pm = PeerManager(self)
        tuntap.start()
        
        self.pinger = Pinger(self)
        self.pinger.start()
                        
        self._proto = proto
        self._tuntap = tuntap
    
    def send(self, type, data, address):
        data = pack('H', type) + data
        data = self.filter.encrypt(data)
        self._proto.send(data, address)
    
    def send_udp(self, data, address):
        self._proto.send(data, address)
    
    def send_packet(self, packet):
        '''Got a packet from the tun/tap that needs to be sent out'''
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
#        self.send(self.DATA, packet)
                
    def send_data(self, data):
        pass

    def recv_udp(self, data, address):
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
#            self.handle_packet(dt, data, address)
    
        
    def recv_packet(self, packet):
        '''Got a packet from a peer, need to inject it into tun/tap'''
        # check?
        #print 'get packet'
        self._tuntap.doWrite(packet)
        
    def recv_data(self, data):
        pass
        
    def register_handler(self, type, callback):
        if type in self.handlers:
            self.handlers[type] += callback
        else:
           self.handlers[type] = Event()
           self.handlers[type] += callback
           
    def unregister_handler(self, type, callback):
        if type in self.handlers:
            self.handlers[type] -= callback

    @classmethod
    def encode_ip(cls, ip):
        return pack('4B', *[int(x) for x in ip.split('.')])
        
    @classmethod
    def decode_ip(cls, ip):
        return '.'.join([str(x) for x in unpack('4B', ip)])

if __name__ == '__main__':


    rt = Router()
    rt._tuntap.configure_iface(config.address)
    reactor.listenUDP(config.port, rt._proto)        
    if sys.argv[1] == 'c':
            rt.pm.try_register(('10.10.10.216',8015))

    print 'run'
    reactor.run()
