# chatter.py

from random import randint
from struct import pack, unpack

from twisted.protocols import basic
from twisted.internet import protocol, reactor
#from twisted.internet.endpoints import TCP4ClientEndpoint   # - new in 10.1

import event
from router import Router
#from event import Event
import settings

class Chatter(basic.LineReceiver):
    
    def connectionMade(self):
        self.factory.add(self)
    
    def connectionLost(self, reason):
        self.factory.remove(self)
    
    def lineReceived(self, line):
        print 'wtf',repr(line)
        self.factory.receive(self, line)
    
    def message(self, line):
        self.sendLine(line)
#        self.transport.write(line+'\r\n')
        print 'sendmsg',line
  
    
class ChatterBox(protocol.ClientFactory):
    protocol = Chatter

    CHAT_INIT = 0x10 + 1
    CHAT_ACK = 0x10 + 2    
    
    def __init__(self, iface):
        self.iface = iface
        self.connections = {}
        self.handler_list = {}
        self.msg_queue = {}
        self.port = settings.get_option('chatter/port',randint(15000, 45000))
#        settings.get_option('network/chatter/port', self.port)
        
        # Event
#        self.message_received = Event()
        
        # Closure magic
        def register_handler(net):
            def handler(type, port, addr):
                self.handle_chat_init(net.router, type, port, addr)
                
            net.router.register_handler(self.CHAT_INIT, handler)
            self.handler_list[net.id] = handler
            
        def unregister_handler(net):
            net.router.unregister_handler(self.CHAT_INIT, self.handler_list[net.id])
            del self.handler_list[net.id]
                
        for net in iface.get_network_list():
            if net.is_running():
                register_handler(net)
            
        iface.network_started += register_handler
        iface.network_stopped += unregister_handler
        
        
        
    def add(self, chatter):
        host = chatter.transport.getPeer() # virtual host
        vip = Router.encode_ip(host[1])
        print 'add chatter',host
        if vip not in self.connections:
            net = self.iface.get_network_manager().get_by_vip(vip)
            peer = net.router.pm.get_by_vip(vip)
#            chatter.pid = peer.id
            chatter.vip = vip
            chatter.pid = peer.id
            chatter.nid = net.id
            self.connections[vip] = chatter
            if vip in self.msg_queue:
                msgs = self.msg_queue[vip]
#                print msgs
                for msg in msgs:
#                    print 'sending',msg
                    chatter.message(msg)
                del self.msg_queue[vip]
        else:
            print 'connection dropped',host
            chatter.loseConnection()
    
    def remove(self, chatter):
        print 'remove chatter'
        if hasattr(chatter, 'vip'):     # for bad connections that never get added
            if chatter.vip in self.connections:
                del self.connections[chatter.vip]

    def send_all(self, line):
        for con in self.connections.values():
            con.message(line)
    
    def send_message(self, nid, pid, line):
        # check to make sure 'line' is a str?
#        print 'len',len(self.connections),self.connections
        peer = self.iface.get_network_dict()[nid].router.pm[pid]
        vip = peer.vip
        if vip in self.connections:
            self.connections[vip].message(line)
        else:
            if vip in self.msg_queue:
                self.msg_queue[vip].append(line)
            else:
                self.msg_queue[vip] = [line]
                
            self.try_connect(peer)
            print 'doing connect to',peer.name,peer.address
            #self.connect(self.router.pm[pid]).addCallback(send_message, pid, line)
    
    def receive(self, chatter, line):
        print line, 'from'
#        self.message_received(chatter.pid, line)
        event.emit('message-received', self, chatter.nid, chatter.pid, line)
    
    def try_connect(self, peer):
        if peer.vip not in self.connections:
            net = self.iface.get_network_manager().get_by_peer(peer)
            print peer.name, net
            # try to xchange port info
            net.router.send(self.CHAT_INIT, pack('I',self.port), peer.address)
            
#    def try_register(self, address):
#        '''Try to register self with a peer by sending a register packet
#        with own peer info.  Will continue to send this packet until an 
#        ack is received or MAX_REG_TRIES packets have been sent.'''
#        if not (address in self.router.pm):
#            print 'here'
#            
#            def send_register(i):
#                print 'sendreg',i
#                if i > self.MAX_REG_TRIES or address in self.router.pm:
#                    return
#                else:
#                    self.router.send(Router.REGISTER, self._my_pickle, address)
#                    reactor.callLater(self.REG_TRY_DELAY, send_register, i+1)
#                    
#            reactor.callLater(self.REG_TRY_DELAY, send_register, 0)
#        else:
#            print 'wtf'
            
    def handle_chat_init(self, router, type, port, address):
        port = unpack('I',port)[0]
        peer = router.pm.get_by_address(address)
        if peer.id not in self.connections:
            vaddress = (router.decode_ip(peer.vip), port)
            reactor.connectTCP( vaddress[0], vaddress[1], self)
        
        router.send(self.CHAT_ACK, pack('I',self.port), address)
    
    def disconnect(self, peer):
        if peer.id in self.connections:
            self.connections[peer.vip].loseConnection()
            
