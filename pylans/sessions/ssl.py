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
from struct import pack, unpack
import os
import logging
from .. import util
from .. import protocol
from .tcp import TCPSessionManager

logger = logging.getLogger(__name__)

        
class SSLSessionManager(TCPSessionManager):


###### ###### ###### Connection Stuff ###### ###### ###### 

    def update_map(self, sid, addr):
        if isinstance(addr, protocol.SSLPeerProtocol):
            self.session_map[sid] = addr
        else:
            raise ValueError, "session map stores ssl connections, not {0}"\
                                    .format(addr)

        
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


    def start(self, port):
        self.port = reactor.listenSSL(port, self,
                ssl.DefaultOpenSSLContextFactory('key.pem','cert.pem'))
        return self.port
        
    def open(self, sid, session_key, relays=0):
        if sid in self.shaking:
            addr = self.shaking[sid][2]
            # shouldn't be in shaking if not in connecting
#            self.session_map[sid] = self.connecting[addr][2]
            self.update_map(sid, self.connecting[addr][2])
            del self.shaking[sid]
            del self.connecting[addr]
            util.emit_async('session-opened', self, sid, relays)
            
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


