#! /usr/bin/env python
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
# router.py
#
# #### each network has it's own adapter/router
#TODO make tun/tap both work, selectable
#TODO starting/stopping router doesn't owrk right
#     * clear peer list when going offline, if we go back online other peer things we are still connected
#     * should we keep the peer list and just refresh/let it timeout, or clear it?

import logging
import random
from struct import pack, unpack
from tuntap import TunTap
from twisted.internet import reactor, defer
from util.event import Event
from peers import PeerManager
from mods.pinger import Pinger
import sessions
import settings
import util

logger = logging.getLogger(__name__)


class Router(object):
    '''The router object handles all the traffic between the virtual tun/tap
    device and the peers.  All traffic flows through the router, where it is
    filtered (encryption/decryption) and sent to its destination or a handler
    for special packets.

    Packet format: TBD'''
    VERSION = pack('H', 1)

    TIMEOUT = 5 # 5s
    # packet types
    ENCODED = 0x80
    DATA = 1
    DATA_RELAY = 2
    ACK = 3
    RELAY = 4

    #USER = 0x80

    def __init__(self, network, tuntap=None):
        if tuntap is None:
            mode = network.adapter_mode
            tuntap = TunTap(self, mode)

        logger.info('Initializing router in {0} mode.'.format('TAP' if tuntap.is_tap else 'TUN'))

        self.handlers = {}
        self._requested_acks = {}
        self.addr_map = {}

        self.network = util.get_weakref_proxy(network)

        # check if we are using SSL
        if settings.get_option(self.network.name + '/' + 'use_ssl', False):
            self.sm = sessions.SSLSessionManager(self)
        else:
            self.sm = sessions.SessionManager(self)
        self.pm = PeerManager(self)

        # move this out of router?
        self.pinger = Pinger(self)

        self._tuntap = tuntap

        # move out of router?
        import bootstrap
        self._bootstrap = bootstrap.TrackerBootstrap(network)

        # add handler for message acks
        self.register_handler(self.ACK, self.handle_ack)

    def get_my_address(self):
        '''Get interface address (IP or MAC), return a deferred.
        Override'''
        pass

    @defer.inlineCallbacks
    def start(self):
        '''Start the router.  Starts the tun/tap device and begins listening on
        the UDP port.'''
        # start tuntap device
        self._tuntap.start()

        # configure tun/tap address (deferred)
        yield self._tuntap.configure_iface(self.network.virtual_address)

        # set mtu (if possible)
        mtu = settings.get_option(self.network.name + '/' + 'set_mtu', None)
        if mtu is None:
            mtu = settings.get_option(self.network.name + '/' + 'set_mtu', None)
        if mtu is not None:
            self._tuntap.set_mtu(mtu)
            
        # start connection listener
        self.sm.start(self.network.port)

        # get addresses (deferred)
        yield self.get_my_address()

        logger.info('router started, listening on port {0}'.format(self.network.port))

        self._bootstrap.start()
        self.pinger.start()
        reactor.callLater(1, util.get_weakref_proxy(self.pm.try_old_peers))


    def stop(self):
        '''Stop the router.  Stops the tun/tap device and stops listening on the
        UDP port.'''
        self.pinger.stop()
        self._bootstrap.stop()
        self._tuntap.stop()
        # bring down iface?
        # todo determine states: online/offline/disabled/adapterless?
        self.pm.clear()
        self.sm.stop()

        logger.info('router stopped')

    def relay(self, data, dst):
        if dst in self.pm:
            self.sm.send(data, dst, self.pm[dst].address)
            logger.debug('relaying packet to {0}'.format(repr(dst)))


    def send(self, type, data, dst, ack=False, id=0, ack_timeout=None, clear=False, faddress=None):
        '''Send a packet of type with data to address.  Address should be an id
        if the peer is known, since address tuples aren't unique with relaying'''
        # shortcut for data, to speed up teh BWs
        if type == self.DATA:
            dst_id = dst[1]
            dst = dst[0]
            # encode
            try:
                data = self.sm.encode(dst_id, data)
            except KeyError, s:
                logger.critical('failed to encode data packet: {0}'.format(s))
                return
            # pack
            data = pack('!2H', type, id) + dst_id + self.pm._self.id + data
            # send
            return self.sm.send(data, dst_id, dst)

        elif dst in self.sm.session_map: # sid
            dst_id = dst
            dst = self.sm.session_map[dst]
        elif dst in self.sm.shaking: #TODO: check for valid shaking packets
            dst_id = dst
            dst = self.sm.shaking[dst][2]
        elif dst in self.pm and dst != self.pm._self.id: # don't send to self...
            # it shouldn't really reach this point, as there shouldn't be
            # anyone in pm who's not in sm
            pi = self.pm[dst]
            dst_id = pi.id
            dst = pi.address

        # address tuple (like for greets)
        elif isinstance(dst, tuple):
            pi = self.pm.get(dst)
            if pi is not None:
                dst_id = pi.id
            else:
                dst_id = '\x00'*16 # non-routable


        # unknown peer dst TODO: this should return an erroring deferred?
        elif faddress is not None:
            # got packet from an unknown id, send a greet to the address
            self.sm.try_greet(faddress)
            return #TODO does this prevent acks on greets?
        else:
            logger.error('cannot send to unknown dest {0}'.format(repr(dst)))
            return #todo throw exception

        # want ack?
        if ack or id > 0:
            if id == 0:
                id = random.randint(0, 0xFFFF)
            d = defer.Deferred()
            timeout = ack_timeout if ack_timeout is not None else self.TIMEOUT
            timeout_call = reactor.callLater(timeout, util.get_weakref_proxy(self._timeout), id)
            self._requested_acks[id] = (d, timeout_call)
        else:
            d = None

        # encode the data
        if data != '' and not clear:
            if dst_id in self.sm.session_map:
                data = self.sm.encode(dst_id, pack('!H',type) + data)
            #logger.debug('encoding packet {0}'.format(type))
                type = self.ENCODED
            else:
                logger.critical('trying to send encrypted packet ({0}) w/out session!!'.format(type))
                return #todo throw exception?
        else:
            logger.debug('sending clear packet ({0})'.format(type))

        data = pack('!2H', type, id) + dst_id + self.pm._self.id + data

        #TODO exception handling for bad addresses
        self.sm.send(data, dst_id, dst)

        return d

    def handle_ack(self, type, data, address, src):
        id = unpack('!H', data)[0]
        logger.debug('got ack with id {0}'.format(id))

        if id in self._requested_acks:
            d, timeout_call = self._requested_acks[id]
            del self._requested_acks[id]
            timeout_call.cancel()
            d.callback(id)

    def _timeout(self, id):
        if id in self._requested_acks:
            d = self._requested_acks[id][0]
            del self._requested_acks[id]
            logger.info('ack timeout')
            d.errback(Exception('call {0} timed out'.format(id)))
        else:
            logger.info('timeout called with bad id??!!?')

    def send_packet(self, packet):
        '''Got a packet from the tun/tap device that needs to be sent out'''
        pass

    def recv(self, data, address):
        '''Received a packet from the protocol port.
        Parse it and send it on its way.
        Data types get special treatment to reduce overhead.'''

        # get dst and src 128-bit ids
        dst = data[4:20]

        # ours?
        if dst == self.pm._self.id or dst == '\x00'*16:
            pt = unpack('!H', data[:2])[0]
            # get dst and src 128-bit ids
            src = data[20:36]

            if pt == self.DATA:
                # data packets are always encrypted
                packet = self.sm.decode(src, data[36:])
                self.recv_packet(packet, src, address)

            else:
                if pt == self.ENCODED:
                    packet = self.sm.decode(src, data[36:])
                    pt, packet = unpack('!H',packet[:2])[0], packet[2:]
                    #logger.debug('got encoded packet {0}'.format(pt))
                else:
                    packet = data[36:]

                id = unpack('!H', data[2:4])[0]


                if pt in self.handlers:
                    try:
                        self.handlers[pt](pt, packet, address, src)
                    except Exception, e:
                        import traceback
                        logger.error('packet handler for packet type {1} raised\
                            exception:\n {0}'.format(e, pt))
                        logger.debug(traceback.format_exc())
                        return # don't ack
                        
                if id > 0: # ACK requested 
                    logger.debug('sending ack')
                    # ack to unknown sources?  - send greets!
                    self.send(self.ACK, data[2:4], src, clear=True, faddress=address)
                logger.debug('handling {0} packet from {1}'.format(pt, src.encode('hex')))

        # nope!
        else:
            return self.relay(data, dst)


    def recv_packet(self, packet, address):
        '''Got a data packet from a peer, need to inject it into tun/tap'''
        pass

    def register_handler(self, type, callback):
        '''Register a handler for a specific packet type.  Handles will be
        called as 'callback(type, data, address, src_id)'.'''

        logger.debug('registering packet handler for packet type: {0}'.format(type))

        if type in self.handlers:
            self.handlers[type] += callback

        else:
           self.handlers[type] = Event()
           self.handlers[type] += callback

    def unregister_handler(self, type, callback):
        '''Remove a registered handler for a specific packet type.'''

        logger.debug('unregistering packet handler for packet type: \
                     {0}'.format(type))

        if type in self.handlers:
            self.handlers[type] -= callback

class TapRouter(Router):
    addr_size = 6

    SIGNATURE = 'PVA'+Router.VERSION

    def get_my_address(self, *x):
        '''Get interface address (IP/MAC)'''

        d = defer.Deferred()
        def do_ips(ips=None):
            '''get the IP/mac addresses'''
            if ips is None:
                ips = self._tuntap.get_ips()
            if len(ips) > 0:
                if self.pm._self.vip_str not in ips:
                    logger.critical('TAP addresses ({0}) don\'t contain \
                                    configured address ({1}), taking address\
                                    from adapter ({2})'.format(ips,
                                            self.pm._self.vip_str, ips[0]))
                    self.pm._self.vip = util.encode_ip(ips[0])
            else:
                logger.critical('TAP adapater has no addresses')

            # get mac addr
            self.pm._self.addr = self._tuntap.get_mac() #todo check if this is none?

            # get 'direct' addresses
            from net.netifaces import ifaddresses
            addr = ifaddresses()
            for dev in addr['AF_INET']:
                if dev not in ['lo'] and not dev.startswith('pytun'):
                    for address in addr['AF_INET'][dev]:
                        self.pm._self.direct_addresses.append((address['address'], 
                                                        self.network.port))

            self.pm._update_pickle()

            reactor.callLater(0, d.callback, ips)

        # Grap VIP, so we display the right one
        ips = self._tuntap.get_ips()
        if len(ips) == 1 and ips[0] == '0.0.0.0': # interface not ready yet?
            logger.warning('Adapter not read, delaying...')
            reactor.callLater(3, do_ips)
        else:
            do_ips(ips)

        return d

    def send_packet(self, packet):
        '''Got a packet from the tun/tap device that needs to be sent out'''

        dst = packet[0:self.addr_size]

        # if ip in peer list
        if dst in self.addr_map:
            self.send(self.DATA, packet, self.addr_map[dst])

        # or if it's a broadcast
        elif self._tuntap.is_broadcast(dst):
            #logger.debug('sending broadcast packet')
            for addr in self.addr_map.values():
                self.send(self.DATA, packet, addr)

        # if we don't have a direct connection...
        #elif dst in self.relay_map:
        #    self.send(self.DATA, packet, self.relay_map[dst])
        else:
            logger.debug('got packet on wire to unknown destination: \
                         {0}'.format(dst.encode('hex')))

    def recv_packet(self, packet, src, address):
        '''Got a data packet from a peer, need to inject it into tun/tap'''

        dst = packet[0:self.addr_size]

        # is it ours?
        if dst == self.pm._self.addr or self._tuntap.is_broadcast(dst):
            self._tuntap.doWrite(packet)
            logger.debug('writing packet to TAP device')

# todo what to do about this
            src_addr = packet[self.addr_size:self.addr_size*2]
            if src_addr not in self.addr_map: # negligible speed hit
                self.addr_map[src_addr] = (address, src)
                logger.warning('got new addr from packet!: {0}'.format(src_addr.encode('hex')))
        else:
            # no, odd
            self.send_packet(packet)
            logger.debug('got packet (encrypted) with different dest ip, relay packet?')



class TunRouter(Router):
    '''not currently in use'''
    addr_size = 4

    SIGNATURE = 'PVU'+Router.VERSION

    def get_my_address(self):
        '''Get interface address (IP)'''
        ips = self._tuntap.get_ips()
        if len(ips) > 0:
#            ips = [x[0] for x in ips] # if we return (addr,mask)
            if self.pm._self.vip_str not in ips:
                logger.critical('TUN addresses ({0}) don\'t contain configured address ({1}), taking address from adapter ({2})'.format(ips, self.pm._self.vip_str, ips[0]))
                self.pm._self.vip = util.encode_ip(ips[0])
                self.pm._self.addr = self.pm._self.vip
        else:
            logger.critical('TUN adapater has no addresses')
            self.pm._self.addr = self.pm._self.vip

        self.pm._update_pickle()

    def send_packet(self, packet):
        '''Got a packet from the tun/tap device that needs to be sent out'''
#        print 'tunk:\n',packet[0:14].encode('hex')
        dst = packet[0:self.addr_size]
#        prot = unpack('1B',packet[9])[0]

        # if ip in peer list
        if dst in self.addr_map:
            self.send(self.DATA, packet, self.addr_map[dst])
        else:
            logger.debug('got packet on wire to unknown destination: {0}'.format(dst.encode('hex')))

    def recv_packet(self, packet):
        '''Got a data packet from a peer, need to inject it into tun/tap'''
        # check?
        dst = packet[0:self.addr_size]

        if dst == self.pm._self.addr:
            self._tuntap.doWrite(packet)
        else:
            self.send_packet(packet)
            logger.debug('got packet with different dest ip, relay packet?')

def get_router(net, *args, **kw):
    if net.adapter_mode == 'TAP':
        return TapRouter(net, *args, **kw)
    else:
        return TunRouter(net, *args, **kw)