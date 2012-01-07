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
# TODO: what is the difference between a session and a peer?
from twisted.internet import ssl, reactor, defer
import hashlib, hmac
from struct import pack, unpack
import os
import util
from crypto import Crypter
from peers import PeerInfo
import protocol
import logging

logger = logging.getLogger(__name__)

class SessionManager(object):

    GREET = 14
    HANDSHAKE = 15
    HANDSHAKE_ACK = 16
    KEY_XCHANGE = 30
    KEY_XCHANGE_ACK = 31

    HANDSHAKE_TIMEOUT = 3 #seconds
    def __init__(self, router, proto=None):

        if proto is None:
            proto = protocol.UDPPeerProtocol(router.recv)
    
#        proto.router = util.get_weakref_proxy(router)
        self.proto = proto
        self.port = None

        self.router = util.get_weakref_proxy(router)
        # sid -> encryption object
        self.session_objs = {}
        # sid -> address
        self.session_map = {}
        # sid -> (nonce, relays, address) for handshake
        self.shaking = {}

        self.id = self.router.network.id

        router.register_handler(self.GREET, self.handle_greet)
        router.register_handler(self.HANDSHAKE, self.handle_handshake)
        router.register_handler(self.HANDSHAKE_ACK, self.handle_handshake_ack)
        router.register_handler(self.KEY_XCHANGE, self.handle_key_xc)
        router.register_handler(self.KEY_XCHANGE_ACK, self.handle_key_xc_ack)

    
###### ###### ###### Protocol Stuff ###### ###### ###### 

    def update_map(self, sid, address):
        self.session_map[sid] = address

    def send(self, data, sid, address):
        self.proto.send(data, address)

    def start(self, port):
        # start listening on port
        self.port = reactor.listenUDP(port, self.proto)
        return self.port
        
    def stop(self):
        if self.port is not None:
            self.port.stopListening()
            self.port = None

    def open(self, sid, session_key, relays=0):
        if sid in self.shaking:
            # create encryption option
            obj = Crypter(session_key, callback=self.init_key_xc, args=(sid,))
            self.session_objs[sid] = obj
            
            # update sid -> address map
            self.update_map(sid, self.shaking[sid][2])
            del self.shaking[sid]
            
            util.emit_async('session-opened', self, sid, relays)
        else:
            raise Exception, "TODO: key-exchange"

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
        self.open(sid, session_key)

    def key_xc_fail(self, sid):
        logger.error('key xchange failed!')
        #TODO re-try key xchange, or drop session??



###### ###### ###### Session Initiation/Handshake functions ###### ###### ###### 

    def connect(self, addrs):
        self.try_greet(self, addrs)

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
        return # same as defer.returnValue(None)
        #raise Exception('Could not establish connection with addresses.')

    def connect(self, address, ack=False):
        self.send_greet(address, ack)
        
    def send_greet(self, address, ack=False):
        #if address not in self:
        return self.router.send(self.GREET, '', address, ack=ack)

    def handle_greet(self, type, packet, address, src_id):
        if src_id == self.id:
            logger.info('greeted self')
            return #TODO throw exception to prevent acks?

        logger.debug('handle greet')
        if (src_id not in self.session_map or self.router.pm[src_id].timeouts > 0) \
         and src_id not in self.shaking:
            # unknown peer not currently shaking hands, start handshake
            self.send_handshake(src_id, address, 0)
        else:
            # check to see if we found a direct route TODO
            if src_id in self.router.pm:
                pi = self.router.pm[src_id]
                if pi.relays > 0:
                    import copy
                    logger.info('direct connection established with {0}'.format(src_id.encode('hex')))

                    # update peer
                    pn = copy.copy(pi)
                    pn.relays = 0
                    pn.address = address
                    self.router.pm.update_peer(pi, pn)

                    # return the favor
                    self.send_greet(address)

    def send_handshake(self, sid, address, relays=0):
        if (sid not in self.session_map or self.router.pm[sid].timeouts > 0) \
         and sid not in self.shaking:
            logger.info('send handshake to {0}'.format(sid.encode('hex')))

            nonce = os.urandom(32) #todo crypto size
            self.shaking[sid] = (nonce, relays, address)

            # timeout handshake
            reactor.callLater(self.HANDSHAKE_TIMEOUT, self.handshake_timeout, sid)
            mac = hmac.new(self.router.network.key, nonce, hashlib.sha256).digest()
 
            # don't need ack, should get handshake-ack or timeout
            self.router.send(self.HANDSHAKE, pack('!B', relays)+nonce+mac, sid, clear=True)


    def handle_handshake(self, type, packet, address, src_id):
        logger.info('got handshake packet from {0}'.format(src_id.encode('hex')))
        if (src_id not in self.session_map or self.router.pm[src_id].timeouts > 0) \
         and src_id not in self.shaking:
            r, nonce, mac = packet[0], packet[1:33], packet[33:]
            r = unpack('!B', r)[0]

            # verify nonce
            if hmac.new(self.router.network.key, nonce, hashlib.sha256).digest() != mac:
                logger.critical("hmac verification failed on handshake!")
            else:
                self.send_handshake_ack(nonce, src_id, address, r)

    def send_handshake_ack(self, nonce, sid, address, relays=0):
        logger.info('sending handshake ack to {0}'.format(sid.encode('hex')))
        mynonce = os.urandom(32)
        self.shaking[sid] = (mynonce, relays, address)
#        self.session_map[sid] = address
#        self.update_map(sid, address)
        
        mac = hmac.new(self.router.network.key, nonce+mynonce, hashlib.sha256).digest()
        d = self.router.send(self.HANDSHAKE_ACK, mynonce+mac, sid, ack=True, clear=True)
        d.addCallback(lambda *x: self.handshake_done(sid, nonce+mynonce, address))
        d.addErrback(lambda *x: self.handshake_fail(sid, x))

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

    def handshake_done(self, sid, salt, address):
        logger.info('handshake finished with {0}'.format(sid.encode('hex')))
        if sid in self.shaking:
            # todo - session key size?
            session_key = hashlib.md5(self.router.network.key+salt).digest()
            # init encryption
            self.open(sid, session_key, relays=self.shaking[sid][1])


    def handshake_timeout(self, sid):
        if sid not in self.session_map:
            logger.warning('handshake with {0} timed out'.format(sid.encode('hex')))
            self.close(sid)

    def handshake_fail(self, sid, x):
        logger.critical('handshake failed with {0}'.format(sid.encode('hex')))
        self.close(sid)

    def close_session(self, sid):
        self.close(sid)



    ### Container Functions
#    def get(self, item, default=None):
#        try:
#            return self[item]
#        except KeyError:
#            return default

#    def __contains__(self, item):

#    def __getitem__(self, item):

#        else:
#            raise KeyError, "sid not found"

#    def __len__(self):

        
    def __eq__(self, other):
        import weakref
        if isinstance(other, weakref.ProxyTypes):
            other = other._ref()
        return self is other
        
    def _ref(self):
        return self
        
        
        
        
class SSLSessionManager(SessionManager, protocol.SSLPeerFactory):

    def __init__(self, router):
        self.connecting = {}
        SessionManager.__init__(self, router, proto=self)
        
        
###### ###### ###### Protocol Factory Stuff ###### ###### ###### 

    def buildProtocol(self, addr):
        # server and client
        addr = (addr.host, addr.port)   # match dict key
        if addr not in self.connecting:
            d = defer.Deferred()
            self.connecting[addr] = (None, d)
        else:
            d = self.connecting[addr][1]
            
        p = self.protocol(d, self.router.recv)
        self.connecting[addr] += (p,)
        d.addCallback(self._connect_success, addr)
        d.addErrback(self._connect_fail, addr)
        return p
#
    def clientConnectLost(self, connector, reason):
        # client only
        address = connector.getDestination()
        address = (address.host,address.port)
        if address in self.connecting:
            ctr, d = self.connecting[address]
            logger.debug('connection lost: {0}, {1}, {2}, {3}'.format(
                ctr, connector, address, reason))
            del self.connecting[address]
            d.errback()
        
    def clientConnectionFailed(self, connector, reason):
        self.clientConnectionLost(connector, reason)
        

###### ###### ###### Connection Stuff ###### ###### ###### 

    def update_map(self, sid, addr):
        if isinstance(addr, protocol.SSLPeerProtocol):
            self.session_map[sid] = addr
        else:
            raise ValueError, "session map stores ssl connections, not {0}".format(addr)

    def _connect_fail(self, proto, addr):
        # called for both server and client
        if addr in self.connecting:
            del self.connecting[addr]
            
        logger.info('connection failed: {0}, {1}'.format(addr, proto))

        # get sids using this protocol
        sids = [ k for k in self.session_map.keys() if self.session_map[k] == proto ]

        # close them down
        for sid in sids:
            self.close(sid)
        
        
    def _connect_success(self, proto, addr):
        # called for both server and client
#        if addr in self.connecting:
#            del self.connecting[addr]

        logger.info('connection success: {0}, {1}'.format(addr, proto))
        #TODO connected but not shaking state?

    def connect(self, address):
        #TODO check if already connected
        if address not in self.connecting:
            logger.debug('trying to connect to {0}'.format(address))
            d = defer.Deferred()
            # how to deferr the result of this, or save this connection in handshaking?
            self.connecting[address] = \
                 (reactor.connectSSL(address[0],address[1], self,
                  ssl.ClientContextFactory()), d)
#                (reactor.connectSSL(address[0],address[1], self),d)
            # glib timeout? TODO
        else:
            logger.debug('already connected to {0}'.format(address))
            d = self.connecting[address][1]
            
        return d


#    def try_greet(self, address):
#        logger.critical('try_greet not implimented')
        
    def send_greet(self, address, ack=False):
        d = self.connect(address)
        d.addCallback(lambda *x: self.router.send(self.GREET, '', address, ack=ack))
#        d.addErrback(self._connect_fail
        return d

    def open(self, sid, session_key, relays=0):
        if sid in self.shaking:
            addr = self.shaking[sid][2]
            # shouldn't be in shaking if not in connecting
            self.session_map[sid] = self.connecting[addr][2]
            del self.shaking[sid]
            del self.connecting[addr]
            util.emit_async('session-opened', self, sid, relays)

    def start(self, port):
        self.port = reactor.listenSSL(port, self,
                ssl.DefaultOpenSSLContextFactory('key.pem','cert.pem'))
        return self.port
        
    def stop(self):
        if self.port is not None:
            self.port.stopListening()
            self.port = None
        
    def send(self, data, sid, address):
        if sid in self.session_map:
            self.session_map[sid].send(data)
        elif address in self.connecting: #TODO handle greets/handshakes
            #TODO check for valid packets
            self.connecting[address][2].send(data)
        else:
            logger.error("cannot send to sid not in session map")
            raise KeyError, "cannot send to sid not in session map"
            
    def encode(self, sid, data):
        if sid in self.session_map:
            return data
        else:
            logger.error("encode: sid not in session map")
            raise KeyError, "encode: sid not in session map"
        
    def decode(self, sid, data):
        if sid in self.session_map:
            return data
        else:
            logger.error("decode: sid not in session map")
            raise KeyError, "decode: sid not in session map"

    def _get_proto_by_addr(self, addr):
        d = dict(((x.getPeer().host,x.getPeer().port),x) for x in self.session_map.values())
        #TODO tuple or ipv4addr?
        return d.get(addr, None)
