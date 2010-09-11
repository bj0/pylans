#! /usr/bin/env python
#TODO another way to check if an id is known, if there are going to be multiple networks using the same router...
#TODO make tun/tap both work, selectable

from crypto import Crypter
from event import Event
from peers import PeerManager
from pinger import Pinger
from struct import pack, unpack
from tuntap import TunTap
from twisted.internet import reactor, defer
from twisted.internet.protocol import DatagramProtocol
import logging
import random
import settings
import uuid
import util



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
    VERSION = pack('H', 0)
    
    TIMEOUT = 5 # 5s
    # packet types
    DATA = 1
    DATA_BROADCAST = 2
    ACK = 3
    
    USER = 0x80

    def __init__(self, network, proto=None, tuntap=None):
    
        if tuntap is None:
            mode = settings.get_option('settings/mode', TunTap.TAPMODE)
            tuntap = TunTap(self, mode)
        if proto is None:
            proto = UDPPeerProtocol()
                        
        logger.info('Initializing router in {0} mode.'.format('TAP' if tuntap.is_tap else 'TUN'))
                        
        self.handlers = {}
        self._requested_acks = {}
                        
        self.network = network
        self.filter = Crypter(network.key)
        proto.router = self
        self.pm = PeerManager(self)
        #self.ip_map = self.pm.ip_map
        self.addr_map = self.pm.addr_map
        
        self.pinger = Pinger(self)
        self.pinger.start()
                        
        self._proto = proto
        self._tuntap = tuntap
        self._port = None
        
        import bootstrap
        self._bootstrap = bootstrap.TrackerBootstrap(self.network)
        
        self.register_handler(self.ACK, self.handle_ack)

    def get_my_address(self):
        '''Get interface address (IP or MAC), return a deferred'''
        pass
    
    def start(self):
        '''Start the router.  Starts the tun/tap device and begins listening on
        the UDP port.'''
        
        self._tuntap.start()
        self._tuntap.configure_iface(self.network.virtual_address)
        self._port = reactor.listenUDP(self.network.port, self._proto)

        d = self.get_my_address()

        logger.info('router started, listening on UDP port {0}'.format(self._port))
    
        def start_connections(*x):
            self._bootstrap.run()
            reactor.callLater(1, self.try_old_peers)
            
        d.addCallback(start_connections)
    
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
    
    def relay(self, data, dst):
        if dst in self.pm:
            logger.debug('relaying packet to {0}'.format(repr(dst)))
            self.send_udp(data, self.pm[dst].address)

    
    def send(self, type, data, dst, ack=False, id=0):
        '''Send a packet of type with data to address.  Address should be a vip if the peer is known, since address tuples aren't unique with relaying'''
        if type == self.DATA or type == self.DATA_BROADCAST:
            data = pack('H', type) + data
            self.send_udp(data, dst)
            
        else:
            if dst in self.pm: # known peer dst
                peer = self.pm[dst]
                dst_id = peer.id.bytes
                dst = peer.address
                
            else: # unknown peer dst (like for reg's)
                if not isinstance(dst, tuple):
                    logger.warning('unknown dest {0} not an address tuple'.format(repr(dst)))
                    return
                dst_id = '\x00'*16

            if ack or id > 0: # want ack
                if id == 0:
                    id = random.randint(0, 0xFFFF)
                d = defer.Deferred()
                timeout_call = reactor.callLater(self.TIMEOUT, self._timeout, id)
                self._requested_acks[id] = (d, timeout_call)
                
            else:
                d = None            

            data = pack('2H', type, id) + dst_id + self.pm._self.id.bytes + data
            
            #TODO exception handling for bad addresses
            self.send_udp(data, dst)
            
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
        pass
                
    def recv_udp(self, data, address):
        '''Received a packet from the UDP port.  Parse it and send it on its way.'''
        data = self.filter.decrypt(data)
        # check if from known peer
        dt = unpack('H', data[:2])[0]
        
        if dt == self.DATA:
            self.recv_packet(data[2:])

        # should only be this on TAP
        elif dt == self.DATA_BROADCAST:
            logger.debug('got broadcast from {0}'.format(util.decode_mac(data[2:8])))
            if data[2:8] == self.pm._self.addr:
                self.recv_packet(data[8:])
            else:
                self.relay(data, data[2:8])

        else:
            id = unpack('H', data[2:4])[0]
            
            # get dst and src 128-bit UUIDs
            dst = data[4:20]
            src = data[20:36]

            if dst == self.pm._self.id.bytes or dst == '\x00'*16: #handle
                if dt in self.handlers:
                    # need to check if this is from a known peer?
                    self.handlers[dt](dt, data[36:], address, uuid.UUID(bytes=src))
                if id > 0: # ACK requested
                    logger.debug('sending ack')
                    self.send(self.ACK, data[2:4], src)
                logger.debug('handling {0} packet from {1}'.format(dt, src.encode('hex')))

            else: 
                self.relay(data, uuid.UUID(bytes=dst))
                logger.debug('relaying {0} packet to {1}'.format(dt, dst.encode('hex')))
    
        
    def recv_packet(self, packet):
        '''Got a data packet from a peer, need to inject it into tun/tap'''
        pass
                        
    def register_handler(self, type, callback):
        '''Register a handler for a specific packet type.  Handles will be
        called as 'callback(type, data, address, src_id)'.'''
        
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
            
class TapRouter(Router):
    addr_size = 6
    
    SIGNATURE = 'PVA'+Router.VERSION

    def get_my_address(self):
        '''Get interface address (MAC)'''
        # get mac addr
        self.pm._self.addr = self._tuntap.get_mac()

        d = defer.Deferred()
        def do_ips(ips=None):
            if ips is None:
                ips = self._tuntap.get_ips()
            if len(ips) > 0:
    #            ips = [x[0] for x in ips]
                if self.pm._self.vip_str not in ips:
                    logger.critical('TAP addresses ({0}) don\'t contain configured address ({1}), taking address from adapter ({2})'.format(ips,self.pm._self.vip_str, ips[0]))
                    self.pm._self.vip = util.encode_ip(ips[0])
            else:
                logger.crititcal('TAP adapater has no addresses')

            self.pm._update_pickle()
            
            reactor.callLater(0, d.callback, ips)
        
        # Grap VIP, so we display the right one
        ips = self._tuntap.get_ips()
        if len(ips) == 1 and ips[0] == '0.0.0.0': # interface not ready yet?
            logger.warning('Adapter not read, delaying...')
            reactor.callLater(3, do_ips)            
        else:
            do_ips(ips)

        return d    

    def send_packet(self, packet):
        '''Got a packet from the tun/tap device that needs to be sent out'''
#        print 'tunk:\n',packet[0:14].encode('hex')
        dst = packet[0:self.addr_size]
#        prot = unpack('1B',packet[9])[0]
        
        # if ip in peer list
        if dst in self.addr_map:
            self.send(self.DATA, packet, self.addr_map[dst])
        elif self._tuntap.is_broadcast(dst):
            logger.debug('sending broadcast packet')
            for mac in self.addr_map.keys():
                self.send(self.DATA_BROADCAST, mac+packet, self.addr_map[mac])
        else:
            logger.debug('got packet on wire to unknown destination: {0}'.format(dst.encode('hex')))

    def recv_packet(self, packet):
        '''Got a data packet from a peer, need to inject it into tun/tap'''
        # check?
        dst = packet[0:self.addr_size]

        if dst == self.pm._self.addr or self._tuntap.is_broadcast(dst):
            self._tuntap.doWrite(packet)

        else:
            self.send_packet(packet)
            logger.debug('got packet with different dest ip, relay packet?')
           
        

class TunRouter(Router):
    addr_size = 4

    SIGNATURE = 'PVU'+Router.VERSION

    def get_my_address(self):
        '''Get interface address (IP)'''
        ips = self._tuntap.get_ips()
        if len(ips) > 0:
#            ips = [x[0] for x in ips] # if we return (addr,mask)
            if self.pm._self.vip_str not in ips:
                logger.critical('TUN addresses ({0}) don\'t contain configured address ({1}), taking address from adapter ({2})'.format(ips,self.pm._self.vip_str, ips[0]))
                self.pm._self.vip = util.encode_ip(ips[0])
                self.pm._self.addr = self.pm._self.vip
        else:
            logger.crititcal('TUN adapater has no addresses')
            self.pm._self.addr = self.pm._self.vip

        self.pm._update_pickle()

    def send_packet(self, packet):
        '''Got a packet from the tun/tap device that needs to be sent out'''
#        print 'tunk:\n',packet[0:14].encode('hex')
        dst = packet[0:self.addr_size]
#        prot = unpack('1B',packet[9])[0]
        
        # if ip in peer list
        if dst in self.addr_map:
            self.send(self.DATA, packet, self.addr_map[dst])
        else:
            logger.debug('got packet on wire to unknown destination: {0}'.format(dst.encode('hex')))

    def recv_packet(self, packet):
        '''Got a data packet from a peer, need to inject it into tun/tap'''
        # check?
        dst = packet[0:self.addr_size]

        if dst == self.pm._self.addr:
            self._tuntap.doWrite(packet)
        else:
            self.send_packet(packet)
            logger.debug('got packet with different dest ip, relay packet?')

def get_router(*args, **kw):
    mode = settings.get_option('settings/mode', TunTap.TAPMODE)
    if mode == TunTap.TAPMODE:
        return TapRouter(*args, **kw)
    else:
        return TunRouter(*args, **kw)
