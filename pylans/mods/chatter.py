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
# chatter.py

from twisted.internet import defer, reactor
import collections
import logging
from .. import util
from ..util import event
from ..packets import PacketType

PacketType.add(CHAT_MSG=28)

logger = logging.getLogger(__name__)

class ChatterBox(object):

    MAX_CHAT_RETRIES = 2

    def __init__(self, iface):
        self.iface = util.get_weakref_proxy(iface)
        self.handler_list = {}
        self.msg_queue = collections.deque()

        # Event
#        self.message_received = Event()

        # Closure magic
        def register_handler(net):
            def handler(type, msg, addr, src_id):
                self.handle_chat_msg(net, type, msg, addr, src_id)

            net.router.register_handler(PacketType.CHAT_MSG, handler)
            self.handler_list[net.id] = handler

        def unregister_handler(net):
            net.router.unregister_handler(PacketType.CHAT_MSG, 
                                          self.handler_list[net.id])
            del self.handler_list[net.id]

        for net in iface.get_network_list():
            if net.is_running:
                register_handler(net)

        iface.network_started += register_handler
        iface.network_stopped += unregister_handler

    def is_running(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass


    def send_message(self, nid, peer, line):
        # check to make sure 'line' is a str?

        self.msg_queue.append((nid, peer, line))
    
        reactor.callLater(0, self._process_msg_queue)

    @defer.inlineCallbacks        
    def _process_msg_queue(self):
        
        while self.msg_queue:
            nid, peer, line = self.msg_queue.popleft()
    
            net = self.iface.get_network(nid)
            peer = self.iface.get_peer_info(peer)

            logger.info('sending msg to {0}'.format(peer.name))

            try:
                yield util.retry_func(net.router.send, 
                                  (PacketType.CHAT_MSG, line, peer, True),
                                  tries=self.MAX_CHAT_RETRIES)
            except Exception, e:
                logger.warning('never got ack for sending msg to {0}'
                                    .format(peer.name))


    def handle_chat_msg(self, net, type, msg, addr, src_id):
        logger.info('got a msg from {0}'.format(src_id.hex))
        event.emit('message-received', self, net.id, src_id, msg)

