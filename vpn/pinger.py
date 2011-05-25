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
# todo: make interval dynamically change running pinger?

from platform import system
from random import randint
from struct import pack
import logging
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from vpn import settings
import util

if system() == 'Windows':   # On Windows, time() has low resolution(~1ms)
    from time import clock as time
else:
    from time import time


logger = logging.getLogger(__name__)

class Pinger(object):

    MAX_PING_TIME = 10.0
    MAX_TIMEOUTS = 10
    PING = 0x20 - 1
#    PONG = 0x20 - 2

    def __init__(self, router, interval=None):
        self.router = util.get_weakref_proxy(router)
        self.active_pings = {}
        self._lp = LoopingCall(self.do_pings)
        if interval is not None:
            self.interval = interval

#        router.register_handler(self.PING, self.handle_ping)
#        router.register_handler(self.PONG, self.handle_pong)

    def _get(self, prop, default):
        return settings.get_option(self.router.network.name+'/'+prop, default)

    def _set(self, prop, value):
        settings.set_option(self.router.network.name+'/'+prop, value)

    interval = property(lambda s: s._get('ping_interval',5.0), lambda s,v: s._set('ping_interval',v))

    def send_ping(self, peer):
        d = self.router.send(self.PING, '', peer, ack=True, ack_timeout=self.MAX_PING_TIME)
        d.addCallback(self.ping_ack, peer, time())
        d.addErrback(self._ping_timeout, peer)
        logger.debug('sending ping to {0}'.format(peer.name))

    def ping_ack(self, id, peer, ping_time):
        dt = time() - ping_time
        self.router.pm.peer_list[pi.peer_id].ping_time = dt
        self.router.pm.peer_list[pi.peer_id].timeouts = 0

        logger.debug('received ping response from {0} with time {1}'.format(self.router.pm.peer_list[pi.peer_id].name, dt))


    def do_pings(self):
        if self.running:
            for peer in self.router.pm.peer_list.values():
                self.send_ping(peer)


    def _ping_timeout(self, id, peer):

        if peer.id in self.router.pm.peer_list:
#            peer = self.router.pm.peer_list[peer.id]
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
