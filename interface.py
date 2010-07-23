
# how much to put in this?
# should i switch to global events?
# global interface "singleton" (like settings)

class Interface(object):


    def get_network_list(self):
    
    def get_network(self, name=None, id=None):
    
    def get_peer_list(self, network):
    
    def get_peer_info(self, network, peer_id):
    
    
    def set_network_name(self, newname, oldname=None, id=None):
    
    def set_network_key(self, key, name=None, id=None):
    
    def set_my_name(self, name, network_name=None, id=None):
    
    

