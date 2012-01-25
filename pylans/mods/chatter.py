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

import logging
from .. import util
from ..util import event
from ..packets import PacketType

PacketType.add(CHAT_MSG=28)

logger = logging.getLogger(__name__)

class ChatterBox(object):

#    CHAT_MSG = 28
    MAX_CHAT_RETRIES = 2

    def __init__(self, iface):
        self.iface = util.get_weakref_proxy(iface)
        self.handler_list = {}
#        self.msg_queue = {}

        # Event
#        self.message_received = Event()

        # Closure magic
        def register_handler(net):
            def handler(type, msg, addr, src_id):
                self.handle_chat_msg(net, type, msg, addr, src_id)

            net.router.register_handler(PacketType.CHAT_MSG, handler)
            self.handler_list[net.id] = handler

        def unregister_handler(net):
            net.router.unregister_handler(PacketType.CHAT_MSG, self.handler_list[net.id])
            del self.handler_list[net.id]

        for net in iface.get_network_list():
            if net.is_running:
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
            if i < self.MAX_CHAT_RETRIES:
                d = net.router.send(PacketType.CHAT_MSG, line, peer, True)
                d.addErrback(send_msg, i+1)
                logger.debug('sending msg attempt #{0}'.format(i))
            else:
                logger.warning('never got ack for sending msg to {0}'.format(peer.name))

        send_msg(None, 0)


    def handle_chat_msg(self, net, type, msg, addr, src_id):
        event.emit('message-received', self, net.id, src_id, msg)
        logger.info('got a msg from {0}'.format(src_id.hex))
