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
# networks.py

import binascii
import logging
import os
from util import event
from vpn import router
from vpn import settings

#from router import Router

logger = logging.getLogger(__name__)

class Network(object):

    def __init__(self, name, key=None, username=None, address=None, port=None,
                 id=None, enabled=None, mode=None, key_str=None):

        self._name = name
#        self.name = self._name
        self._id = None
        self.router = None
        self._running = False

        if enabled is not None:
            self.enabled = enabled

        if key is not None:
            self.key = key
        elif key_str is not None:
            self.key_str = key_str
        elif (self.key is None) or self.key == '':
            self.key = os.urandom(56)

        if username is not None:
            self.username = username
        elif self.username is None:
            self.username = 'user@%s'%name

        if address is not None:
            self.virtual_address = address
        elif self.virtual_address is None:
            self.virtual_address = '10.1.1.1/24'

        if port is not None:
            self.port = port
        elif self.port is None:
            self.port = 8015

        if id is not None:
            self.id = id
        elif self.id is None:
            self.id = os.urandom(16)

        if mode is not None:
            self.adapter_mode = mode
        elif self.adapter_mode is None:
            self.adapter_mode = 'TAP'

        settings.save()

        # Events
#        self.address_changed = Event()
#        self.started = Event()
#        self.stopped = Event()

    def new_connection(self, net, peer):
        if peer.is_direct:
            peers = self.known_addresses

            if peer.id not in peers:
                peers[peer.id] = [peer.address]
                self.known_addresses = peers

            elif peer.address not in peers[peer.id]:
                #TODO will an IP need to have multiple ports? this eliminates clutter
                for addr in peers[peer.id]:
                    if addr[0] == peer.address[0]:
                        peers[peer.id].remove(addr)
#
                peers[peer.id].append(peer.address)
                self.known_addresses = peers


    @property
    def is_running(self):
        return self._running

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if self._name != value:
            settings.MANAGER.rename_section(self._name, value)
            self._name = value
            event.emit('network-changed', self)
            settings.save()

    def start(self):
        if self.enabled:
            if self._running:
                return
            if self.router is None:
                self.router = router.get_router(self)

            event.register_handler('peer-added', self.router.pm, self.new_connection);
            self.router.start()
            self._running = True
            event.emit('network-started', self)
            logger.info('network {0} started'.format(self.name))
        else:
            logger.info('network {0} not starting, disabled'.format(self.name))

    def stop(self):
        if not self._running:
            return
        if self.router is not None:
            event.unregister_handler('peer-added', self.router.pm, self.new_connection);
            self.router.stop()
            self._running = False
            event.emit('network-stopped', self)
            logger.info('network {0} stopped'.format(self.name))

    def _get(self, item, default=None):
        return settings.get_option(self._name+'/%s'%item, default)

    def _set(self, item, value):
        return settings.set_option(self._name+'/%s'%item, value)

    @property
    def enabled(self):
        return self._get('enabled',True)

    @enabled.setter
    def enabled(self, value):
        if isinstance(value, bool):
            if value != self.enabled:
                self._set('enabled',value)
                event.emit('network-changed', self)
        else:
            raise TypeError('enabled must be True or False')
        settings.save()

    @property
    def key(self):
        try:
            return self._get('key','').decode('base64')
        except binascii.Error:
            return self._get('key')

    @key.setter
    def key(self, value):
        if self.key != value:
            self._set('key', value.encode('base64').replace('\n',''))
            #TODO impliment key change
            event.emit('network-changed', self)
            settings.save()

    @property
    def key_str(self):
        return self._get('key','')

    @key_str.setter
    def key_str(self, value):
        if value != self.key_str:
            self._set('key', value)
            event.emit('network-changed', self)
            settings.save()

    @property
    def username(self):
        return self._get('name')

    @username.setter
    def username(self, value):
        if self.username != value:
            self._set('name', value)
            event.emit('network-changed', self)
            settings.save()

    @property
    def virtual_address(self):
        return self._get('virtual_address')

    @virtual_address.setter
    def virtual_address(self, value):
        if self.virtual_address != value:
            self._set('virtual_address', value)
            event.emit('network-changed', self)
            settings.save()

#        self.address_changed(value)

    address = virtual_address

    @property
    def virtual_ip(self):
        if self.virtual_address is not None:
            return self.virtual_address.split('/')[0]
        return None

    @virtual_ip.setter
    def virtual_ip(self, value):
        if self.virtual_ip != value:
            if self.virtual_address is None:
                mask = '24'
            else:
                mask = self.virtual_address.split('/')[1]
            self.virtual_address = '%s/%s'%(value, mask)
            event.emit('network-changed', self)
            settings.save()

    ip = virtual_ip

    @property
    def port(self):
        return self._get('port')

    @port.setter
    def port(self, value):
        if self.port != value:
            self._set('port', value)
            event.emit('network-changed', self)
            settings.save()

    @property
    def wan_port(self):
        return self._get('wan_port', self.port)

    @wan_port.setter
    def wan_port(self, value):
        if self.wan_port != value:
            self._set('wan_port', value)

    @property
    def adapter_mode(self):
        return self._get('adapter_mode')

    @adapter_mode.setter
    def adapter_mode(self, value):
        if value != self.adapter_mode:
            self._set('adapter_mode', value)

    @property
    def id(self):
        if self._id is None and self._get('id') is not None:
            self._id = self._get('id').decode('hex')
        return self._id


    @id.setter
    def id(self, value):
        if isinstance(value, str):
            if self.id != value:
                self._set('id', value.encode('hex'))
                self._id = value
                settings.save()
        else: # how to tell if it's hex or bytes?? TODO
            raise TypeError, "Bad type for ID"

    @property
    def known_addresses(self):
        return self._get('known_addresses', {})

    @known_addresses.setter
    def known_addresses(self, value):
        if self.known_addresses != value:
            self._set('known_addresses', value)
            event.emit('network-changed', self)
            settings.save()


class NetworkManager(object):

    def __init__(self, load=True):
        self.network_list = {}

        if load:
            self.load_all()

    def network_exists(self, name):
        return settings.MANAGER.has_section(name)

    def start_network(self, network):
        if network in self:
            self[network].start()

    def start_all(self):
        for net in self.network_list.values():
            if not net.is_running:
                net.start()

    def stop_network(self, network):
        if network in self:
            self[network].stop()

    def enable_network(self, network):
        if network in self:
            self[network].enabled = True
            event.emit('network-enabled', network)


    def disable_network(self, network):
        if network in self:
            self[network].enabled = False
            event.emit('network-disabled', network)
            self.stop_network(network)
            network.router = None # shut down the adapter?

    def load(self, name):
        if self.network_exists(name):
            nw = Network(name)
            self.network_list[nw.id] = nw
            event.emit('network-loaded',self, nw)
            return nw
        return None

    def load_all(self):
        for nw in self._saved_networks():
            self.load(nw)

    def create(self, name, key=None, username=None, address=None, port=None,
                 id=None, enabled=None, mode=None, key_str=None):
        if self.network_exists(name):
            logger.warning('A network by that name already exists') #TODO throw exception?
            if name in self:
                return self[name]
            else:
                return Network(name)


        net = Network(name, key=key, username=username, address=address, port=port,
                        id=id, enabled=enabled, mode=mode, key_str=key_str)
        self.network_list[net.id] = net
        event.emit('network-created',self, net)
        logger.debug('network {0} created'.format(net.name))
        return net

    def remove(self, name):
        if self.network_exists(name):
            net = self[name]
            settings.MANAGER.remove_section(name)
            settings.save()
            event.emit('network-removed', self, net)
            logger.info('network {0} removed from settings'.format(name))

        if name in self:
            net = self[name]
            net.stop()
            del self.network_list[net.id]# TODO check refcount
            logger.debug('network {0} removed from manager'.format(name))

    def get_by_vip(self, vip):
        for net in self.network_list.values():
            if net.router.pm.get_by_vip(vip) is not None:
                return net

    def get_by_peer(self, peer):
        for net in self.network_list.values():
            if peer in net.router.pm:
                return net
        return None

    def get_by_name(self, name):
        for nw in self.network_list.values():
            if nw.name == name:
                return nw
        return None

    def _saved_networks(self):
        nl = settings.MANAGER.sections()
        if 'settings' in nl:
            nl.remove('settings')
        return nl

    ###### Container Type Overloads

    def iterkeys(self):
        for nw in self.network_list:
            yield nw

    def __iter__(self):
        return self.iterkeys()

    def __len__(self):
        return len(self.network_list)

    def __getitem__(self, item):
        if isinstance(item, str):                     # name or id
            if item in self.network_list:
                net = self.network_list[item]
            else:
                net = self.get_by_name(item)

        elif isinstance(item, Network):                 # network reference
            if item in self:
                return item
        else:
            raise TypeError('Unrecognized key type')

        if net is None:
            raise KeyError('Unknown network.')
        else:
            return net


    def __contains__(self, item):
        if isinstance(item, str):                     # name or id
            return ((item in self.network_list) or
                (self.get_by_name(item) is not None))
        elif isinstance(item, Network):                 # network reference
            return (item in self.network_list.values())

        return False


MANAGER = NetworkManager()
