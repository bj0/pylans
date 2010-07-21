#!/usr/bin/python
# prompt.py
# todo: quit message?
# more commands: peer list, dump peer, ??s

from cmd import Cmd

from twisted.internet import reactor
from twisted.internet.threads import deferToThread

import router
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
            
    def do_EOF(self, line):
        print
        reactor.callFromThread(reactor.stop)
        return True
        
        


if __name__ == '__main__':
    rt = router.Router()
    cbox = ChatterBox(rt)
    p = Prompt(rt)
    deferToThread(p.cmdloop)

    rt._tuntap.configure_iface(router.config.address)
    reactor.callLater(5, reactor.listenTCP,15034, cbox, interface=router.config.address.split('/')[0])
    reactor.listenUDP(router.config.port, rt._proto)        
#            rt.try_register(('10.10.10.216',8015))

    
    print 'run'
    reactor.run()    
    
