#!/usr/bin/python
# prompt.py
# todo: quit message?
# more commands: dump peer, ??s

import sys
import uuid
import logging
from cmd import Cmd

from twisted.internet import reactor
from twisted.internet.threads import deferToThread

#import settings
#import router
#from networks import NetworkManager
#from router import PeerInfo # for pickle
from interface import Interface
from chatter import ChatterBox
import settings

logger = logging.getLogger()
__levels = { 0 : logging.CRITICAL,
             1 : logging.ERROR,
             2 : logging.WARNING,
             3 : logging.INFO,
             4 : logging.DEBUG }
#logging.basicConfig(level=__levels.get(settings.get_option('settings/loglevel',0),0))

class Prompt(Cmd):

    #completekey = None
    def __init__(self, iface):
        self.iface = iface
        
        # Events
        iface.peer_added += lambda net, peer: sys.stdout.write('peer {0} added to network {1}'.format(peer.name, net.name))
        iface.peer_removed += lambda net, peer: sys.stdout.write('peer {0} removed from network {1}'.format(peer.name, net.name))
        iface.network_started += lambda net: sys.stdout.write('network {0} started'.format(net))
        iface.network_stopped += lambda net: sys.stdout.write('network {0} stopped'.format(net))
        iface.message_received += lambda net, peer, msg: sys.stdout.write('{0}@{1}: {2}'.format(peer.name, net.name, msg))
        
        Cmd.__init__(self)
        
        
    def do_log(self, line):
        line = line.lower()
        
        if line == 'debug':
            logger.setLevel(logging.DEBUG)
            settings.set_option('settings/loglevel', 4)
            print 'Logging threshold set to DEBUG'

        elif line == 'info':
            logger.setLevel(logging.INFO)
            settings.set_option('settings/loglevel', 3)
            print 'Logging threshold set to INFO'
        
        elif line.startswith('warn'):
            logger.setLevel(logging.WARNING)
            settings.set_option('settings/loglevel', 2)
            print 'Logging threshold set to WARNING'
        
        elif line == 'error':
            logger.setLevel(logging.ERROR)
            settings.set_option('settings/loglevel', 1)
            print 'Logging threshold set to ERROR'
        
        elif line.startswith('crit'):
            logger.setLevel(logging.CRITICAL)
            settings.set_option('settings/loglevel', 0)
            print 'Logging threshold set to CRITICAL'
        
        
        
    def do_connect(self, line):
        try:
            line = line.split()
            ip, port = line[0:2]
            port = int(port)
            
            if len(line) > 2:
                network = line[3]
            else:
                network = None
            print 'Trying to connect to %s @ %d' % (ip,port)
            
            reactor.callFromThread(iface.connect_to_address,(ip,port), network)
            
        except ValueError:
            print 'Invalid arguments.'
            
            
    def do_status(self, line):
        line = line.split()
        if len(line) > 0:
            nets = line
            nets = [ iface.get_network(net) for net in nets if net is not None ]
        else:
            nets = iface.get_network_list()
            
        for net in nets:
#            net = iface.get_network(net)
            print '========= Network Status ========='
            print 'name:        {0}'.format(net.name)
            print 'id:          {0}'.format(net.id)
            print 'address:     {0}'.format(net.virtual_address)
            print 'port:        {0}'.format(net.port)
            print 'my name:     {0}'.format(net.username)
            if net.router is not None:
                print '# of peers:  {0}'.format(len(net.router.pm))
            else:
                print 'network offline'
            
    def complete_status(self, text, line, begidx, endidx):
        nets = iface.get_network_names()
        if not text:
            return nets
            
        return [ net for net in nets if net.startswith(text) ]
        
            
    def do_list(self, line):
        line = line.split()
        if len(line) > 0:
            nets = line
            nets = [ iface.get_network(net) for net in nets if net is not None ]
        else:
            nets = iface.get_network_list()
        
        for net in nets:
            print '========= Peers (%s) =========' % net.name
            for p in iface.get_peer_list(net):
                print 'name:      {0}'.format(p.name)
                print 'id:        {0}'.format(p.id)
                print 'vip:       {0}'.format(p.vip_str)
                print 'address:   {0}'.format(p.address)
                print 'is_direct: {0}'.format(p.is_direct)
                if(not p.is_direct):
                    print '  relay:   {0}'.format(p.relay_id)
                print 'ping_time: {0} ms'.format(p.ping_time*1e3)
                print 'timeouts:  {0}'.format(p.timeouts)
            
    def complete_list(self, text, line, begidx, endidx):
        nets = iface.get_network_names()
        if not text:
            return nets
            
        return [ net for net in nets if net.startswith(text) ]
            
    def do_msg(self, line):
        # this doesn't work if the network as a '@' in it
        name = line.split()[0]
        name = name.split('@')
        if len(name) > 1:
            name, net = '@'.join(name[:-1]),name[-1]
        else:
            name, net = name[0], None
        msg = ' '.join(line.split()[1:])
        peer = iface.get_peer_info(name, net)
        net = iface.get_network()
        if peer is not None and net is not None:
            reactor.callFromThread(cbox.send_message, net.id, peer.id, msg)
        else:
            print 'peer or network is not specified'
            
            
    def emptyline(self, *args):
        self.do_status('')
            
    def do_EOF(self, line):
        print
        reactor.callFromThread(reactor.stop)
        return True
        
        


if __name__ == '__main__':

    iface = Interface()
    if len(iface.get_network_dict()) < 1:
        iface.create_new_network('newnetwork')

    iface.start_all_networks()
    cbox = ChatterBox(iface)
    p = Prompt(iface)
    deferToThread(p.cmdloop)

    # give it time to bring up teh interface, then open tcp port
    reactor.callLater(5, reactor.listenTCP, cbox.port, cbox)

    
    print 'run'
    reactor.run()    
    
