#! /usr/bin/env python
#
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
# tuntap device interface
#
#
# TUN mode - Layer 3, only IP packets are passed to the device:
# -- packet format is:
# -- http://en.wikipedia.org/wiki/IPv4
# -- src ip address is at 12 (96)
# -- dst ip address is at 16 (128)
#
# TAP mode - layer 2, ethernet packets, which sometimes (but not always)
#  embed IP packets.
# -- packet format is:
# -- [mac dst] [mac src] [type] [data] [crc]
# --     6         6       2       ?     4
# common types:
# -- 0x0800 - ipv4
# -- 0x0806 - arp
#
# TODO: for windows: setting ip address, mtu,

from __future__ import absolute_import
import logging
from . import util
from ..net.netifaces import *


logger = logging.getLogger(__name__)

class TunTapBase(object):
    '''
        Access to the virtual tun/tap device (Base Class).
    '''


#    @classmethod
#    def is_ip6_discovery(mac):
#    '''ip6 neighbor discovery address are between 33:33:00:00:00:00 - 33:33:FF:FF:FF:FF (n2n et al)'''
#        if mac[0:2] == '\x33\x33':
#            return True
#        return False

    def get_mac(self):
        '''Get mac using netifaces'''
        try:
            ret = ifaddresses(self.ifname)
            mac = ret['AF_LINK']['addr']
        except (ValueError, KeyError), e:
            logger.critical('unable to get MAC address for {0}:{1}'
                    .format(self.ifname,e))
            #return None TODO: when this is none it passes it to other peers, causing exceptions, need better solution
            raise

        logger.debug('got mac address: {0}'.format(mac))

        return util.encode_mac(mac)

    def get_ips(self):
        try:
            ips = ifaddresses(self.ifname)['AF_INET']
            ips = [x['address'] for x in ips]
        except (ValueError, KeyError), e:
            logger.critical('unable to get IP addresses for {0}:{1}'
                        .format(self.ifname, e))
            return []
            #raise

        logger.debug('got {0} ip addresses: {1}'.format(len(ips),ips))
        return ips


    @property
    def is_tap(self):
        '''Is this a TAP device?'''
        return (self.mode == self.TAPMODE)

    @property
    def is_tun(self):
        '''Is this a TUN device?'''
        return not self.is_tap

    @classmethod
    def is_multicast(cls, mac):
        '''ethernet (ipv4) multicast addresses are 01:00:5E:??:??:??

        >>> import util
        >>> TunTapBase.is_multicast(util.encode_mac('01:00:5e:a1:00:3c'))
        True

        >>> TunTapBase.is_multicast(util.encode_mac('FF:00:5e:a1:00:3c'))
        False
        '''
        if mac[0:3] == '\x01\x00\x5e':
            return True
        return False

    @classmethod
    def is_broadcast(cls, mac):
        '''ethernet broadcast is typically FF:FF:FF:FF:FF:FF, but we can just check the LSB of the first octet (which includes multicast)

        >>> import util
        >>> TunTapBase.is_broadcast(util.encode_mac('01:00:5e:a1:00:3c'))
        True

        >>> TunTapBase.is_broadcast(util.encode_mac('FF:00:5e:a1:00:3c'))
        True

        >>> TunTapBase.is_broadcast(util.encode_mac('FE:00:5e:a1:00:3c'))
        False
        '''
        if ord(mac[0]) & 1 == 1:
            return True
        return False



