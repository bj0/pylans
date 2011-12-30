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
# tracker bootstrap
# todo: change self.tracker into property that dynamically reads/writes
#          settings file, does this mean an independent tracker object can't be created?

from hashlib import sha1
from struct import unpack
import logging
import urllib2
import util
from twisted.internet import reactor
from twisted.web import client
from util import bencode
import settings



logger = logging.getLogger(__name__)

class TrackerBootstrap(object):

    def __init__(self, net, tracker=None, use_tracker=None, interval=None):
        self.net = util.get_weakref_proxy(net)
        
        if tracker is not None:
            self.tracker = tracker
        if use_tracker is not None:
            self.use_tracker = use_tracker
        if interval is not None:
            self.interval = interval
        
        if self.use_tracker:
            logger.info('tracker use is enabled')
        
    def _get(self, prop, default):
        return settings.get_option(self.net.name+'/'+prop, default)
        
    def _set(self, prop, value):
        settings.set_option(self.net.name+'/'+prop, value)
        
    tracker = property(lambda s: s._get('tracker','http://tracker.openbittorrent.com/announce'), lambda s,v: s._set('tracker',v))
    interval = property(lambda s: s._get('tracker_interval', 10*60), lambda s,v: s._set('tracker_interval',v))
    use_tracker = property(lambda s: s._get('use_tracker', False), lambda s,v: s._set('use_tracker',v))
        
    def tracker_request(self):
        id = self.net.router.pm._self.id*2
        id = urllib2.quote(id[:20])
        hash = sha1(self.net.key).digest()
        hash = urllib2.quote(hash)
        
        url = self.tracker + '?info_hash=' + hash + '&port=%d&compact=1&peer_id=' % self.net.port \
            + id + '&uploaded=0&downloaded=0&left=100'
            
        return client.getPage(url)
        
    def start(self):
        self._running = True
        self.run()
        
    def stop(self):
        self._running = False
        
    def run(self):
        if self.use_tracker and self._running:
            
            # function for successful response from tracker:
            def do_response(result):
                # parse result
                d = bencode.bdecode(result)
                
                if 'min interval' in d:
                    logger.info('tracker\'s min interval is %d, ours is %d' % (d['min interval'],self.interval))
                    self.interval = max(d['min interval'] + 5,self.interval) #TODO do we want to do use servers min interval or our own?
                
                peers = d.get('peers','')
                addrs = []
                for i in range(0, len(peers) // 6):
                    ip, port = peers[:4], peers[4:6]
                    ip = util.decode_ip(ip)
                    port = unpack('!H',port)[0]
                    addrs.append((ip,port))
                    peers = peers[6:]
                
                logger.info('got response from tracker with peers:'+str(addrs))
                self.net.router.sm.try_greet(addrs)
                reactor.callLater(self.interval, self.run)
                
            def do_error(err):
                logger.warning('tracker request failed: '+str(err))
                reactor.callLater(self.interval, self.run)
            
            logger.info('sending a request to tracker: %s' % self.tracker)
            d = self.tracker_request()
            d.addCallback(do_response)
            d.addErrback(do_error)
            
            
            
