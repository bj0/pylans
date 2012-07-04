from twisted.internet import reactor, defer
from twisted.internet import protocol
from twisted.protocols import basic
import logging
import struct

from . import util

logger = logging.getLogger(__name__)


class UDPPeerProtocol(protocol.DatagramProtocol):
    '''Protocol or sending/receiving data to peers'''

    def __init__(self, recv_cb):
        self.recv = recv_cb

    def send(self, data, address):
        '''Send data to address'''
        try:
            logger.trace('sending {1} bytes on UDP port to {0}',
                            address, len(data))
            self.transport.write(data, address)
            
        except Exception, e:
            logger.warning('UDP send threw exception:\n  {0}', e)
            ##TODO this is here because UDP socket fills up and just dies
            # but it's UDP so we can drop packets

    def datagramReceived(self, data, address):
        '''Called by twisted when data is received from address'''
        self.recv(data, address)
        logger.trace('received {1} bytes on UDP port from {0}',
                        address, len(data))

    def connectionRefused(self):
        logger.warning('connectionRefused on UDP port')


class TCPPeerProtocol(basic.Int32StringReceiver):
    _type = 'TCP'
    def __init__(self, deferred, recv_cb, factory):
        self.deferred = deferred
        self.recv = recv_cb
        self.factory = factory

    def connectionMade(self):
        self._peer = self.transport.getPeer()
        self._peer = (self._peer.host, self._peer.port)
        if self.deferred is not None:
            d, self.deferred = self.deferred, None
            d.callback(self)
        
    def connectionLost(self, reason):
        print 'proto connection lost'
        if self.deferred is not None:
            d, self.deferred = self.deferred, None
            d.errback(reason)
        else: #connection was already made
            self.factory._connect_fail(self, self._peer)

    def send(self, data):
        self.transport.write(struct.pack('!i',len(data))+data)
        logger.trace('sending {0} bytes on {1} port'
                        , len(data), self._type)
        
#    def dataReceived(self, data):
    def stringReceived(self, data):
        logger.trace('received {0} bytes on {1} port'
                        , len(data), self._type)
        self.recv(data, self._peer)
        
    def close(self):
        self.transport.loseConnection()
        

class SSLPeerProtocol(TCPPeerProtocol):
    _type = 'SSL'

class TCPPeerFactory(protocol.ServerFactory,protocol.ClientFactory):
    protocol = TCPPeerProtocol
    
    def __init__(self):
        pass    
        
    def buildProtocol(self, addr):
        pass
#
    def clientConnectionLost(self, connector, reason):
        pass
        
    def clientConnectionFailed(self, connector, reason):
        pass
        
class SSLPeerFactory(TCPPeerFactory):
    protocol = SSLPeerProtocol
