# chatter.py


from twisted.protocols import basic
from twisted.internet import protocol, reactor
#from twisted.internet.endpoints import TCP4ClientEndpoint   # - new in 10.1

from event import Event

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
    
    def __init__(self, router):
        self.router = router
        self.connections = {}
        self.msg_queue = {}
        
        # Event
        self.message_received = Event()
        
    def add(self, chatter):
        host = chatter.transport.getPeer() # virtual host
        vip = self.router.encode_ip(host[1])
        print 'add chatter',host
        if vip in self.router.pm:
            peer = self.router.pm[vip]
            chatter.pid = peer.id
            self.connections[chatter.pid] = chatter
            if chatter.pid in self.msg_queue:
                msgs = self.msg_queue[chatter.pid]
                print msgs
                for msg in msgs:
                    print 'sending',msg
                    self.send_message(chatter.pid, msg)
                del self.msg_queue[chatter.pid]
    
    def remove(self, chatter):
        print 'remove chatter'
        if hasattr(chatter, 'pid'):     # for bad connections that never get added
            if chatter.pid in self.connections:
                del self.connections[chatter.pid]
    
    def send_message(self, pid, line):
        # check to make sure 'line' is a str?
        print 'len',len(self.connections),self.connections
        if pid in self.connections:
            self.connections[pid].message(line)
        else:
            if pid in self.msg_queue:
                self.msg_queue[pid].append(line)
            else:
                self.msg_queue[pid] = [line]
                
            self.connect(self.router.pm[pid])
            print 'doing connect to',pid
            #self.connect(self.router.pm[pid]).addCallback(send_message, pid, line)
    
    def receive(self, chatter, line):
        print line, 'from', chatter.pid
        self.message_received(chatter.pid, line)
    
    def connect(self, peer):
        if peer.id not in self.connections:
            vaddress = (self.router.decode_ip(peer.vip), 15034)
#            ep = TCP4ClientEndpoint(reactor, *vaddress)
#            return ep.connect(self)
            reactor.connectTCP( vaddress[0], vaddress[1], self)
    
    def disconnect(self, peer):
        if peer.id in self.connections:
            self.connections[peer.id].loseConnection()
            
            
