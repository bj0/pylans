# Copyright (C) 2011  Brian Parma (execrable@gmail.com)
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
# TODO: need a pinger or something to determine when sessions are dead
from twisted.internet import reactor, defer
import hashlib, hmac
from struct import pack, unpack
import os
import util
from vpn.crypto import Crypter
from vpn.peers import PeerInfo
import logging

logger = logging.getLogger(__name__)

class SessionManager(object):

    GREET = 14
    HANDSHAKE = 15
    HANDSHAKE_ACK = 16
    KEY_XCHANGE = 30
    KEY_XCHANGE_ACK = 31

    def __init__(self, router):

        self.router = util.get_weakref_proxy(router)
        # sid -> encryption object
        self.session_objs = {}
        # sid -> address
        self.session_map = {}
        # sid -> (nonce, relays) for handshake
        self.shaking = {}

        self.id = self.router.network.id

        router.register_handler(self.GREET, self.handle_greet)
        router.register_handler(self.HANDSHAKE, self.handle_handshake)
        router.register_handler(self.HANDSHAKE_ACK, self.handle_handshake_ack)
        router.register_handler(self.KEY_XCHANGE, self.handle_key_xc)
        router.register_handler(self.KEY_XCHANGE_ACK, self.handle_key_xc_ack)

    def open(self, sid, session_key, relays=0):
        obj = Crypter(session_key, callback=self.init_key_xc, args=(sid,))
        self.session_objs[sid] = obj
        util.emit_async('session-opened', self, sid, relays)

    def close(self, sid):
        if sid in self.session_objs:
            del self.session_objs[sid]
        if sid in self.session_map:
            del self.session_map[sid]
        if sid in self.shaking:
            del self.shaking[sid]

        # addr map uses mac addresses as keys, not sids
        # gen a list incase there are multiple addresses for an sid (there shouldn't be)
        aslist = [k for k in self.router.addr_map if self.router.addr_map[k][-1] == sid]
        for x in aslist:
            logger.debug('removing addr map {0}->{1}'.format(util.decode_mac(x),sid.encode('hex')))
            del self.router.addr_map[x]
        util.emit_async('session-closed', self, sid)

    def encode(self, sid, data):
        if isinstance(sid, PeerInfo):
            sid = sid.id

        if sid not in self:
            #logger.critical('unknown session id: {0}'.format(sid.encode('hex'))
            raise KeyError, "unknown session id: {0}".format(sid.encode('hex'))
        return self.session_objs[sid].encrypt(data)

    def decode(self, sid, data):
        if isinstance(sid, PeerInfo):
            sid = sid.id

        if sid not in self:
            raise KeyError, "unknown session id: {0}".format(sid.encode('hex'))
        return self.session_objs[sid].decrypt(data)



###### ###### ###### Key XChange Stuff ###### ###### ###### 

    def init_key_xc(self, obj, sid):
        logger.info('new key xchange initiated')
        #TODO prevent multiple key xc at the same time?
        mynonce = os.urandom(32)
        mac = hmac.new(self.router.network.key, mynonce, hashlib.sha256).digest()

        self.router.send(self.KEY_XCHANGE, mynonce+mac, sid)

    def handle_key_xc(self, type, packet, address, src_id):
        logger.info('got new key xchange packet')
        nonce, mac = packet[:32], packet[32:]

        # verify nonce
        if hmac.new(self.router.network.key, nonce, hashlib.sha256).digest() != mac:
            logger.critical("hmac verification failed on key xchange!")
        else:
            send_key_xc_ack(nonce, sid)

    def send_key_xc_ack(self, nonce, sid):
        logger.info('sending key xchange ack')
        mynonce = os.urandom(82)
        mac = hmac.new(self.router.network.key, nonce+mynonce, hashlib.sha256).digets()

        d = self.router.send(self.KEY_XCHANGE_ACK, nonce+mynonce+mac, sid, ack=True)
        d.addCallback(lambda *x: self.key_xc_complete(nonce+mynonce, sid))
        d.addErrback(lambda *x: self.key_xc_fail(sid))

    def handle_key_xc_ack(self, type, packet, address, src_id):
        logger.info('got key xchange ack')
        mynonce, nonce, mac = packet[:32], packet[32:64], packet[64:]

        # verify nonce
        if hmac.new(self.router.network.key, nonce, hashlib.sha256).digest() != mac:
            logger.critical('hmac verification failed on key xchange!')
        else:
            self.key_xc_complete(mynonce+nonce, src_id)

    def key_xc_complete(self, salt, sid):
        logger.info('new key xchange complete')
        session_key = hashlib.sha256(self.router.network.key+salt).digest()
        self.open(pid, session_key)

    def key_xc_fail(self, sid):
        logger.critical('key xchange failed!')
        #TODO re-try key xchange, or drop session??



###### ###### ###### Session Initiation/Handshake functions ###### ###### ###### 

    @defer.inlineCallbacks
    def try_greet(self, addrs):
        '''Try and send 'greet' packets to given address.'''
        if isinstance(addrs, tuple):
            # It's an (address,port) pair
            addrs = [addrs]

        elif isinstance(addrs, PeerInfo):
            if addrs.is_direct:
                # don't need to...
                return
                #yield defer.succeed(None)

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
            #return
            raise Exception('try_greet called with incorrect parameter: {0}'.format(addrs))

        for address in addrs:
            logger.info('sending greet to {0}'.format(address))
            for i in range(3):
                logger.debug('sending greet packet #{0}'.format(i))
                try:
                    ret = yield self.send_greet(address, ack=True)
                    return # stop trying if successful TODO: return address?
                except Exception, e:
                    logger.info('(greet) address {0} timed out'.format(address))
                    # just keep trying...

        logger.info('Could not establish connection with addresses.')
        return
        #raise Exception('Could not establish connection with addresses.')


    def send_greet(self, address, ack=False):
        #if address not in self:
        return self.router.send(self.GREET, '', address, ack=ack)

    def handle_greet(self, type, packet, address, src_id):
        if src_id == self.id:
            logger.info('greeted self')
            return #TODO throw exception to prevent acks?

        logger.debug('handle greet')
        if (src_id not in self or self.router.pm[src_id].timeouts > 0) \
         and src_id not in self.shaking:
            # unknown peer not currently shaking hands, start handshake
            self.send_handshake(src_id, address, 0)
        else:
            # check to see if we found a direct route TODO
            if src_id in self.router.pm:
                pi = self.router.pm[src_id]
                if pi.relays > 0:
                    import copy
                    logger.critical('got us some directness')

                    # update peer
                    pn = copy.copy(pi)
                    pn.relays = 0
                    pn.address = address
                    self.router.pm.update_peer(pi, pn)

                    # return the favor
                    self.send_greet(address)

    def handshake_timeout(self, pid):
        if pid not in self:
            logger.warning('handshake with {0} timed out'.format(pid.encode('hex')))
            if pid in self.shaking:
                del self.shaking[pid]
            if pid in self.session_map:
                del self.session_map[pid]

    def send_handshake(self, pid, address, relays=0):
        if (pid not in self or self.router.pm[pid].timeouts > 0) \
         and pid not in self.shaking:
            logger.info('send handshake to {0}'.format(pid.encode('hex')))

            nonce = os.urandom(32) #todo crypto size
            self.shaking[pid] = (nonce, relays)
            self.session_map[pid] = address

            # timeout handshake
            reactor.callLater(3, self.handshake_timeout, pid)

            mac = hmac.new(self.router.network.key, nonce, hashlib.sha256).digest()

            # need ack?
            self.router.send(self.HANDSHAKE, pack('!B', relays)+nonce+mac, pid, clear=True)


    def handle_handshake(self, type, packet, address, src_id):
        logger.critical('got handshake!!!')
        if (src_id not in self or self.router.pm[src_id].timeouts > 0) \
         and src_id not in self.shaking:
            r, nonce, mac = packet[0], packet[1:33], packet[33:]
            r = unpack('!B', r)[0]

            # verify nonce
            if hmac.new(self.router.network.key, nonce, hashlib.sha256).digest() != mac:
                logger.critical("hmac verification failed on handshake!")
            else:
                self.send_handshake_ack(nonce, src_id, address, r)

    def send_handshake_ack(self, nonce, pid, address, relays=0):
        logger.info('sending handshake ack to {0}'.format(pid.encode('hex')))
        mynonce = os.urandom(32)
        self.shaking[pid] = (mynonce, relays)
        self.session_map[pid] = address
        
        mac = hmac.new(self.router.network.key, nonce+mynonce, hashlib.sha256).digest()
        d = self.router.send(self.HANDSHAKE_ACK, mynonce+mac, pid, ack=True, clear=True)
        d.addCallback(lambda *x: self.handshake_done(pid, nonce+mynonce, address))
        d.addErrback(lambda *x: self.handshake_fail(pid, x))

    def handle_handshake_ack(self, type, packet, address, src_id):
        logger.info('got handshake ack from {0}'.format(src_id.encode('hex')))
        if src_id in self.shaking:
            nonce, mac = packet[:32], packet[32:]
            mynonce = self.shaking[src_id][0]
            if hmac.new(self.router.network.key, mynonce+nonce, hashlib.sha256).digest() != mac:
                logger.critical("hmac verification failed on handshake_ack!")
                self.handshake_fail(src_id)
                raise Exception('hmac verification failed on handshake_ack!') # prevent ack
            else:
                self.handshake_done(src_id, mynonce+nonce, address)

    def handshake_done(self, pid, salt, address):
        logger.info('handshake finished with {0}'.format(pid.encode('hex')))
        if pid in self.shaking:
            # todo - session key size?
            session_key = hashlib.md5(self.router.network.key+salt).digest()
            # init encryption
            self.open(pid, session_key, relays=self.shaking[pid][1])
            del self.shaking[pid]

            # emit event, close session if failed
            # but do it after we send the ack
            #def do_later():
                #pass
            #    d = self.try_register(pid, relays=self.shaking[pid][1])
            #    d.addErrback(self.close_session, pid)
            #reactor.callLater(0, do_later)

    def handshake_fail(self, pid, x):
        logger.critical('handshake failed with {0}'.format(pid.encode('hex')))
        if pid in self.shaking:
            del self.shaking[pid]
        if pid in self.session_map:
            del self.session_map[pid]

    def close_session(self, pid):
        self.close(pid)



    ### Container Functions
    def get(self, item, default=None):
        try:
            return self[item]
        except KeyError:
            return default

    def __contains__(self, item):
        return item in self.session_objs

    def __getitem__(self, item):
        return self.session_objs[item]

    def __len__(self):
        len(self.session_objs)
