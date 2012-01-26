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
from twisted.internet import reactor, defer
import logging
import struct

from ..crypto import Crypter
from ..packets import PacketType
from ..peers import PeerInfo
from .. import util
from .. import protocol
from . import SessionManager


logger = logging.getLogger(__name__)

        
class TCPSessionManager(SessionManager, protocol.TCPPeerFactory):

    def __init__(self, router):
        self.connecting = {}
        SessionManager.__init__(self, router, proto=self)
        
        
###### ###### ###### Protocol Factory Stuff ###### ###### ###### 

    def buildProtocol(self, addr):
        # server and client
        addr = (addr.host, addr.port)   # match dict key
        if addr not in self.connecting:
            # server
            d = defer.Deferred()
            self.connecting[addr] = (None, d)
        else:
            # client
            d = self.connecting[addr][1]
            
        p = self.protocol(d, self.router.recv, self)
        self.connecting[addr] += (p,)
        d.addCallback(self._connect_success, addr)
        d.addErrback(self._connect_fail, addr)
        return p
#
    def clientConnectionLost(self, connector, reason):
        # client only
        print 'lost'
        
    def clientConnectionFailed(self, connector, reason):
        print 'failed'
        address = connector.getDestination()
        address = (address.host,address.port)
        if address in self.connecting:
            ctr, d = self.connecting[address][0:2]
            logger.debug('connection failed: {0}, {1}, {2}, {3}'.format(
                ctr, connector, address, reason))
            del self.connecting[address]
            d.errback(reason)
#        self.clientConnectionLost(connector, reason)
        
    def _connect_fail(self, proto, addr):
        # called for both server and client (from proto)
        if addr in self.connecting:
            del self.connecting[addr]
            
        logger.info('connection closing: {0}, {1}'.format(addr, proto))

        # get sids using this protocol
        sids = [ k for k in self.session_map.keys() if self.session_map[k] == proto ]

        # close them down
        for sid in sids:
            self.close(sid)
        
        
    def _connect_success(self, proto, addr):
        # called for both server and client (from proto)

        logger.info('connection success: {0}, {1}'.format(addr, proto))
        #TODO connected but not shaking state?


###### ###### ###### Connection Stuff ###### ###### ###### 

    def update_map(self, sid, addr):
        if isinstance(addr, protocol.TCPPeerProtocol):
            self.session_map[sid] = addr
        else:
            raise ValueError, "session map stores tcp connections, not {0}".format(addr)

    def connect(self, address):
        # check if already connected
        if address not in self.connecting:
            logger.debug('trying to connect to {0}'.format(address))
            d = defer.Deferred()
            # how to deferr the result of this, or save this connection in handshaking?
            self.connecting[address] = \
                 (reactor.connectTCP(address[0],address[1], self), d)

            # glib timeout? TODO
            reactor.callLater(5, self.timeout, address)
        else:
            logger.warning('already connected to {0}'.format(address))
            d = self.connecting[address][1]
            
        return d

    def timeout(self, address):
        # timeout called by clients (should it be called by servers?)
        if address in self.connecting:
            logger.info('connection timed out')
            self.connecting[address][2].transport.loseConnection()

    def open(self, sid, session_key, relays=0):
        if sid in self.shaking:
            addr = self.shaking[sid][2]
            
            # session reset
            def do_reset():
                logger.warning('doing session reset for {0}'.format(sid.encode('hex')))
                self.send_handshake(sid, address, relays)
                
            # create encryption option
            obj = Crypter(session_key, callback=do_reset)
            self.session_objs[sid] = obj
            
            # update sid -> address map
            self.update_map(sid, self.connecting[addr][2])
#            self.session_map[sid] = self.connecting[addr][2]
            del self.shaking[sid]
            del self.connecting[addr]
            
            util.emit_async('session-opened', self, sid, relays)
        else:
            raise Exception, "TODO: key-exchange"

#    def open(self, sid, session_key, relays=0):
#        if sid in self.shaking:
#            addr = self.shaking[sid][2]
#            # shouldn't be in shaking if not in connecting
#            self.session_map[sid] = self.connecting[addr][2]
#            del self.shaking[sid]
#            del self.connecting[addr]
#            util.emit_async('session-opened', self, sid, relays)

    @defer.inlineCallbacks
    def send_greet(self, address, ack=False):
        print 'one'
        yield self.connect(address)
        print 'two'
        yield self.router.send(PacketType.GREET, '', address, ack=ack)
        print 'three'

    def start(self, port):
        self.port = reactor.listenTCP(port, self)
        return self.port
        
    def stop(self):
        if self.port is not None:
            self.port.stopListening()
            self.port = None
        
    def send(self, data, sid, address):
        if sid in self.session_map:
            self.session_map[sid].send(data)
        elif address in self.connecting: 
            # check for valid packets
            type = PacketType(struct.unpack('!1H', data[:2])[0])
            if type in [PacketType.GREET, PacketType.HANDSHAKE1,
                        PacketType.HANDSHAKE2, PacketType.HANDSHAKE3,
                        PacketType.ACK, PacketType.CLOSE]:

                self.connecting[address][2].send(data)
            else:
                logger.error(
                    "trying to send {0} packet through uninitialized session"
                                            .format(type))
                raise ValueError, \
                    "trying to send {0} packet through uninitialized session" \
                                            .format(type)

        else:
            logger.error("cannot send to sid not in session map")
            raise KeyError, "cannot send to sid not in session map"
            
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

    def _get_proto_by_addr(self, addr):
        d = dict(((x.getPeer().host,x.getPeer().port),x) 
                                for x in self.session_map.values())
        #TODO tuple or ipv4addr?
        return d.get(addr, None)
