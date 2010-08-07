# peers.py
# TODO reconnection stuff should save addresses/peer-id and only try those addresses if the peer-id isn't already connected
# TODO rsa key exchange - new 'packet format'

import logging
import cPickle as pickle
import uuid

from twisted.internet import reactor

import event
import util

logger = logging.getLogger(__name__)

class PeerInfo(object):
    '''Represents a peer connection'''   
    def __init__(self):
        self.id = 0                     # unique peer id
        self.name = 'wop'
        self.alias = None
        self.address = ('ip','port')
        self.vip = 0                    # virtual ip
        self.real_ips = []              # list of known real ips
        self.is_direct = False          # is this peer direct connected?
        self.relays = 0
        self.relay_id = 0               # if not, who is the relay
        self.ping_time = 0              #
        self.timeouts = 0               # tracking ping timeouts
        
    def update(self, peer):
        self.name = peer.name
        self.vip = peer.vip

    @property
    def vip_str(self):
        return util.decode_ip(self.vip)

class PeerManager(object):
    '''Manages peer connections'''
    MAX_REG_TRIES = 5
    MAX_PX_TRIES = 5
    REG_TRY_DELAY = 2
    PX_TRY_DELAY = 2

    # packet types
    REGISTER = 4
    REGISTER_ACK = 5
    PEER_XCHANGE = 6
    PEER_XCHANGE_ACK = 7
    PEER_ANNOUNCE = 8
    
    def __init__(self, router):
        self.peer_list = {}
        self.peer_map = {}
        self.relay_list = {}
        self.relay_map = {}
        self.ip_map = {}
        
        self._self = PeerInfo()
        self._self.id = router.network.id
        self._self.name = router.network.username
        self._self.vip = util.encode_ip(router.network.ip)
        self._my_pickle = pickle.dumps(self._self,-1)

        self.router = router
        router.register_handler(self.PEER_XCHANGE, self.handle_px)
        router.register_handler(self.PEER_XCHANGE_ACK, self.handle_px_ack)
        router.register_handler(self.REGISTER, self.handle_reg)
        router.register_handler(self.REGISTER_ACK, self.handle_reg_ack)
        router.register_handler(self.PEER_ANNOUNCE, self.handle_announce)
        
        # Events
#        self.peer_added = Event()
#        self.peer_removed = Event()

    def add_peer(self, peer):
        '''Add a peer connection'''
        if peer.id not in self.peer_list:
            self.peer_list[peer.id] = peer
            self.ip_map[peer.vip] = peer.address
            
            # fire event
            event.emit('peer-added', self, peer)
            self.send_announce(peer)
#            self.peer_added(peer)
                        
    def remove_peer(self, peer):
        '''Remove a peer connection'''
        if peer.id in self.peer_list:
            del self.peer_list[peer.id]
            del self.ip_map[peer.vip]
            
            # fire event
#            self.peer_removed(peer)
            event.emit('peer-removed', self, peer)
            
    def get_by_name(self, name):
        '''Get a peer connection by peer name'''
        for p in self.peer_list.values():
            if p.name == name:
                return p
        return None
            
    def get_by_vip(self, vip):
        '''Get a peer connection by virtual ip'''
        for p in self.peer_list.values():
            if p.vip == vip:
                return p
        return None
            
    def get_by_address(self, address):
        '''Get a peer connection by real (ip,port)'''
        for p in self.peer_list.values():
            if p.address == address:
                return p
        return None
        
    def _timeout(self, peer):
        logger.warning('peer {0} on network {1} timed out'.format(peer.name, self.router.network.name))
        self.remove_peer(peer)
           
           
    def update_peer(self, opi, npi):
        changed = False                
        if opi.vip != npi.vip:
            self.ip_map[npi.vip] = self.ip_map[opi.vip]
            del self.ip_map[opi.vip]
            opi.vip = npi.vip
            changed = True
            logger.info('peer {0} vip changed.'.format(opi.id))
        if (opi.relays >= npi.relays and opi.address != npi.address):
            self.ip_map[opi.vip] = npi.address
            opi.address = npi.address
            opi.relays = npi.relays
            opi.is_direct = (opi.relays == 0)
            changed = True
            logger.info('peer {0} relay changed.'.format(opi.id))
        if opi.name != npi.name:
            opi.name = npi.name
            changed = True            
            logger.info('peer {0} name changed.'.format(opi.id))

        if changed:
            # fire event
            event.emit('peer-changed', self, opi)
            self.send_announce(opi)
            
    
    ###### Announce Functions
    
    def send_announce(self, peer, address=None):
        '''Send an announce about peer to all known connections'''
        if peer.id != self._self.id:
            peer.relays += 1 # inc relay so routing works right
            peerkle = pickle.dumps(peer, -1)
            peer.relays -= 1
        else:
            peerkle = pickle.dumps(peer, -1)
            
        if address is not None:
            self.router.send(self.PEER_ANNOUNCE, peerkle, address)        
            logger.info('sending announce about {0} to {1}'.format(peer.id, address))
        else:
            for p in self.peer_list.values():
                if p.id != peer.id:
                    self.router.send(self.PEER_ANNOUNCE, peerkle, p.address)
                    logger.info('sending announce about {0} to {1}'.format(peer.id, p.id))
        
    
    def handle_announce(self, type, packet, address, vip):
        logger.info('received an announce packet from {0}'.format(address))
        pi = pickle.loads(packet)
        if pi.id != self._self.id:
            if pi.id not in self:
                if pi.relays == 0:
                    pi.address = address
                    pi.is_direct = True
                    self.add_peer(pi)
                    self.send_announce(self._self, address)
                    logger.info('announce from unknown peer {0}, adding and announcing self'.format(pi.name))
                else:
                    self.add_relay(pi, address)
                    logger.info('announce for unknown peer {0}, trying to connect'.format(pi.name))
                    self.try_register(pi.address)
            else:
                pi.address = address
                self.update_peer(self.peer_list[pi.id],pi)
    
    ###### Peer XChange Functions
    
    def try_px(self, peer):
        '''Initiate a peer exchange by sending a px packet.  The packet will be
        resent until an ack packet is recieved or MAX_PX_TRIES packets have been sent.
        This px packet includes the pickled peer list.'''
        
        logger.info('initiating a peer exchange with {0}'.format(peer.name))
        
        def send_px(i):
            if i <= self.MAX_PX_TRIES and peer.id not in self.peer_map:
                self.router.send(self.PEER_XCHANGE, pickle.dumps(self.peer_list,-1), peer.address)
                logger.debug('sending PX packet #{0}'.format(i))
 
                reactor.callLater(self.PX_TRY_DELAY, send_px, i+1)
                
        reactor.callLater(self.PX_TRY_DELAY, send_px, 0)

    def handle_px(self, type, packet, address, vip):
        '''Handle a peer exchange packet.  Load the peer list with the px packet 
        and send an ack packet with own peer list.'''
        
        peer_list = pickle.loads(packet)
            
        # reply
        logger.info('received a PX packet, sending PX ACK')
        self.router.send(self.PEER_XCHANGE_ACK, pickle.dumps(self.peer_list,-1), address)
        self.parse_peer_list(self[vip], peer_list)
            

    def handle_px_ack(self, type, packet, address, vip):
        '''
            Handle a px ack packet by parsing incoming peer list
        '''
        
        logger.info('received a PX ACK packet')
        
        peer_list = pickle.loads(packet)
#        print 'px',vip.encode('hex')
        self.parse_peer_list(self[vip], peer_list)
    
    def parse_peer_list(self, from_peer, peer_list):
        '''Parse a peer list from a px packet'''
        
#        if from_peer.id not in self.peer_map:
        self.peer_map[from_peer.id] = peer_list

        for peer in peer_list.values():
            if peer.id != self._self.id:
                peer.relays += 1
                if peer.id in self.peer_list:
                    self.update_peer(self.peer_list[peer.id],peer)
                else:
                    self.try_register(peer.address)
                    self.add_relay(peer, from_peer.address)
                
            # generate map?
    
    def add_relay(self, peer, relay_addr):
        peer.is_direct = False
        peer.relay = self[relay_addr]
        peer.address = relay_addr
        self.add_peer(peer)
        
    
    
    ###### Peer Register Functions
    
    def try_register(self, address):
        '''Try to register self with a peer by sending a register packet
        with own peer info.  Will continue to send this packet until an 
        ack is received or MAX_REG_TRIES packets have been sent.'''
        
        logger.info('initiating a register xchange with {0}'.format(address))
        
        if (address not in self.router.pm):
            
            def send_register(i):
                '''Send a register packet and re-queues self'''
                if i <= self.MAX_REG_TRIES and address not in self.router.pm:
                    logger.debug('sending REG packet #{0}'.format(i))
                    self.router.send(self.REGISTER, self._my_pickle, address)
                    reactor.callLater(self.REG_TRY_DELAY, send_register, i+1)

            reactor.callLater(self.REG_TRY_DELAY, send_register, 0)
        else:
            logger.debug('address {0} already in peer list'.format(address))
                    
    def handle_reg(self, type, packet, address, vip):
        '''Handle incoming reg packet by adding new peer and sending ack.'''
        
        logger.info('received REG packet, sending ACK')
        
        pi = pickle.loads(packet)    
        if pi.id == self._self.id:
            # we sent a reg to ourself?
            pass
        elif pi.id not in self.peer_list:
            logger.info('received a register from a new peer {0}'.format(pi.name))
            pi.address = address
            pi.is_direct = (pi.relays == 0)
            self.add_peer(pi)
            self.try_px(pi)
        else:
            pi.address = address
            pi.is_direct = (pi.relays == 0)
            self.update_peer(self.peer_list[pi.id], pi)

        self.router.send(self.REGISTER_ACK, self._my_pickle, address)
                
        
    def handle_reg_ack(self, type, packet, address, vip):
        '''Handle reg ack by adding new peer'''
        
        logger.info('received REG ACK packet')
        
        pi = pickle.loads(packet)

        if pi.id == self._self.id:
            # yea yea...
            pass
        elif pi.id not in self.peer_list:
            logger.info('received REG ACK packet from new peer {0}'.format(pi.name))
            pi.address = address
            pi.is_direct = (pi.relays == 0)
            self.add_peer(pi)
            self.try_px(pi)
        else:
            pi.address = address
            pi.is_direct = (pi.relays == 0)
            self.update_peer(self.peer_list[pi.id], pi)
                
                
    ###### Container Type Overloads
    
    def iterkeys(self):
        for peer in self.peer_list:
            yield peer
    
    def __iter__(self):
        return self.iterkeys()
    
    def __len__(self):
        return len(self.peer_list)
    
    def __getitem__(self, item):
        if isinstance(item, PeerInfo) and item in self:
            return item
            
        if isinstance(item, tuple):                     # address
            peer = self.get_by_address(item)
                
        elif isinstance(item, uuid.UUID):               # peer id
            peer = self.peer_list[item]
            
        elif isinstance(item, str):  # name
            peer = self.get_by_name(item)
            if peer is None:
                peer = self.get_by_vip(item)
        else:
            raise TypeError('Unrecognized key type')

        if peer is None:
            raise KeyError('Address {0} not in peer list.'.format(repr(item)))
        else:
            return peer

    
    def __contains__(self, item):
        if isinstance(item, PeerInfo):
            return item.id in self.peer_list        
        if isinstance(item, tuple):                     # address
            return self.get_by_address(item) is not None
        elif isinstance(item, uuid.UUID):               # peer id
            return (item in self.peer_list)
        elif isinstance(item, str):  # name or vip
            return (self.get_by_name(item) is not None) or \
                    (item in self.ip_map)
    


