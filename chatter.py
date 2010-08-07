# chatter.py
# todo: switch to using UDP+ack for msgs instead of TCP to remove dependence on virtual adapter

from random import randint
from struct import pack, unpack
import logging

from twisted.protocols import basic
from twisted.internet import protocol, reactor
#from twisted.internet.endpoints import TCP4ClientEndpoint   # - new in 10.1

import event
from router import Router
#from event import Event
import settings
import util


logger = logging.getLogger(__name__)

#class Chatter(basic.LineReceiver):
#    
#    def connectionMade(self):
#        self.factory.add(self)
#    
#    def connectionLost(self, reason):
#        self.factory.remove(self)
#    
#    def lineReceived(self, line):
#        self.factory.receive(self, line)
#        logger.debug('received chat msg from {0}:{1}'.format(self.pid.get_hex(), line))
#    
#    def message(self, line):
#        self.sendLine(line)
#        logger.debug('sent chat msg to {0}:{1}'.format(self.pid.get_hex(), line))
  
    
#class ChatterBox(protocol.ClientFactory):
class ChatterBox(object):
#    protocol = Chatter

    CHAT_MSG = 0x10 + 1
#    CHAT_ACK = 0x10 + 2    
#    MAX_INIT_TRIES = 3
    MAX_CHAT_RETRIES = 2
    
    def __init__(self, iface):
        self.iface = iface
#        self.connections = {}
        self.handler_list = {}
#        self.msg_queue = {}
#        self.port = settings.get_option('chatter/port',randint(15000, 45000))
#        self._tcp_port = None
#        settings.get_option('network/chatter/port', self.port)
        
        # Event
#        self.message_received = Event()
        
        # Closure magic
        def register_handler(net):
            def handler(type, msg, addr, vip):
                self.handle_chat_msg(net, type, msg, addr, vip)
                
            net.router.register_handler(self.CHAT_MSG, handler)
            self.handler_list[net.id] = handler
            
        def unregister_handler(net):
            net.router.unregister_handler(self.CHAT_MSG, self.handler_list[net.id])
            del self.handler_list[net.id]
                
        for net in iface.get_network_list():
            if net.is_running():
                register_handler(net)
            
        iface.network_started += register_handler
        iface.network_stopped += unregister_handler
        
#    def is_running(self):
#        return self._tcp_port is not None

    def start(self):
        pass
#        logger.info('starting chatter on port %d',self.port)
#        self._tcp_port = reactor.listenTCP(self.port, self)
        
    def stop(self):        
        pass
#        if self._tcp_port is not None:
#            logger.info('stopping chatter on port %d',self.port)
#            self._tcp_port.stopListening()
#            self._tcp_port = None
            
#    def add(self, chatter):
#        host = chatter.transport.getPeer() # virtual host
#        vip = util.encode_ip(host[1])
#        if vip not in self.connections:
#            net = self.iface.get_network_manager().get_by_vip(vip)
#            peer = net.router.pm.get_by_vip(vip)
#            chatter.vip = vip
#            chatter.pid = peer.id
#            chatter.nid = net.id
#            self.connections[vip] = chatter
#            logger.info('chatter connection created with {0}'.format(host))
#            
#            if vip in self.msg_queue:
#                logger.debug('sending {1} queue\'d messages to {0}'.format(host, len(self.msg_queue[vip])))
#                msgs = self.msg_queue[vip]
#                for msg in msgs:
#                    chatter.message(msg)
#                del self.msg_queue[vip]
#        else:
#            chatter.transport.loseConnection()
#            logger.info('chatter connection dropped from {0}'.format(host))
#    
#    def remove(self, chatter):
#        if hasattr(chatter, 'vip'):     # for bad connections that never get added
#            if chatter.vip in self.connections:
#                del self.connections[chatter.vip]
#                logger.info('chatter connection to {0} closed'.format(util.decode_ip(chatter.vip)))

#    def send_all(self, line):
#        for con in self.connections.values():
#            con.message(line)
    
    def send_message(self, nid, peer, line):
        # check to make sure 'line' is a str?
        
        net = self.iface.get_network_dict()[nid]
        peer = net.router.pm[peer]
       
        logger.info('sending msg to {0}'.format(peer.name))
        
        def send_msg(err, i):
            d = net.router.send(self.CHAT_MSG, line, peer, True)
            d.addErrback(send_msg, i+1)
            logger.debug('sending msg attempt #{0}'.format(i))
            
        send_msg(None, 0)
            
#        vip = peer.vip
#        if vip in self.connections:
#            self.connections[vip].message(line)
#        else:
#            if vip in self.msg_queue:
#                self.msg_queue[vip].append(line)
#            else:
#                self.msg_queue[vip] = [line]
#                
#            self.try_connect(peer)
            
    def handle_chat_msg(self, net, type, msg, addr, vip):
        event.emit('message-received', self, net.id, net.router.pm[vip].id, msg)
        logger.info('got a msg from {0}'.format(repr(vip))
    
#    def receive(self, chatter, line):
##        self.message_received(chatter.pid, line)
#        event.emit('message-received', self, chatter.nid, chatter.pid, line)
    
#    def try_connect(self, peer):
#        if peer.vip not in self.connections:
#            net = self.iface.get_network_manager().get_by_peer(peer)
#            
#            def send_init(i):
#                if i <= self.MAX_INIT_TRIES and peer.vip not in self.connections:
#                    logger.debug('sending chat init packet #{0}'.format(i))
#                    net.router.send(self.CHAT_INIT, pack('I',self.port), peer)
#                    reactor.callLater(self.CHAT_TRY_DELAY, send_init, i+1)
#                    
#            reactor.callLater(self.CHAT_TRY_DELAY, send_init, 0)
#            logger.info('initiating chatter connection to {0} on {1}'.format(peer.name, net.name))
            
            
#    def handle_chat_init(self, router, type, port, address, vip):
#        port = unpack('I',port)[0]
#        peer = router.pm[vip]
#        if peer.id not in self.connections:
#            vaddress = (util.decode_ip(peer.vip), port)
#            reactor.connectTCP( vaddress[0], vaddress[1], self)

#        router.send(self.CHAT_ACK, pack('I',self.port), vip)
#        logger.info('received chat init packet from {0}, sending ack'.format(peer.name))
#    
#    def disconnect(self, peer):
#        if peer.id in self.connections:
#            self.connections[peer.vip].loseConnection()
#            
