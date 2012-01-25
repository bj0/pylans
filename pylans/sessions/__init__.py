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
# TODO: reconnect with relayed peers?
# TODO: periodic px?
from twisted.internet import reactor, defer
import hashlib, hmac
from struct import pack, unpack
import os
import logging
from .. import util
from ..crypto import Crypter, jpake
from ..peers import PeerInfo
from .. import protocol
from ..packets import PacketType

logger = logging.getLogger(__name__)

PacketType.add(
GREET       = 14,
HANDSHAKE1  = 15,
HANDSHAKE2  = 16,
HANDSHAKE3  = 17,
CLOSE       = 13)

class SessionManager(object):


    HANDSHAKE_TIMEOUT = 3 #seconds
    def __init__(self, router, proto=None):

        if proto is None:
            proto = protocol.UDPPeerProtocol(router.recv)
    
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

        router.register_handler(PacketType.GREET, self.handle_greet)
        router.register_handler(PacketType.HANDSHAKE1, self.handle_handshake1)
        router.register_handler(PacketType.HANDSHAKE2, self.handle_handshake2)
        router.register_handler(PacketType.HANDSHAKE3, self.handle_handshake3)
        router.register_handler(PacketType.CLOSE, self.handle_close)

    
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
            address = self.shaking[sid][2]
            
            # session reset
            def do_reset():
                logger.warning('doing session reset for {0}'.format(sid.encode('hex')))
                self.send_handshake(sid, address, relays)
                
            # create encryption option
            obj = Crypter(session_key, callback=do_reset)
            self.session_objs[sid] = obj
            
            # update sid -> address map
            self.update_map(sid, address)
            del self.shaking[sid]
            
            util.emit_async('session-opened', self, sid, relays)
        else:
            raise Exception, "TODO: key-exchange"

    def handle_close(self, pt, data, addr, sid):
        logger.info('got a close packet from {0}'.format(sid.encode('hex')))
        self.close(sid)

    def close(self, sid):
        logger.debug('closing session {0}'.format(sid.encode('hex')))
        # remove encryption object
        if sid in self.session_objs:
            del self.session_objs[sid]
        # remove address map
        if sid in self.session_map:
            # send a close packet for the other side
            self.router.send(PacketType.CLOSE, '', sid)
            del self.session_map[sid]
        # remove incomplete session
        if sid in self.shaking:
            del self.shaking[sid]
         
        # clear unreachable routes
        # addr map uses mac addresses as keys, not sids
        # gen a list incase there are multiple addresses for an sid
        aslist = [k for k in self.router.addr_map 
                            if self.router.addr_map[k][-1] == sid]
        for x in aslist:
            logger.debug('removing addr map {0}->{1}'.format(
                                util.decode_mac(x),sid.encode('hex')))
            del self.router.addr_map[x]
        util.emit_async('session-closed', self, sid)

    def encode(self, sid, data):
        if isinstance(sid, PeerInfo):
            sid = sid.id

        if sid not in self.session_objs:
            logger.error('unknown session id: {0}'.format(sid.encode('hex')))
            raise KeyError, "unknown session id: {0}".format(sid.encode('hex'))
        return self.session_objs[sid].encrypt(data)

    def decode(self, sid, data):
        if isinstance(sid, PeerInfo):
            sid = sid.id

        if sid not in self.session_objs:
            logger.error('unknown session id: {0}'.format(sid.encode('hex')))
            raise KeyError, "unknown session id: {0}".format(sid.encode('hex'))
        return self.session_objs[sid].decrypt(data)




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
        return self.router.send(PacketType.GREET, '', address, ack=ack)

    def handle_greet(self, type, packet, address, src_id):
        if src_id == self.id:
            logger.info('greeted self')
#           if we block ack, won't it just keep sending?
#            raise Exception, 'greeted self'
            return

        logger.debug('handle greet')
        if (src_id not in self.session_map or self.router.pm[src_id].timeouts > 0) \
         and src_id not in self.shaking:
            # unknown peer not currently shaking hands, start handshake
            self.send_handshake(src_id, address, 0)
        else:
            # check to see if we found a direct route
            if src_id in self.router.pm:
                pi = self.router.pm[src_id]
                if pi.relays > 0:
                    import copy
                    logger.info('direct connection established with {0}'
                                .format(src_id.encode('hex')))

                    # update peer
                    pn = copy.copy(pi)
                    pn.relays = 0
                    pn.address = address
                    self.router.pm.update_peer(pi, pn)

                    # return the favor
                    self.send_greet(address)

    def send_handshake(self, sid, address, relays=0):
        # todo make retry for fails
        if sid not in self.shaking:
            logger.info('sending handshake to {0}'.format(sid.encode('hex')))

            j = jpake.JPAKE(self.router.network.key)
            send1 = j.pack_one(j.one())
            j._one = True
            j._two = False
            self.shaking[sid] = [j, relays, address]

            # timeout handshake
            reactor.callLater(self.HANDSHAKE_TIMEOUT, 
                              self.handshake_timeout, sid)
 
            # don't need ack, should get handshake-ack or timeout
            return self.router.send(PacketType.HANDSHAKE1, 
                                    pack('!B', relays)+send1, 
                                    sid, clear=True)

        else:
            logger.info('send_handshake called on {0} while already shaking'
                        .format(sid.encode('hex')))

    def handle_handshake1(self, type, packet, address, src_id):

        logger.info('got handshake1 from {0}'.format(src_id.encode('hex')))
        r, recv1 = packet[0], packet[1:]
        r = unpack('!B', r)[0]

        if src_id in self.shaking:
            j, relays, addr = self.shaking[src_id]
            if relays < r:
                # incoming hs1 came over more hops
                r = relays
                address = addr
            elif addr != address:
                # incoming hs1 came over less (or equal) hops
                self.shaking[src_id][2] = address
            
        else:
            self.send_handshake(src_id, address, r)
            j = self.shaking[src_id][0]

        send2 = j.pack_two(j.two(j.unpack_one(recv1)))
        j._two = True
        logger.info('sending handshake2 to {0}'.format(src_id.encode('hex')))
        return self.router.send(PacketType.HANDSHAKE2, send2, src_id, clear=True)
        

    @defer.inlineCallbacks
    def handle_handshake2(self, type, packet, address, src_id):
        if src_id in self.shaking:
            logger.info('got handshake2 from {0}'.format(src_id.encode('hex')))
            j = self.shaking[src_id][0]
            
            # make sure we got hs1 before hs2
            if not j._two:
                logger.warning('handshake2 arrived but never got handshake1 '
                                +'from {0}'.format(src_id.encode('hex')))
                self.handshake_fail(src_id)
                return
                
            recv2 = j.unpack_two(packet)
            session_key = j.three(recv2)
            hsh = hashlib.sha256(session_key).digest()
                        
            for i in range(3): # 3 retrys
                logger.info('sending handshake3 to {0}'.format(src_id.encode('hex')))
                try:
                    yield self.router.send(PacketType.HANDSHAKE3, hsh, src_id, clear=True, ack=True)
                    break
                except Exception, e:
                    logger.warning('handshake3 to {0} timed out'.format(src_id.encode('hex')))
                    # let it retry...
            else:
                # all hs3 packets timed out
                self.handshake_fail(src_id)
                return

            if len(self.shaking[src_id]) == 4: # if we already got handshake3 packet
                packet = self.shaking[src_id][3]
                self.shaking[src_id][3] = session_key
                self.handle_handshake3(None, packet, None, src_id)
            else:
                self.shaking[src_id] += [session_key,]
        else:
            logger.warning('got handshake2 from {0}, but not currently shaking'.format(src_id.encode('hex')))
        
    def handle_handshake3(self, type, packet, address, src_id):
        if src_id in self.shaking:
            if len(self.shaking[src_id]) < 4: # we haven't got handshake2 yet
                logger.info('got handshake3 before handshake2 from {0}'.format(src_id.encode('hex')))
#                handshake_fail(src_id)
                self.shaking[src_id] += [packet,]
                return
                
            logger.info('got handshake3 from {0}'.format(src_id.encode('hex')))
            session_key = self.shaking[src_id][3]
            
            if packet == hashlib.sha256(session_key).digest():
                self.handshake_done(src_id)
            else:
                logger.error('handshake with {0} verification failed'.format(src_id.encode('hex')))
                self.handshake_fail(src_id)
            
        else:
            logger.warning('got handshake3 from {0}, but not currently shaking'.format(src_id.encode('hex')))
        

    def handshake_done(self, sid):
        logger.info('handshake finished with {0}'.format(sid.encode('hex')))
        if sid in self.shaking:
            # todo - session key size?
            session_key = self.shaking[sid][3]
#            session_key = hashlib.md5(session_key).digest()
            r = self.shaking[sid][1]
            
            # init encryption
            self.open(sid, session_key, relays=r)


    def handshake_timeout(self, sid):
        if sid in self.shaking and sid not in self.session_map:
            logger.warning('handshake with {0} timed out'.format(sid.encode('hex')))
            self.close(sid)

    @defer.inlineCallbacks
    def handshake_fail(self, sid, *x):
        logger.error('handshake failed with {0}'.format(sid.encode('hex')))
        # add a delay to prevent hammering
        yield util.sleep(.2) 
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
        
        
try:
    from ssl import SSLSessionManager
except ImportError:
    logger.warning('could not import SSL, ssl sessions unavailable')

