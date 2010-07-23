# networks.py

import os
import uuid

import settings
from event import Event
from router import Router

class Network(object):
    
    def __init__(self, name, key=None, user_name=None, address=None, port=None, id=None):
        
        self._name = name
        self.name = self._name
        self._id = id
        self.router = None
        
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
            
        if user_name is not None:
            self.user_name = user_name
        elif self.user_name is None:
            self.user_name = 'user@%s'%name
            
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
        
    def new_connection(self, peer):
        peers = self.known_addresses
        if peer.address not in peers:
            peers.append(peer.address)
            self.known_addresses = peers
            
        
    def start(self):
        if self.router is None:
            self.router = Router(self)

        self.router.pm.peer_added += self.new_connection
        self.router.start()
        
    def stop(self):
        if self.router is not None:
            self.router.stop()
        
    def get(self, item, default=None):
        return settings.get_option(self._name+'/%s'%item, default)
        
    def set(self, item, value):
        return settings.set_option(self._name+'/%s'%item, value)
        
    @property
    def key(self):
        try:
            return self.get('key','').decode('base64')
        except Error:
            return self.get('key')
        
    @key.setter
    def key(self, value):
        self.set('key', value.encode('base64').replace('\n',''))
        settings.save()
        
    @property
    def user_name(self):
        return self.get('name')
        
    @user_name.setter
    def user_name(self, value):
        self.get('name', value)
        settings.save()
        
    @property
    def virtual_address(self):
        return self.get('virtual_address')
        
    @virtual_address.setter
    def virtual_address(self, value):
        self.set('virtual_address', value)
        settings.save()
        
#        self.address_changed(value)
        
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
        return self.get('port')
        
    @port.setter
    def port(self, value):
        self.set('port', value)
        settings.save()
        
    @property
    def id(self):
        if self._id is None and self.get('id') is not None:
            self._id = uuid.UUID(hex=self.get('id'))
        return self._id
        
    @id.setter
    def id(self, value):
        if isinstance(value, uuid.UUID):
            self.set('id', value.hex)
            self._id = value
        else:
            self.set('id', value)
            self._id = uuid.UUID(hex=value)
        settings.save()
        
    @property
    def known_addresses(self):
        return self.get('known_addresses', [])
        
    @known_addresses.setter
    def known_addresses(self, value):
        self.set('known_addresses', value)
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
        
        
    def load(self, name):
        if self.network_exists(name):
            nw = Network(name)
            self.network_list[nw.id] = nw
            return nw
        return None
        
    def load_all(self):
        networks = settings.get_option('settings/networks')
        if networks is not None:
            for nw in networks:
                self.load(nw)
        
    def create(self, name, key=None, user_name=None, address=None, port=None, id=None):    
        networks = settings.get_option('settings/networks')
        if self.network_exists(name):
            print 'A network by that name already exists'
            return Network(name)
            
            
        net = Network(name, key, user_name, address, port, id)
        self.network_list[id] = net            
        return net

    def get_by_name(self, name):
        for nw in self.network_list:
            if nw.name == name:
                return nw
        return None
    
    ###### Container Type Overloads
    
    def iterkeys(self):
        for nw in self.network_list:
            yield peer
    
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
    


