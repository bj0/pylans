#!/usr/bin/python
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
# prompt.py
# todo: quit message?
# more commands: dump peer, ??s

from cmd import Cmd
import logging
from twisted.internet import reactor
from twisted.internet.threads import deferToThread
import settings
from interface import Interface
import util

logger = logging.getLogger()

class Prompt(Cmd):

    #completekey = None
    def __init__(self, iface):
        self.iface = iface

        # Events
        iface.peer_added += lambda net, peer: logger.info('peer {0} added to network {1}'.format(peer.name, net.name))
        iface.peer_removed += lambda net, peer: logger.info('peer {0} removed from network {1}'.format(peer.name, net.name))
        iface.network_started += lambda net: logger.info('network {0} started'.format(net))
        iface.network_stopped += lambda net: logger.info('network {0} stopped'.format(net))
        iface.message_received += lambda net, peer, msg: logger.critical('{0}@{1}: {2}'.format(peer.name, net.name, msg))

        self.previous_et = None
        self.prompt = 'pylans:> '

        Cmd.__init__(self)


    def do_log(self, line):
        line = line.lower()

        if line.startswith('deb'):
            self.iface.log_level = logging.DEBUG
            print 'Logging threshold set to DEBUG'

        elif line == 'info':
            self.iface.log_level = logging.INFO
            print 'Logging threshold set to INFO'

        elif line.startswith('warn'):
            self.iface.log_level = logging.WARNING
            print 'Logging threshold set to WARNING'

        elif line.startswith('err'):
            self.iface.log_level = logging.ERROR
            print 'Logging threshold set to ERROR'

        elif line.startswith('crit'):
            self.iface.log_level = logging.CRITICAL
            print 'Logging threshold set to CRITICAL'

        else:
            print 'Logging threshold is currently {0}'.format(logging.getLevelName(self.iface.log_level))

        settings.save()
        
    def help_log(self):
        print 'log ([level])\n set or display current log level\n'

    def do_connect(self, line):
        try:
            line = line.split()
            ip, port = line[0:2]
            port = int(port)

            if len(line) > 2:
                network = line[2]
            else:
                network = None

            net = self.iface.get_network(network)
            if net is None:
                print 'No network specified.'
            else:
                print 'Trying to connect to %s @ %d' % (ip, port)
                reactor.callFromThread(self.iface.connect_to_address, (ip, port), network)

        except ValueError:
            print 'Invalid arguments.'

    def help_connect(self):
        print 'connect [ip] [port] ([network])\n connect to a new peer address ' \
               + 'on specified or current network\n'
                

    def do_status(self, line):
        line = line.split()
        if len(line) > 0:
            nets = line
            nets = [ self.iface.get_network(net) for net in nets if net is not None ]
        else:
            nets = self.iface.get_network_list()

        for net in nets:
#            net = iface.get_network(net)
            print '========= Network Status ========='
            print 'name:        {0}'.format(net.name)
            print 'id:          {0}'.format(net.id.encode('hex'))
            print 'address:     {0}'.format(net.virtual_address)
            print 'port:        {0}'.format(net.port)
            print 'my name:     {0}'.format(net.username)
            if net.router is not None and net.is_running:
                print '# of peers:  {0}'.format(len(net.router.pm))
                print 'my vip       {0}'.format(net.router.pm._self.vip_str)
                print 'my addr      {0}'.format(net.router.pm._self.addr_str)
            else:
                print 'network offline'

    def complete_status(self, text, line, begidx, endidx):
        nets = self.iface.get_network_names()
        if not text:
            return nets

        return [ net for net in nets if net.startswith(text) ]

    def help_status(self):
        print 'status\n display status of defined networks\n'

    def do_list(self, line):
        line = line.strip()
        if len(line) > 0:
            nets = line.split()
            nets = [ self.iface.get_network(net) for net in nets if net is not None ]
        else:
            nets = self.iface.get_network_list()

        # print info for online networks
        for net in (x for x in nets if x.router is not None and x.is_running):
            print '========= Peers (%s) =========' % net.name
            for p in self.iface.get_peer_list(net):
                print 'name:      {0}'.format(p.name)
                print 'id:        {0}'.format(p.id.encode('hex'))
                print 'vip:       {0}'.format(p.vip_str)
                print 'addr:      {0}'.format(p.addr_str)
                print 'address:   {0}'.format(p.address)
                print 'is_direct: {0}'.format(p.is_direct)
                if(not p.is_direct):
                    rp = self.iface.get_peer_info(p.relay_id)
                    if rp is not None:
                        print '  relay:   {0} ({1})'.format(rp.name,
                                                     p.relay_id.encode('hex'))
                    else:
                        print '  relay: error, could not lookup pid {0}'.format(
                                            p.relay_id.encode('hex'))
                print 'ping_time: {0:.3f} ms'.format(p.ping_time * 1e3)
                print 'timeouts:  {0}'.format(p.timeouts)

    def complete_list(self, text, line, begidx, endidx):
        nets = self.iface.get_network_names()
        if not text:
            return nets

        return [ net for net in nets if net.startswith(text) ]

    def help_list(self):
        print 'list ([network])\n list info for specified or active networks\n'

    def do_msg(self, line):
        # this doesn't work if the network as a '@' in it
        name = line.split()[0]
        name = name.split('@')
        if len(name) > 1:
            name, net = '@'.join(name[:-1]), name[-1]
        else:
            name, net = name[0], None
        msg = ' '.join(line.split()[1:])
        peer = self.iface.get_peer_info(name, net)
        net = self.iface.get_network(net)
        if peer is not None and net is not None:
            reactor.callFromThread(self.iface.send_message, net.id, peer.id, msg)
        else:
            print 'peer or network is not specified'

#    def do_set(self, line):
#        if line == '':
#            return
#        line = line.split()
#        settings.set_option(line[0], ' '.join(line[1:]))
#        settings.save()
#
#    def do_get(self, line):
#        if line == '':
#            return
#        line = line.split()
#        print settings.get_option(line[0], ' '.join(line[1:]))

#    def complete_get(self, text, line, bidx, eidx):
#        text = line[4:eidx]
#        lst = []
#        for sec in settings.MANAGER.sections():
#            for opt in settings.MANAGER.options(sec):
#                lst.append('{0}/{1}'.format(sec,opt))
#
#        print '>{0},{1},{2},{3}<'.format(text,line,bidx,eidx)
#        return [ x for x in lst if x.startswith(text) ]

#    def do_remove(self, line):
#        if line == '':
#            return
#        line = line.split()
#        settings.MANAGER.remove_option(line[0])
#        settings.save()

    def do_py(self, line):
        # setup local vars (user_ns seems broken)
        iface = self.iface
        cli = self
        p = util.prompt(globals(),'IPython Interactive Console')
        p()

    def help_py(self):
        print 'py\n enter an (i)python interactive terminal for debugging purposes\n'

#    def emptyline(self, *args):
#        self.do_status('')

    def do_EOF(self, line):
        print
        reactor.callFromThread(reactor.stop)
        return True

    def postcmd(self, stop, line):
        '''This is executed after every command'''
        net = self.iface.get_network()
        if net is not None:
            self.prompt = 'pylans:{0}> '.format(net.name)
        
        return stop

def main():
    iface = Interface()
#    if len(iface.get_network_dict()) < 1:
#        iface.create_new_network('newnetwork')

    iface.start_all_networks()
#    cbox = ChatterBox(iface)
    p = Prompt(iface)
    deferToThread(p.cmdloop)

    # give it time to bring up teh interface, then open tcp port
#    reactor.callLater(5, reactor.listenTCP, cbox.port, cbox)


    reactor.run()


if __name__ == '__main__':
    main()
