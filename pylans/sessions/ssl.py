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
import logging
from .. import util
from .. import protocol
from . import SessionManager

logger = logging.getLogger(__name__)

        
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

        logger.info('connection success: {0}, {1}'.format(addr, proto))
        #TODO connected but not shaking state?

    def connect(self, address):
        # check if already connected
        if address not in self.connecting:
            logger.debug('trying to connect to {0}'.format(address))
            d = defer.Deferred()
            # how to deferr the result of this, or save this connection in handshaking?
            self.connecting[address] = \
                 (reactor.connectSSL(address[0],address[1], self,
                  ssl.ClientContextFactory()), d)

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
        elif address in self.connecting: 
            # check for valid packets
            type = struct.unpack('!1H', data[:2])[0]
            if type in [self.GREET, self.HANDSHAKE, self.HANDSHAKE_ACK,
                        self.KEY_XCHANGE, self.KEY_XCHANGE_ACK, self.router.ACK]:

                self.connecting[address][2].send(data)
            else:
                logger.error("trying to send {0} packet through uninitialized"
                            +" session")
                raise ValueError, "trying to send {0} packet through " \
                            +"uninitialized session"
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
