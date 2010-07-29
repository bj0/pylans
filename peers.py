# peers.py
# TODO reconnection stuff should save addresses/peer-id and only try those addresses if the peer-id isn't already connected
# TODO rsa key exchange - new 'packet format'

import logging

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
    REG_TRY_DELAY = 1
    PX_TRY_DELAY = 1

    # packet types
    REGISTER = 4
    REGISTER_ACK = 5
    PEER_XCHANGE = 6
    PEER_XCHANGE_ACK = 7
    PEER_ANNOUNCE = 8
    
    def __init__(self, router):
        self.peer_list = {}
        self.peer_map = {}
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
                
        # incase there are changes to vip and name
        if opi.vip != npi.vip:
            logger.debug('updating peer info with new virtual ip')
            self.remove_peer(opi)
            self.add_peer(npi)
        else:
            opi.update(npi)

    
    ###### Announce Functions
    
    def send_announce(self, peer):
        '''Send an announce about peer to all known connections'''
        peerkle = pickle.dumps(peer, -1)
        for p in self.peer_list.values():
            if p.id != peer.id:
                self.router.send(self.PEER_ANNOUNCE, peerkle, p.address)
                logger.debug('sending announce about {0} to {1}'.format(peer.id, p.id))
        
    
    def handle_announce(self, type, packet, address):
        logger.debug('received an announce packet from {0}'.format(address))
        pi = pickle.loads(packet)
        if pi.id != self._self.id:
            if pi.id not in self:
                logger.debug('announce for unknown peer {0}, trying to connect'.format(pi.name))
                self.try_register(pi.address)
            else:
                self.update_peer(self.peer_list[pi.id],pi)
    
    ###### Peer XChange Functions
    
    def try_px(self, pid):
        '''Initiate a peer exchange by sending a px packet.  The packet will be
        resent until an ack packet is recieved or MAX_PX_TRIES packets have been sent.
        This px packet includes the pickled peer list.'''
        
        logger.debug('initiating a peer exchange with {0}'.format(self.peer_list[pid].name))
        
        def send_px(i):
            if i <= self.MAX_PX_TRIES and pid not in self.peer_map:
                return
            else:
                logger.debug('sending PX packet #{0}'.format(i))
                self.router.send(self.PEER_XCHANGE, pickle.dumps(self.peer_list,-1), self.peer_list[pid].address)
                reactor.callLater(self.PX_TRY_DELAY, send_px, i+1)
                
        reactor.callLater(self.PX_TRY_DELAY, send_px, 0)

    def handle_px(self, type, packet, address):
        '''Handle a peer exchange packet.  Load the peer list with the px packet 
        and send an ack packet with own peer list.'''
        
        peer_list = pickle.loads(packet)
            
        # reply
        logger.debug('received a PX packet, sending PX ACK')
        self.router.send(self.PEER_XCHANGE_ACK, pickle.dumps(self.peer_list,-1), address)
        self.parse_peer_list(self.get_by_address(address), peer_list)
            

    def handle_px_ack(self, type, packet, address):
        '''
            Handle a px ack packet by parsing incoming peer list
        '''
        
        logger.debug('received a PX ACK packet')
        
        peer_list = pickle.loads(packet)
        self.parse_peer_list(self.get_by_address(address), peer_list)
    
    def parse_peer_list(self, from_peer, peer_list):
        '''Parse a peer list from a px packet'''
        
        if from_peer.id not in self.peer_map:
            self.peer_map[from_peer.id] = peer_list

        for peer in peer_list:
            if peer.id != self._self.id:
                if peer.id in self.peer_list:
                    pass # known peer
                else:
                    self.try_register(peer.address)
                
            # generate map?
    
    
    
    ###### Peer Register Functions
    
    def try_register(self, address):
        '''Try to register self with a peer by sending a register packet
        with own peer info.  Will continue to send this packet until an 
        ack is received or MAX_REG_TRIES packets have been sent.'''
        
        logger.debug('initiating a register xchange with {0}'.format(address))
        
        if not (address in self.router.pm):
            
            def send_register(i):
                '''Send a register packet and re-queues self'''
                if i <= self.MAX_REG_TRIES and address not in self.router.pm:
                    logger.debug('sending REG packet #{0}'.format(i))
                    self.router.send(self.REGISTER, self._my_pickle, address)
                    reactor.callLater(self.REG_TRY_DELAY, send_register, i+1)
                    
            reactor.callLater(self.REG_TRY_DELAY, send_register, 0)
        else:
            logger.debug('address {0} already in peer list'.format(address))
                    
    def handle_reg(self, type, packet, address):
        '''Handle incoming reg packet by adding new peer and sending ack.'''
        
        logger.debug('received REG packet, sending ACK')
        
        pi = pickle.loads(packet)    
        if pi.id not in self.peer_list:
            logger.info('received a register from a new peer {0}'.format(pi.name))
            pi.address = address
            self.add_peer(pi)
            self.try_px(pi)
        else:
            self.update_peer(self.peer_list[pi.id], pi)

        self.router.send(self.REGISTER_ACK, self._my_pickle, address)
                
        
    def handle_reg_ack(self, type, packet, address):
        '''Handle reg ack by adding new peer'''
        
        logger.debug('received REG ACK packet')
        
        pi = pickle.loads(packet)

        if pi.id not in self.peer_list:
            logger.info('received REG ACK packet from new peer {0}'.format(pi.name))
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
        if isinstance(item, PeerInfo) and item in self:
            return item
            
        if isinstance(item, tuple):                     # address
            peer = self.get_by_address(item)
                
        elif isinstance(item, uuid.UUID):               # peer id
            peer = self.peer_list[item]
            
        elif isinstance(item, str):  # name
            peer = self.get_by_name(item)
        else:
            raise TypeError('Unrecognized key type')

        if peer is None:
            raise KeyError('Address not in peer list.')
        else:
            return peer

    
    def __contains__(self, item):
        if isinstance(item, PeerInfo):
            return item.id in self.peer_list        
        if isinstance(item, tuple):                     # address
            return self.get_by_address(item) is not None
        elif isinstance(item, uuid.UUID):               # peer id
            return (item in self.peer_list)
        elif isinstance(item, str):  # name
            return self.get_by_name(item) is not None
    


