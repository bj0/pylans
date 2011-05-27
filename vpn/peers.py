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
# peers.py
# TODO rsa key exchange - new 'packet format'
# TODO local clients behind a firewall that use an external intermediary need a way to
#     realize that they can DC using local addresses
# TODO NAT port re-write not taken into account

import cPickle as pickle
import logging
from twisted.internet import reactor, defer
import os
from struct import pack, unpack
import util
from util import event

import hmac, hashlib

logger = logging.getLogger(__name__)

class PeerInfo(object):
    '''Represents a peer connection'''
    def __init__(self):
        self.id = 0                     # unique peer id
        self.name = 'wop'
        self.alias = None
        self.address = ('ip','port')
        self.direct_addresses = []
        self.port = 0                   # listening port
        self.addr = 0                   # can be vip or mac
        self.vip = 0                    # virtual ip
        self.is_direct = False          # is this peer direct connected?
        self.relays = 0
        self.relay_id = 0               # if not, who is the relay
        self.ping_time = 0              #
        self.timeouts = 0               # tracking ping timeouts


    @property
    def vip_str(self):
        return util.decode_ip(self.vip)

    @property
    def addr_str(self):
        if len(self.addr) == 4:
            return util.decode_ip(self.addr)
        else:
            return util.decode_mac(self.addr)

class PeerManager(object):
    '''Manages peer connections'''
    MAX_REG_TRIES = 5
    MAX_PX_TRIES = 5
    REG_TRY_DELAY = 2
    PX_TRY_DELAY = 2

    # packet types
    GREET = 14
    HANDSHAKE = 15
    HANDSHAKE_ACK = 16
    PEER_XCHANGE = 17
    PEER_XCHANGE_ACK = 18
    PEER_ANNOUNCE = 19
    REGISTER = 20
    REGISTER_ACK = 21

    def __init__(self, router):
        # list of peers
        self.peer_list = {}
        # addr to (address,port)
        self.addr_map = {}
        # addr to (address,port) for relays
        self.relay_map = {}
        # id's shaking hands -> nonce
        self.shaking_peers = {}
        # id -> session key
        #self.session_map = {}

        # for display purposes
        self.peer_map = {}

        # my info
        self._self = PeerInfo()
        self._self.id = router.network.id
        self._self.name = router.network.username
        self._self.vip = util.encode_ip(router.network.ip)
        self._self.addr = '\x00'*router.addr_size # temp fake mac?
        self._self.port = router.network.wan_port
        self._my_pickle = pickle.dumps(self._self,-1)

        # packet handlers
        self.router = util.get_weakref_proxy(router)
        self.sm = util.get_weakref_proxy(self.router.sm)
        router.register_handler(self.PEER_XCHANGE, self.handle_px)
        router.register_handler(self.PEER_XCHANGE_ACK, self.handle_px_ack)
        router.register_handler(self.REGISTER, self.handle_reg)
        router.register_handler(self.REGISTER_ACK, self.handle_reg_ack)
        router.register_handler(self.PEER_ANNOUNCE, self.handle_announce)
        router.register_handler(self.GREET, self.handle_greet)
        router.register_handler(self.HANDSHAKE, self.handle_handshake)
        router.register_handler(self.HANDSHAKE_ACK, self.handle_handshake_ack)


    #def clear(self):
    #    self.peer_list = {}
    #    self.peer_map = {}
    #    self.addr_map = {}
    #    self.relay_map = {}
    #    self.shaking_peers = {}

    def _update_pickle(self):
        self._my_pickle = pickle.dumps(self._self,-1)

        # should announce my change to my peerz
        self.send_announce(self._self, None)

    def add_peer(self, peer):
        '''Add a peer connection'''
        if peer.id not in self.peer_list:
            if peer.relays > 0:
                peer.is_direct = False
                peer.relay_id = self[peer.address].id
                #self.try_register(peer)
                self.relay_map[peer.addr] = (peer.address, peer.id)
            else:
                peer.is_direct = True
                peer.relay_id = None
                if peer.address not in peer.direct_addresses:
                    peer.direct_addresses.append(peer.address)
                self.addr_map[peer.addr] = (peer.address, peer.id)
                if peer.addr in self.relay_map:
                    del self.relay_map[peer.addr]

            self.peer_list[peer.id] = peer

            # fire event
            event.emit('peer-added', self, peer)
            self.send_announce(peer)
            self.try_px(peer)

    def remove_peer(self, peer):
        '''Remove a peer connection'''
        if peer.id in self.peer_list:
            del self.peer_list[peer.id]
#        if peer.id in self.relay_list[peer.id]:
#            del self.relay_list[peer.id]
#        if peer.vip in self.ip_map:
#            del self.ip_map[peer.vip]
        if peer.addr in self.addr_map:
            del self.addr_map[peer.addr]
        if peer.addr in self.relay_map:
            del self.relay_map[peer.addr]

            # fire event
#            self.peer_removed(peer)
        event.emit('peer-removed', self, peer)

    def _timeout(self, peer):
        logger.warning('peer {0} on network {1} timed out'.format(peer.name, self.router.network.name))
        self.remove_peer(peer)


    def update_peer(self, opi, npi):
        changed = False
        if (opi.relays >= npi.relays and opi.address != npi.address):
            #self.addr_map[opi.addr] = npi.address
            if npi.relays > 0:
                self.relay_map[opi.addr] = npi.address
            else:
                del self.relay_map[opi.addr]
                self.addr_map[opi.addr] = (npi.address, npi.id)

            opi.address = npi.address
            opi.relays = npi.relays
            opi.is_direct = (opi.relays == 0)

            #relay id? TODO
            changed = True
            logger.info('peer {0} relay changed.'.format(opi.id))

        if opi.addr != npi.addr:
            # check for collision? TODO
            if opi.addr in self.addr_map:
                self.addr_map[npi.addr] = self.addr_map[opi.addr]
                del self.addr_map[opi.addr]
            if opi.addr in self.relay_map:
                self.relay_map[npi.addr] = self.relay_map[opi.addr]
                del self.relay_map[opi.addr]
            opi.addr = npi.addr
            changed = True
            logger.info('peer {0} addr changed.'.format(opi.id))

        if opi.vip != npi.vip:
            # check for collision TODO
            opi.vip = npi.vip
            changed = True
            logger.info('peer {0} vip changed.'.format(opi.id))

        if opi.name != npi.name:
            opi.name = npi.name
            changed = True
            logger.info('peer {0} name changed.'.format(opi.id))

        if set(opi.direct_addresses) != set(npi.direct_addresses):
            # combine direct_addresses (w/out dupes)
            opi.direct_addresses = list(set(opi.direct_addresses).union(set(npi.direct_addresses)))
            changed = True
            logger.info('peer {0} good addresses changed. ({1})'.format(opi.id, opi.direct_addresses))

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
            #peerkle = pickle.dumps(peer, -1)
            peerkle = self._my_pickle

        if address is not None:
            self.sm.send(self.PEER_ANNOUNCE, peerkle, address)
            logger.info('sending announce about {0} to {1}'.format(peer.id, address))
        else:
            for p in self.peer_list.values():
                if p.id != peer.id:
                    self.sm.send(self.PEER_ANNOUNCE, peerkle, p)
                    logger.info('sending announce about {0} to {1}'.format(peer.id, p.id))


    def handle_announce(self, type, packet, address, src_id):
        logger.info('received an announce packet from {0}'.format(address))
        #packet = self.sm.decode(src_id, packet)
        pi = pickle.loads(packet)
        if pi.id != self._self.id:
            if pi.id not in self.sm:
                # init (relayed) handshake
                self.send_handshake(pi.id, address, pi.relays)
            elif pi.id not in self.peer_map:
                if pi.relays == 0: #potential replacement for reg packets? TODO
                    pi.address = address
                    self.add_peer(pi)
                    logger.info('announce from unknown peer {0}, adding and announcing self'.format(pi.name))
                else:
                    pi.address = address
                    self.add_peer(pi)
                    logger.info('announce for unknown peer {0}, trying to connect'.format(pi.name))
            else:
                pi.address = address
                self.update_peer(self.peer_list[pi.id], pi)

    ###### Peer XChange Functions

    def try_px(self, peer):
        '''Initiate a peer exchange by sending a px packet.  The packet will be
        resent until an ack packet is recieved or MAX_PX_TRIES packets have been sent.
        This px packet includes the pickled peer list.'''

        logger.info('initiating a peer exchange with {0}'.format(peer.name))

        def send_px(i):
            if i <= self.MAX_PX_TRIES and peer.id not in self.peer_map:
                self.sm.send(self.PEER_XCHANGE, pickle.dumps(self.peer_list,-1), peer)
                logger.debug('sending PX packet #{0}'.format(i))

                reactor.callLater(self.PX_TRY_DELAY, send_px, i+1)

        reactor.callLater(self.PX_TRY_DELAY, send_px, 0)

    def handle_px(self, type, packet, address, src_id):
        '''Handle a peer exchange packet.  Load the peer list with the px packet
        and send an ack packet with own peer list.'''

        #packet = self.sm.decode(src_id, packet)
        peer_list = pickle.loads(packet)

        # reply
        logger.info('received a PX packet, sending PX ACK')
        self.sm.send(self.PEER_XCHANGE_ACK, pickle.dumps(self.peer_list,-1), src_id)
        self.parse_peer_list(self[src_id], peer_list)


    def handle_px_ack(self, type, packet, address, src_id):
        '''
            Handle a px ack packet by parsing incoming peer list
        '''

        logger.info('received a PX ACK packet')

        #packet = self.sm.decode(src_id, packet)
        peer_list = pickle.loads(packet)
        self.parse_peer_list(self[src_id], peer_list)

    def parse_peer_list(self, from_peer, peer_list):
        '''Parse a peer list from a px packet'''

#        if from_peer.id not in self.peer_map:
        self.peer_map[from_peer.id] = peer_list

        for peer in peer_list.values():
            if peer.id != self._self.id:
                peer.relays += 1
                peer.address = from_peer.address

                if peer.id in self.peer_list:
                    self.update_peer(self.peer_list[peer.id],peer)
                else:
                    self.add_peer(peer)

            # generate map?



    ###### Peer Register Functions

    def try_greet(self, addrs):
        if isinstance(addrs, tuple):
            # It's an (address,port) pair
            addrs = [addrs]

        elif isinstance(addrs, PeerInfo):
            if addrs.is_direct:
                # don't need to...
                return #TODO return a defffffer?

            # it's a peer, try direct_addresses
            # if a NAT scrambled the port, re-add it to the list for each IP
            # list(set()) to eliminate duplicates
            try:
                addrs = \
                    list(set([ (x[0], addrs.port) for x in addrs.direct_addresses
                                                        if x[1] != addrs.port])) \
                        + addrs.direct_addresses
            except AttributeError: # if .port undefined (pre bzr rev 61)
                addrs = addrs.direct_addresses

        elif not isinstance(addrs, list):
            logger.error('try_greet called with incorrect parameter: {0}'.format(addrs))
            return #TODO defferrr?

        main_d = defer.Deferred()

        def try_address(err, j):
            if j < len(addrs):
                address = addrs[j]
                logger.info('sending greet to {0}'.format(address))

#                if (address not in self.router.pm) or not self.router.pm[address].is_direct:
#                    d = defer.Deferred()

                def send_greet(timeout_id, i, *x):
                    '''Send a greet packet and re-queues self'''

                    if i > 0:
                        logger.debug('sending greet packet #{0}'.format(i))
                        d = self.send_greet(address, ack=True)
                        d.addCallbacks(main_d.callback, send_greet, None, None, (i-1,), None)
                    else:
                        # address didn't respond, try next address
                        logger.info('(greet) address {0} timed out'.format(address))
                        reactor.callLater(0, try_address, None, j+1)

                send_greet(0, 3)
            else:
                logger.info('no addresses passed to try_register responded.')
                main_d.errback(Exception('Could not establish connection with addresses.'))

        reactor.callLater(0, try_address, None, 0)
        main_d.addCallback(lambda *x: logger.debug('greet success! {0}'.format(x)))
        main_d.addErrback(logger.info)
        return main_d #TODO this funky thing needs testing

    def send_greet(self, address, ack=False):
        #if address not in self:
        return self.router.send(self.GREET, '', address, ack=ack)

    def handle_greet(self, type, packet, address, src_id):
        if src_id == self._self.id:
            logger.info('greeted self')
            return

        logger.debug('handle greet')
        if src_id not in self.sm and src_id not in self.shaking_peers:
            # unknown peer not currently shaking hands, start handshake
            self.send_handshake(src_id, address, 0)
        else:
            # check to see if we found a direct route TODO
            pass

    def handshake_timeout(self, pid):
        if pid not in self.sm:
            logger.warning('handshake with {0} timed out'.format(pid.encode('hex')))
            if pid in self.shaking_peers:
                del self.shaking_peers[pid]
            if pid in self.sm.session_map:
                del self.sm.session_map[pid]

    def send_handshake(self, pid, address, relays=0):
        logger.debug('send handshake')
        if pid not in self.sm and pid not in self.shaking_peers:
            nonce = os.urandom(32) #todo crypto size
            self.shaking_peers[pid] = (nonce, relays)
            self.sm.session_map[pid] = address

            # timeout handshake
            reactor.callLater(3, self.handshake_timeout, pid)

            mac = hmac.new(self.router.network.key, nonce, hashlib.sha256).digest()

            # need ack?
            self.router.send(self.HANDSHAKE, pack('!B', relays)+nonce+mac, pid)



    def handle_handshake(self, type, packet, address, src_id):
        if src_id not in self.peer_list and src_id not in self.shaking_peers:
            r, nonce, mac = packet[0], packet[1:33], packet[33:]
            r = unpack('!B', r)[0]

            # verify nonce
            if hmac.new(self.router.network.key, nonce, hashlib.sha256).digest() != mac:
                logger.critical("hmac verification failed on handshake!")
            else:
                self.send_handshake_ack(nonce, src_id, address, r)

    def send_handshake_ack(self, nonce, pid, address, relays=0):
        logger.debug('sending handshake ack to {0}'.format(pid.encode('hex')))
        mynonce = os.urandom(32)
        self.shaking_peers[pid] = (mynonce, relays)
        self.sm.session_map[pid] = address

        mac = hmac.new(self.router.network.key, nonce+mynonce, hashlib.sha256).digest()
        d = self.router.send(self.HANDSHAKE_ACK, mynonce+mac, pid, ack=True)
        d.addCallback(lambda *x: self.handshake_done(pid, nonce+mynonce, address))
        d.addErrback(lambda *x: self.handshake_fail(pid, x))

    def handle_handshake_ack(self, type, packet, address, src_id):
        logger.debug('got handshake ack from {0}'.format(src_id.encode('hex')))
        if src_id in self.shaking_peers:
            nonce, mac = packet[:32], packet[32:]
            mynonce = self.shaking_peers[src_id][0]
            if hmac.new(self.router.network.key, mynonce+nonce, hashlib.sha256).digest() != mac:
                logger.critical("hmac verification failed on handshake_ack!")
                self.handshake_fail(src_id)
            else:
                self.handshake_done(src_id, mynonce+nonce, address)


    def handshake_done(self, pid, salt, address):
        logger.debug('handshake finished with {0}'.format(pid.encode('hex')))
        if pid in self.shaking_peers:
            session_key = hashlib.sha256(self.router.network.key+salt).digest()
            self.sm.open(pid, session_key)
            #self.session_map[pid] = (session_key, address, pid)
            # init encryption

            # do register, close session if failed
            def do_later():
                d = self.try_register(pid, relays=self.shaking_peers[pid][1])
                d.addErrback(self.close_session, pid)
            reactor.callLater(0, do_later)

    def handshake_fail(self, pid, x):
        print 'fail',x
        if pid in self.shaking_peers:
            logger.critical('handshake failed with {0}'.format(pid.encode('hex')))
            del self.shaking_peers[pid]

    def close_session(self, pid):
        if pid in self.shaking_peers:
            del self.shaking_peers[pid]
        if pid in self.sm:
            self.sm.close(pid)
        if pid in self.pm:
            self.pm.remove_peer(pid)

    def try_register(self, pid, addr=None, relays=0):
        '''Try to register self with a peer by sending a register packet
        with own peer info.  Will continue to send this packet until an
        ack is received or MAX_REG_TRIES packets have been sent.'''

        if pid not in self.sm: # It's an (address,port) pair
            raise TypeError, "Cannot send register to unknown session"
        addr = pid if addr is None else addr

        d = defer.Deferred()
        if (pid not in self.peer_list):
            # TODO set relay
            self._self.relays = relays
            packet = pickle.dumps(self._self, -1)
            self._self.relays = 0

            def send_register(i):
                '''Send a register packet and re-queues self'''

                if i <= self.MAX_REG_TRIES and pid not in self.peer_list:
                    logger.debug('sending REG packet #{0}'.format(i))
                    self.sm.send(self.REGISTER, packet, addr)
                    reactor.callLater(self.REG_TRY_DELAY, send_register, i+1)
                elif i > self.MAX_REG_TRIES:
                    logger.info('(reg) address {0} timed out'.format(pid))
                    d.errback(Exception('address timed out'))
                else: # address in PM
                    logger.debug('(reg) address {0} in PM.'.format(pid))
                    d.callback(self.peer_list[pid])

            send_register(0)
        else:
            logger.debug('address {0} already in peer list'.format(pid))
            reactor.callLater(0, d.callback, self.router.pm[pid])

        d.addErrback(logger.info)
        return d #TODO this funky thing needs testing


#    def try_register(self, addrs):
#        '''Try to register self with a peer by sending a register packet
#        with own peer info.  Will continue to send this packet until an
#        ack is received or MAX_REG_TRIES packets have been sent.'''
#
#        if isinstance(addrs, tuple): # It's an (address,port) pair
#            addrs = [addrs]
#        elif isinstance(addrs, PeerInfo):
#            # if a NAT scrambled the port, re-add it to the list for each IP
#            # list(set()) to eliminate duplicates
#            try:
#                addrs = \
#                    list(set([ (x[0], addrs.port) for x in addrs.direct_addresses
#                                                        if x[1] != addrs.port])) \
#                        + addrs.direct_addresses
#            except AttributeError: # if .port undefined (pre bzr rev 61)
#                addrs = addrs.direct_addresses
#
#        elif not isinstance(addrs, list):
#            logger.error('try_register called with incorrect parameter: {0}'.format(addrs))
#            return
#
#        main_d = defer.Deferred()
#
#        def try_address(err, j):
#            if j < len(addrs):
#                address = addrs[j]
#                logger.info('initiating a register xchange with {0}'.format(address))
#
#                if (address not in self.router.pm):
#                    d = defer.Deferred()
#
#                    def send_register(i):
#                        '''Send a register packet and re-queues self'''
#
#                        if i <= self.MAX_REG_TRIES and address not in self.router.pm:
#                            logger.debug('sending REG packet #{0}'.format(i))
#                            self.router.send(self.REGISTER, self._my_pickle, address)
#                            reactor.callLater(self.REG_TRY_DELAY, send_register, i+1)
#                        elif i > self.MAX_REG_TRIES:
#                            logger.info('(reg) address {0} timed out'.format(address))
#                            d.errback(Exception('address timed out'))
#                        else: # address in PM
#                            logger.debug('(reg) address {0} in PM.'.format(address))
#                            d.callback(self.router.pm[address])
#
##                    reactor.callLater(self.REG_TRY_DELAY, send_register, 0)
#                    # add callbacks in parallel
#                    d.addCallbacks(main_d.callback, try_address, None, None, (j+1,), None)
#                    send_register(0)
#                else:
#                    logger.debug('address {0} already in peer list'.format(address))
#                    main_d.callback(self.router.pm[address])
#
#            else:
#                logger.info('no addresses passed to try_register responded.')
#                main_d.errback(Exception('Could not establish connection with addresses.'))
#
##            return err
#
#        reactor.callLater(0, try_address, None, 0)
#        main_d.addErrback(logger.info)
#        return main_d
#
    def handle_reg(self, type, packet, address, src_id):
        '''Handle incoming reg packet by adding new peer and sending ack.'''

        logger.info('received REG packet, sending ACK')
        #packet = self.sm.decode(src_id, packet)
        pi = pickle.loads(packet)
        if pi.id == self._self.id:
            # we sent a reg to ourself?
            logger.warning('we recieved a reg from ourself...')
        elif pi.id not in self.peer_list:
            logger.info('received a register from a new peer {0}'.format(pi.name))
            pi.address = address
            self.add_peer(pi)
        else:
            pi.address = address
            self.update_peer(self.peer_list[pi.id], pi)

        # TODO set relay
        self._self.relays = pi.relays
        packet = pickle.dumps(self._self, -1)
        self._self.relays = 0
        self.sm.send(self.REGISTER_ACK, packet, src_id)


    def handle_reg_ack(self, type, packet, address, src_id):
        '''Handle reg ack by adding new peer'''

        logger.info('received REG ACK packet')

        #packet = self.sm.decode(src_id, packet)
        pi = pickle.loads(packet)

        if pi.id == self._self.id:
            # yea yea...
            logger.warning('we recieved a reg ack from ourself...')
        elif pi.id not in self.peer_list:
            logger.info('received REG ACK packet from new peer {0}'.format(pi.name))
            pi.address = address
            self.add_peer(pi)
        else:
            pi.address = address
            self.update_peer(self.peer_list[pi.id], pi)


    ###### Container Type Overloads
    def get_by_name(self, name):
        '''Get a peer connection by peer name'''
        if name == self._self.name:
            return self._self
        for p in self.peer_list.values():
            if p.name == name:
                return p
        return None

    def get_by_vip(self, vip):
        '''Get a peer connection by virtual ip'''
        if vip == self._self.vip:
            return self._self
        for p in self.peer_list.values():
            if p.vip == vip:
                return p
        return None

    def get_by_addr(self, addr):
        '''Get a peer connection by mac or vip address'''
        if addr == self._self.addr:
            return self._self
        for p in self.peer_list.values():
            if p.addr == addr:
                return p
        return None

    def get_by_address(self, address):
        '''Get a peer connection by real (ip,port)'''
        if address == self._self.address:
            return self._self
        for p in self.peer_list.values():
            if p.address == address and p.is_direct:
                return p
        return None

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

        elif isinstance(item, str):  # name, addr, or id
            peer = None
            if item == self._self.id:
                peer = self._self
            elif len(item) == 16 and item in self.peer_list:
                peer = self.peer_list[item]
            else:
                if len(item) == 4:
                    peer = self.get_by_vip(item)
                elif len(item) == 6:
                    peer = self.get_by_addr(item)
                if peer is None:
                    peer = self.get_by_name(item)

        elif isinstance(item, tuple):                     # address
            peer = self.get_by_address(item)

        else:
            raise TypeError('Unrecognized key type')

        if peer is None:
            raise KeyError('Address {0} not in peer list.'.format(repr(item)))
        else:
            return peer

    def get(self, item, default=None):
        try:
            item = self[item]
        except KeyError:
            item = default
        return item

    def __contains__(self, item):
        if isinstance(item, PeerInfo):
            return (item.id in self.peer_list or
                        item.id == self._self.id)
        if isinstance(item, tuple):                     # address
            return self.get_by_address(item) is not None
        elif isinstance(item, str):  # name or vip
            return (item == self._self.id or
                    item in self.peer_list or
                    #TODO which to include here
                self.get(item) != None)
