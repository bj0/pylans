# Copyright (C) 2010  Brian Parma (execrable@gmail.com)
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
# pinger.py

from platform import system
from random import randint
from struct import pack
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
import logging
import settings
import util

if system() == 'Windows':   # On Windows, time() has low resolution(~1ms)
    from time import clock as time
else:
    from time import time


logger = logging.getLogger(__name__)

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

    def __init__(self, router, interval=None):
        if interval is None:
            interval = settings.get_option(router.network.name+'/interval',5.0)
        self.interval = interval
        self.router = util.get_weakref_proxy(router)
        self.active_pings = {}
        self._lp = LoopingCall(self.do_pings)
        
        router.register_handler(self.PING, self.handle_ping)
        router.register_handler(self.PONG, self.handle_pong)
        
    def send_ping(self, peer):
        pi = PingInfo(peer.id)
        timeout_call = reactor.callLater(self.MAX_PING_TIME, self._ping_timeout, pi.id)
        self.active_pings[pi.id] = (pi, timeout_call)
        self.router.send(self.PING, pi.id, peer)
        logger.debug('sending ping to {0}'.format(peer.name))
        
    def handle_ping(self, type, data, address, src_id):

        logger.debug('received ping, sending pong')
        
        self.router.send(self.PONG, data, src_id)

    def handle_pong(self, type, data, address, src_id):
        if data in self.active_pings:
            pi, timeout_call = self.active_pings[data]
            dt = pi.duration()
            timeout_call.cancel()
            self.router.pm.peer_list[pi.peer_id].ping_time = dt
            self.router.pm.peer_list[pi.peer_id].timeouts = 0
            del self.active_pings[data]
            logger.debug('received pong response from {0} with time {1}'.format(self.router.pm.peer_list[pi.peer_id].name, dt))
            
            
    def do_pings(self):
        if self.running:
            for peer in self.router.pm.peer_list.values():
                self.send_ping(peer)        
            

    def _ping_timeout(self, id):
        if id in self.active_pings:
            pi = self.active_pings[id][0]
            del self.active_pings[id]
                
            if pi.peer_id in self.router.pm.peer_list:
                peer = self.router.pm.peer_list[pi.peer_id]
                peer.timeouts += 1
                if peer.timeouts > self.MAX_TIMEOUTS:
                    self.router.pm._timeout(peer)

        
    def start(self):
        self.running = True
        self._lp.start(self.interval)
        logger.info('starting pinger on {0} with {1}s interval'.format(self.router.network.name,self.interval))
        
    def stop(self):
        self.running = False
        self._lp.stop()
        logger.info('stopping pinger on {0} with {1}s interval'.format(self.router.network.name,self.interval))
        
