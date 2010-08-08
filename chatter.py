# chatter.py

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

class ChatterBox(object):

    CHAT_MSG = 0x10 + 1
    MAX_CHAT_RETRIES = 2
    
    def __init__(self, iface):
        self.iface = iface
        self.handler_list = {}
#        self.msg_queue = {}
        
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

    def start(self):
        pass
        
    def stop(self):        
        pass
            
    
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
            
            
    def handle_chat_msg(self, net, type, msg, addr, vip):
        event.emit('message-received', self, net.id, net.router.pm[vip].id, msg)
        logger.info('got a msg from {0}'.format(repr(vip))
    
