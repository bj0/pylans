from twisted.internet import reactor, defer
from twisted.internet import protocol
from twisted.protocols import basic
import util
import logging
import struct

logger = logging.getLogger(__name__)


class UDPPeerProtocol(protocol.DatagramProtocol):
    '''Protocol or sending/receiving data to peers'''

    def __init__(self, recv_cb):
        self.recv = recv_cb

    def send(self, data, address):
        '''Send data to address'''
        try:
            self.transport.write(data, address)
            logger.debug('sending {1} bytes on UDP port to {0}'.format(address, len(data)))
        except Exception, e:
            logger.warning('UDP send threw exception:\n  {0}'.format(e))
            ##TODO this is here because UDP socket fills up and just dies
            # but it's UDP so we can drop packets

    def datagramReceived(self, data, address):
        '''Called by twisted when data is received from address'''
        self.recv(data, address)
        logger.debug('received {1} bytes on UDP port from {0}'.format(address, len(data)))

    def connectionRefused(self):
        logger.debug('connectionRefused on UDP port')



class SSLPeerProtocol(basic.Int32StringReceiver):

    def __init__(self, deferred, recv_cb):
        self.deferred = deferred
        self.recv = recv_cb

    def connectionMade(self):
        self._peer = self.transport.getPeer()
        self._peer = (self._peer.host, self._peer.port)
        if self.deferred is not None:
            d, self.deferred = self.deferred, None
            d.callback(self)
        
    def connectionLost(self, reason):
        if self.deferred is not None:
            d, self.deferred = self.deferred, None
            d.errback(self)

    def send(self, data):
        self.transport.write(struct.pack('!i',len(data))+data)
        logger.debug('sending {0} bytes on SSL port'.format(len(data)))
        
#    def dataReceived(self, data):
    def stringReceived(self, data):
        logger.debug('received {0} bytes on SSL port'.format(len(data)))
        self.recv(data, self._peer)
        
    def close(self):
        self.transport.loseConnection()
        
class SSLPeerFactory(protocol.ServerFactory,protocol.ClientFactory):
    protocol = SSLPeerProtocol
    
    def __init__(self):
        pass    
        
    def buildProtocol(self, addr):
        pass
#
    def clientConnectLost(self, connector, reason):
        pass
        
    def clientConnectionFailed(self, connector, reason):
        pass
