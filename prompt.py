#!/usr/bin/python
# prompt.py
# todo: quit message?
# more commands: dump peer, ??s

import uuid
from cmd import Cmd

from twisted.internet import reactor
from twisted.internet.threads import deferToThread

#import settings
#import router
from networks import NetworkManager
from router import PeerInfo # for pickle
from chatter import ChatterBox

class Prompt(Cmd):

    def __init__(self, router):
        self.router = router
        Cmd.__init__(self)
        
    def do_connect(self, line):
        try:
            ip, port = line.split()
            port = int(port)
            print 'Trying to connect to %s @ %d' % (ip,port)
            
            reactor.callFromThread(self.router.pm.try_register,(ip,port))
            
        except ValueError:
            print 'Invalid arguments.'
            
            
    def do_status(self, line):
        print '========= Network Status ========='
        print 'name:        {0}'.format(self.router.network.name)
        print 'id:          {0}'.format(self.router.network.id)
        print 'address:     {0}'.format(self.router.network.virtual_address)
        print 'port:        {0}'.format(self.router.network.port)
        print 'my name:     {0}'.format(self.router.network.user_name)
        print '# of peers:  {0}'.format(len(self.router.pm))
            
            
    def do_list(self, line):
        pl = self.router.pm.peer_list

        print '========= Peers ========='
        for p in pl.values():
            print 'name:      {0}'.format(p.name)
            print 'id:        {0}'.format(p.id)
            print 'vip:       {0}'.format(self.router.decode_ip(p.vip))
            print 'address:   {0}'.format(p.address)
            print 'is_direct: {0}'.format(p.is_direct)
            if(p.is_direct):
                print 'relay:     {0}'.format(p.relay_id)
            print 'ping_time: {0} ms'.format(p.ping_time*1e3)
            print 'timeouts:  {0}'.format(p.timeouts)
            
            
    def do_msg(self, line):
        name = line.split()[0]
        msg = ' '.join(line.split()[1:])
        peer = self.router.pm.get_by_name(name)
        if peer is not None:
            reactor.callFromThread(cbox.send_message,peer.id, msg)
            
            
    def emptyline(self, *args):
        self.do_status('')
            
    def do_EOF(self, line):
        print
        reactor.callFromThread(reactor.stop)
        return True
        
        


if __name__ == '__main__':

    net_mgr = NetworkManager()
    if len(net_mgr) < 1:
        net = net_mgr.create('newnetwork')
    else:
        net = net_mgr.network_list.values()[0]

    net.start()
    cbox = ChatterBox(net.router)
    p = Prompt(net.router)
    deferToThread(p.cmdloop)

    reactor.callLater(5, reactor.listenTCP, cbox.port, cbox, interface=net.ip)

    
    print 'run'
    reactor.run()    
    
