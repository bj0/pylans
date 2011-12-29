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
# interface.py
# how much to put in this?
# should i switch to global events?
# global interface "singleton" (like settings)

import logging
from vpn import settings

logging.basicConfig(level=settings.get_option('settings/loglevel', 40))
logger = logging.getLogger(__name__)
global_logger = logging.getLogger()

from vpn.chatter import ChatterBox
from util.event import Event
from util import event
from vpn import networks


class Interface(object):


    def __init__(self, mgr=None):

        if mgr is None:
            mgr = networks.MANAGER

        self._mgr = mgr
        self._current = None

        # Events
        self.network_started = Event()
        self.network_stopped = Event()
        self.network_enabled = Event()
        self.network_disabled = Event()
        self.network_created = Event()
        self.network_removed = Event()
        self.network_changed = Event()
        self.peer_added = Event()
        self.peer_removed = Event()
        self.peer_changed = Event()
        self.message_received = Event()

        self._cbox = ChatterBox(self)

        event.register_handler('network-started', None, self.network_started)
        event.register_handler('network-stopped', None, self.network_stopped)
        event.register_handler('network-enabled', None, self.network_enabled)
        event.register_handler('network-disabled', None, self.network_disabled)
        event.register_handler('network-created', None, self.network_created)
        event.register_handler('network-removed', None, self.network_removed)
        event.register_handler('network-changed', None, self.network_changed)
        event.register_handler('peer-added', None, self._peer_added)
        event.register_handler('peer-removed', None, self._peer_removed)
        event.register_handler('peer-changed', None, self._peer_changed)
        event.register_handler('message-received', None, self._message_received)

    @property
    def log_level(self):
        return settings.get_option('settings/loglevel', 40)

    @log_level.setter
    def log_level(self, value):
        if self.log_level != value:
            settings.set_option('settings/loglevel', value)
            global_logger.setLevel(value)
            settings.save()

    def _peer_added(self, pm, peer):
        self.peer_added(pm.router.network, peer)

    def _peer_removed(self, pm, peer):
        self.peer_removed(pm.router.network, peer)

    def _peer_changed(self, pm, peer):
        self.peer_changed(pm.router.network, peer)

    def _message_received(self, cbox, nid, pid, text):
        network = self._mgr[nid]
        self.message_received(network, network.router.pm[pid], text)

    def get_network_manager(self):
        return self._mgr

    def get_network_list(self):
        return self._mgr.network_list.values()

    def get_network_names(self):
        return [ net.name for net in self.get_network_list() ]

    def get_network_dict(self):
        return self._mgr.network_list

    def _get_router(self, network):
        net = self.get_network(network)
        if net is not None:
            return net.router
        return None

    def get_network(self, network=None):
        # does not catch invalid network names, just returns previous correct
        # network
        if isinstance(network, networks.Network):
            self._current = network
        elif network is not None:
            if network in self._mgr:
                self._current = self._mgr[network]
            else:
                logger.warning('specified network not found')

        return self._current


    def get_peer_dict(self, network=None):
        router = self._get_router(network)
        if router is not None:
            return router.pm.peer_list
        return {}

    def get_peer_list(self, network=None):
        return self.get_peer_dict(network).values()

    def get_peer_names(self, network=None):
        return [ peer.name for peer in self.get_peer_list(network) ]

    def get_peer_info(self, peer, network=None):
        #TODO add gets for vip, name, alias?
        router = self._get_router(network)
        if router is not None and peer in router.pm:
            return router.pm[peer]
        return None


    def create_new_network(self, name, key=None, username=None, address=None, port=None,
                id=None, enabled=None, mode=None, key_str=None):
        if name not in self._mgr:
            self._current = self._mgr.create(name=name, key=key, username=username,
                    address=address, port=port, id=id, enabled=enabled, mode=mode, key_str=key_str)
        return self._current

    def delete_network(self, network):
        if self.get_network(network) is not None:
            self._mgr.remove(self._current.name)
            self._current = None

    def start_network(self, network):
        self._mgr.start_network(network)

    def start_all_networks(self):
        self._mgr.start_all()

    def stop_network(self, network):
        self._mgr.stop_network(network)

    def enable_network(self, network):
        self._mgr.enable_network(network)

    def disable_network(self, network):
        self._mgr.disable_network(network)

    def connect_to_address(self, address, network=None):
        if self.get_network(network) is not None:
            self._current.router.sm.try_greet(address)

    def send_message(self, network, peer, msg):
#        if not self._cbox.is_running():
#            self._cbox.start()
        if self.get_network(network) is not None:
            if peer in self._current.router.pm:
                self._cbox.send_message(self._current.id, peer, msg)

    def set_network_name(self, newname, network=None):
        if self.get_network(network) is not None:
            self._current.name = newname

    def set_network_key(self, key, network=None):
        if self.get_network(network) is not None:
            self._current.key = key

    def set_network_username(self, username, network=None):
        if self.get_network(network) is not None:
            self._current.username = username

    def set_network_address(self, address, network=None):
        if self.get_network(network) is not None:
            if '/' in address:
                self._current.address = address
            else:
                self._current.ip = address

    def set_network_ping_interval(self, interval, network=None):
        if self.get_network(network) is not None:
            settings.set_option(network.name+'/ping_interval', interval)

    def set_network_tracker_url(self, url, network=None):
        if self.get_network(network) is not None:
            settings.set_option(network.name+'/tracker', url)

    def set_network_use_tracker(self, use_tracker, network=None):
        if self.get_network(network) is not None:
            settings.set_option(network.name+'/use_tracker', use_tracker)

    def set_network_tracker_interval(self, interval, network=None):
        if self.get_network(network) is not None:
            settings.set_option(network.name+'/tracker_interval', interval)

    def get_network_setting(self, setting, network=None):
        if self.get_network(network) is not None:
            return settings.get_option(network.name+'/'+setting, None)

    def set_network_setting(self, setting, value, network=None):
        if self.get_network(network) is not None:
            settings.set_option(network.name+'/'+setting, value)
            settings.save()
