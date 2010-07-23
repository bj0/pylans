# pinger.py

from random import randint
from struct import pack, unpack
from time import time

from twisted.internet import reactor
from twisted.internet.task import LoopingCall

class PingInfo(object):
    def __init__(self, peer_id):
        self.id = pack('H',randint(0, 0xFFFF))
        self.peer_id = peer_id
        self.ping_time = time()
        self.running = False
        
    def duration(self):
        return time()-self.ping_time

class Pinger(object):

    MAX_PING_TIME = 10.0 
    MAX_TIMEOUTS = 10
    PING = 0x20 - 1
    PONG = 0x20 - 2   

    def __init__(self, router, interval=2.0):
        self.interval = interval
        self.router = router
        self.active_pings = {}
        self._lp = LoopingCall(self.do_pings)
        
#        router.handle_packet += self.handle_packet
        router.register_handler(self.PING, self.handle_ping)
        router.register_handler(self.PONG, self.handle_pong)
        
    def send_ping(self, peer):
#        print 'sending ping'
        pi = PingInfo(peer.id)
        self.active_pings[pi.id] = pi
        self.router.send(self.PING, pi.id, peer.address)
        
    def handle_ping(self, type, data, address):
        self.router.send(self.PONG, data, address)

    def handle_pong(self, type, data, address):
        if data in self.active_pings:
            pi = self.active_pings[data]
            dt = pi.duration()
            self.router.pm.peer_list[pi.peer_id].ping_time = dt
            self.router.pm.peer_list[pi.peer_id].timeouts = 0
            del self.active_pings[data]
            #print 'got ping response:',dt
            
            
    def do_pings(self):
        if self.running:
            for peer in self.router.pm.peer_list.values():
                self.send_ping(peer)        
            
        for ping in self.active_pings.values():
            if ping.duration() > self.MAX_PING_TIME:
                del self.active_pings[ping.id]
                
                if ping.peer_id in self.router.pm.peer_list:
                    peer = self.router.pm.peer_list[ping.peer_id]
                    peer.timeouts += 1
                    if peer.timeouts > self.MAX_TIMEOUTS:
                        self.router.pm.timeout(peer)
 #                   print 'ping died'
        
    def start(self):
        self.running = True
        self._lp.start(self.interval)
        
    def stop(self):
        self.running = False
        self._lp.stop()
        
