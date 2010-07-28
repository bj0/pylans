# networks.py

import os
import uuid
import logging

import settings
import event
from event import Event
from router import Router

logger = logging.getLogger(__name__)

class Network(object):
    
    def __init__(self, name, key=None, username=None, address=None, port=None, id=None):
        
        self._name = name
        self.name = self._name
        self._id = id
        self.router = None
        self._running = False
        
        networks = settings.get_option('settings/networks')
        if networks is None:
            networks = []
            settings.set_option('settings/networks',networks)
            
        if name not in networks:
            networks.append(name)
            settings.set_option('settings/networks',networks)

        if key is not None:
            self.key = key
        elif self.key == '':
            self.key = os.urandom(16)
            
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
            self.id = uuid.uuid4()
        
        settings.save()        
        
        # Events
#        self.address_changed = Event()
#        self.started = Event()
#        self.stopped = Event()
        
    def new_connection(self, net, peer):
        peers = self.known_addresses
        if peer.address not in peers:
            peers.append(peer.address)
            self.known_addresses = peers
            
        
    def is_running(self):
        return self._running
        
    def start(self):
        if self._running:
            return
        if self.router is None:
            self.router = Router(self)

        event.register_handler('peer-added', self.router.pm, self.new_connection);
        self.router.start()
        self._running = True
        event.emit('network-started', self)
        logger.info('network {0} started'.format(self.name))
        
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
    def key(self):
        try:
            return self._get('key','').decode('base64')
        except Error:
            return self._get('key')
        
    @key.setter
    def key(self, value):
        self._set('key', value.encode('base64').replace('\n',''))
        #TODO impliment key change
        settings.save()
        
    @property
    def username(self):
        return self._get('name')
        
    @username.setter
    def username(self, value):
        self._set('name', value)
        settings.save()
        
    @property
    def virtual_address(self):
        return self._get('virtual_address')
        
    @virtual_address.setter
    def virtual_address(self, value):
        self._set('virtual_address', value)
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
        if self.virtual_address is None:
            mask = '24'
        else:
            mask = self.virtual_address.split('/')[1]
        self.virtual_address = '%s/%s'%(value, mask)
        
    ip = virtual_ip
        
    @property
    def port(self):
        return self._get('port')
        
    @port.setter
    def port(self, value):
        self._set('port', value)
        settings.save()
        
    @property
    def id(self):
        if self._id is None and self._get('id') is not None:
            self._id = uuid.UUID(hex=self._get('id'))
        return self._id
        
    @id.setter
    def id(self, value):
        if isinstance(value, uuid.UUID):
            self._set('id', value.hex)
            self._id = value
        else:
            self._set('id', value)
            self._id = uuid.UUID(hex=value)
        settings.save()
        
    @property
    def known_addresses(self):
        return self._get('known_addresses', [])
        
    @known_addresses.setter
    def known_addresses(self, value):
        self._set('known_addresses', value)
        settings.save()
        
        
class NetworkManager(object):

    def __init__(self, load=True):
        self.network_list = {}
        
        if load:
            self.load_all()
        
    def network_exists(self, name):
        networks = settings.get_option('settings/networks')
        if networks is None:
            settings.set_option('settings/networks',[])
            return False
            
        if name in networks:
            return True
        return False

    def start_network(self, network):
        if network in self:
            self[network].start()
    
    def start_all(self):
        for net in self.network_list.values():
            if not net.is_running():
                net.start()
        
    def load(self, name):
        if self.network_exists(name):
            nw = Network(name)
            self.network_list[nw.id] = nw
            event.emit('network-loaded',self, nw)
            return nw
        return None
        
    def load_all(self):
        networks = settings.get_option('settings/networks')
        if networks is not None:
            for nw in networks:
                self.load(nw)
        
    def create(self, name, key=None, username=None, address=None, port=None, id=None):    
        if self.network_exists(name):
            logger.warning('A network by that name already exists')
            return Network(name)
            
            
        net = Network(name, key, username, address, port, id)
        self.network_list[id] = net
        event.emit('network-created',self, net)
        logger.debug('network {0} created'.format(net.name))
        return net
        
    def remove(self, name):
        if self.network_exists(name):
            networks = settings.get_option('settings/networks')
            networks.remove(name)
            settings.set_option('settings/networks', networks)
            settings.MANAGER.remove_section(name)
            logger.info('network {0} removed from settings'.format(name))
        
        if name in self:
            net = self[name]
            net.stop()
            del self.network_list[net.id]
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
    
    ###### Container Type Overloads
    
    def iterkeys(self):
        for nw in self.network_list:
            yield nw
    
    def __iter__(self):
        return self.iterkeys()
    
    def __len__(self):
        return len(self.network_list)
    
    def __getitem__(self, item):
        if isinstance(item, str):                     # name
            net = self.get_by_name(item)
                
        elif isinstance(item, uuid.UUID):               # network id
            net = self.network_list[item]
            
        else:
            raise TypeError('Unrecognized key type')

        if net is None:
            raise KeyError('Unknown network.')
        else:
            return net

    
    def __contains__(self, item):
        if isinstance(item, str):                     # name
            return self.get_by_name(item) is not None
        elif isinstance(item, uuid.UUID):               # network id
            return (item in self.network_list)
    

MANAGER = NetworkManager()
