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
# TODO merge with session manager? inherit?
# TODO routing check, make sure displayed relay is actual relay

import cPickle as pickle
import logging
from twisted.internet import reactor, defer
import os
from struct import pack, unpack
import util
from util import event
import settings

import hmac, hashlib

logger = logging.getLogger(__name__)

class PeerInfo(object):
    '''Represents a peer connection'''
    def __init__(self, peer=None):
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
            
    def __str__(self):
        return ('PeerInfo Object(name={0},'+ \
                'addr={1},'+ \
                'address={2})').format(
                self.name,
                util.decode_mac(self.addr),
                self.address)
                

class PeerManager(object):
    '''Manages peer connections'''
    MAX_REG_TRIES = 5
    MAX_PX_TRIES = 5
    REG_TRY_DELAY = 2
    PX_TRY_DELAY = 2

    # packet types
    PEER_XCHANGE = 17
    PEER_XCHANGE_ACK = 18
    PEER_ANNOUNCE = 19
    REGISTER = 20
    REGISTER_ACK = 21

    def __init__(self, router):
        # list of peers
        self.peer_list = {}
        # addr to (address,port)
#        self.addr_map = {}
        # id's shaking hands -> nonce
#        self.shaking_peers = {}

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

        self.router = util.get_weakref_proxy(router)
        self.sm = util.get_weakref_proxy(router.sm)
        self.addr_map = self.router.addr_map

        # packet handlers
        router.register_handler(self.PEER_XCHANGE, self.handle_px)
        router.register_handler(self.PEER_XCHANGE_ACK, self.handle_px_ack)
        router.register_handler(self.REGISTER, self.handle_reg)
        router.register_handler(self.REGISTER_ACK, self.handle_reg_ack)
        router.register_handler(self.PEER_ANNOUNCE, self.handle_announce)

        def do_session_opened(obj, sid, relays):
            if self.sm == obj:
                d = self.try_register(sid, relays=relays)
                # close session if we can't register peer presence
                d.addErrback(lambda *x: self.sm.close(sid))
        
        def do_session_closed(obj, sid):
            if self.sm == obj:
                self.remove_peer(self.get(sid))
            
        event.register_handler('session-opened', None, do_session_opened)
        event.register_handler('session-closed', None, do_session_closed)


    #def clear(self):
    #    self.peer_list = {}
    #    self.peer_map = {}
    #    self.addr_map = {}
    #    self.shaking_peers = {}

    def _update_pickle(self):
        self._my_pickle = pickle.dumps(self._self,-1)

        # should announce my change to my peerz
        self.send_announce(self._self)

    def add_peer(self, peer):
        '''Add a peer connection'''
        if peer.id not in self.peer_list:
            if peer.relays > 0:
                peer.is_direct = False
                peer.relay_id = self[peer.address].id
                #try to DC
                reactor.callLater(1, self.sm.try_greet, peer.direct_addresses)
            else:
                peer.is_direct = True
                peer.relay_id = None
                if peer.address not in peer.direct_addresses:
                    peer.direct_addresses.append(peer.address)

            self.peer_list[peer.id] = peer
            if peer.addr not in self.addr_map:
                self.addr_map[peer.addr] = (peer.address, peer.id)
            elif peer.id != self.addr_map[peer.addr][1]:
                # what if its here and has a diff id/addr? TODO
                logger.critical('mac address collision between {0} and {1}'.format(
                            self.addr_map[peer.addr][1].encode('hex'),
                            peer.id.encode('hex') ))
                self.addr_map[peer.addr] = (peer.address, peer.id)
            elif peer.address != self.addr_map[peer.addr][0]:
                # what to do if the addresses are diff?
                logger.critical('multiple addresses for mac:{0}'.format(peer.addr_str))
                self.addr_map[peer.addr] = (peer.address, peer.id)

            # fire event
            event.emit('peer-added', self, peer)
            self.send_announce(peer)
            self.try_px(peer)

    def remove_peer(self, peer):
        '''Remove a peer connection'''
        if peer is not None and peer.id in self.peer_list:
            del self.peer_list[peer.id]

            # fire event
            event.emit('peer-removed', self, peer)

    def _timeout(self, peer):
        logger.warning('peer {0} on network {1} timed out'.format(peer.name, self.router.network.name))
        self.sm.close(peer.id) #TODO make this better
#        self.remove_peer(peer)


    def update_peer(self, opi, npi):
        changed = False
        if (opi.relays >= npi.relays and opi.address != npi.address):
            # point addr_map at better relay
            self.addr_map[opi.addr] = (npi.address, npi.id)
            #self.sm.session_map[npi.id] = npi.address
            self.sm.update_map(npi.id, npi.address)

            opi.address = npi.address
            opi.relays = npi.relays
            opi.is_direct = (opi.relays == 0)
            if opi.is_direct > 0:
                opi.relay_id = npi.relay_id
            
            changed = True
            logger.info('peer {0} relay changed.'.format(opi.id.encode('hex')))

        if opi.addr != npi.addr:
            # check for collision? TODO
            if opi.addr in self.addr_map:
                self.addr_map[npi.addr] = self.addr_map[opi.addr]
                del self.addr_map[opi.addr]
            opi.addr = npi.addr #todo check if this is None?
            changed = True
            logger.info('peer {0} addr changed.'.format(opi.id.encode('hex')))

        if opi.vip != npi.vip:
            # check for collision TODO
            opi.vip = npi.vip
            changed = True
            logger.info('peer {0} vip changed.'.format(opi.id.encode('hex')))

        if opi.name != npi.name:
            opi.name = npi.name
            changed = True
            logger.info('peer {0} name changed.'.format(opi.id.encode('hex')))

        if set(opi.direct_addresses) != set(npi.direct_addresses):
            # combine direct_addresses (w/out dupes)
            opi.direct_addresses = list(set(opi.direct_addresses).union(set(npi.direct_addresses)))
            changed = True
            logger.info('peer {0} good addresses changed. ({1})'.format(opi.id.encode('hex'), opi.direct_addresses))
            # try to DC
            reactor.callLater(1, self.sm.try_greet, opi.direct_addresses)

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
            self.router.send(self.PEER_ANNOUNCE, peerkle, address)
            logger.info('sending announce about {0} to {1}'.format(peer.id.encode('hex'), address))
        else:
            for p in self.peer_list.values():
                if p.id != peer.id:
                    self.router.send(self.PEER_ANNOUNCE, peerkle, p)
                    logger.info('sending announce about {0} to {1}'.format(peer.id.encode('hex'), p.id.encode('hex')))


    def handle_announce(self, type, packet, address, src_id):
        logger.info('received an announce packet from {0}'.format(address))
        #packet = self.sm.decode(src_id, packet)
        pi = pickle.loads(packet)
        pi.address = address
        pi.relay_id = src_id
        if pi.id != self._self.id:
            if pi.id not in self.sm.session_map:
                # init (relayed) handshake
                self.sm.send_handshake(pi.id, address, pi.relays)
            elif pi.id not in self.peer_list:
                self.add_peer(pi)
                logger.info('announce from unknown peer {0}, adding and announcing self'.format(pi.name))
            else:
                self.update_peer(self.peer_list[pi.id], pi)

    ###### Peer XChange Functions

    def try_px(self, peer):
        '''Initiate a peer exchange by sending a px packet.  The packet will be
        resent until an ack packet is recieved or MAX_PX_TRIES packets have been sent.
        This px packet includes the pickled peer list.'''

        logger.info('initiating a peer exchange with {0}'.format(peer.name))

        def send_px(i):
            if i <= self.MAX_PX_TRIES and peer.id not in self.peer_map:
                self.router.send(self.PEER_XCHANGE, pickle.dumps(self.peer_list,-1), peer)
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
        self.router.send(self.PEER_XCHANGE_ACK, pickle.dumps(self.peer_list,-1), src_id)
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
                peer.relay_address = from_peer.id

                if peer.id in self.peer_list:
                    self.update_peer(self.peer_list[peer.id],peer)
                elif peer.id not in self.sm.session_map:
                    self.sm.send_handshake(peer.id, peer.address, peer.relays)
                elif peer.id not in self.peer_list:
                    self.add_peer(peer)

            # generate map?



    ###### Peer Register Functions

    @defer.inlineCallbacks
    def try_register(self, pid, addr=None, relays=0):
        '''Try to register self with a peer by sending a register packet
        with own peer info.  Will continue to send this packet until an
        ack is received or MAX_REG_TRIES packets have been sent.'''
        
        def sleep(secs):
            '''Async sleep call'''
            d = defer.Deferred()
            reactor.callLater(secs, d.callback, None)
            return d

        if pid not in self.sm.session_map: # It's an (address,port) pair
            logger.error("Cannot send register to unknown session {0}".format(pid.encode('hex')))
            raise TypeError("Cannot send register to unknown session {0}".format(pid.encode('hex')))
        addr = pid #if addr is None else addr

        if (pid not in self.peer_list):
            # TODO set relay
            self._self.relays = relays
            packet = pickle.dumps(self._self, -1)
            self._self.relays = 0
            
            for i in range(self.MAX_REG_TRIES):
                if pid in self.peer_list:
                    defer.returnValue(self.peer_list[pid])
                else:
                    logger.debug('sending REG packet #{0}'.format(i))
                    self.router.send(self.REGISTER, packet, addr)
                    yield sleep(self.REG_TRY_DELAY)

            logger.info('(reg) address {0} timed out'.format(pid))
            raise Exception('(reg) address {0} timed out'.format(pid))
        else:
            logger.debug('address {0} already in peer list'.format(pid))
            defer.returnValue(self.peer_list[pid])

    def try_old_peers(self):
        '''Try to connect to addresses that were peers in previous sessions.'''

        logger.info('trying to connect to previously known peers')

        for pid in self.router.network.known_addresses:
            if pid not in self:
                addrs = self.router.network.known_addresses[pid]
                self.sm.try_greet(addrs)

        # re-schedule
        interval = settings.get_option(self.router.network.name + '/try_old_peers_interval', 60*5)
        if interval > 0:
            reactor.callLater(interval, util.get_weakref_proxy(self.try_old_peers))
#
    def handle_reg(self, type, packet, address, src_id):
        '''Handle incoming reg packet by adding new peer and sending ack.'''

        logger.info('received REG packet, sending ACK')

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
            pi.relay_id = src_id
            self.update_peer(self.peer_list[pi.id], pi)

        # TODO set relay
        self._self.relays = pi.relays
        packet = pickle.dumps(self._self, -1)
        self._self.relays = 0
        self.router.send(self.REGISTER_ACK, packet, src_id)


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
            pi.relay_id = src_id
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
