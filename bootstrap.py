# tracker bootstrap

from twisted.web import client
from twisted.internet import reactor

import settings
import util
import urllib2
import bencode
import logging

from hashlib import sha1
from struct import unpack

logger = logging.getLogger(__name__)

class TrackerBootstrap(object):

    def __init__(self, net, tracker=None):
        self.net = net
        
        if tracker is None:
            tracker = settings.get_option(net.name+'/tracker','http://tracker.openbittorrent.com/announce')
        
        self.use_tracker = settings.get_option(net.name+'/use_tracker',False)
        self.tracker = tracker
        self.interval = settings.get_option(net.name+'/tracker_interval',10*60)
        
        if self.use_tracker:
            logger.info('tracker use is enabled')
        
    def tracker_request(self):
        id = self.net.router.pm._self.id.bytes*2
        id = urllib2.quote(id[:20])
        hash = sha1(self.net.key).digest()
        hash = urllib2.quote(hash)
        
        url = self.tracker + '?info_hash=' + hash + '&port=%d&compact=1&peer_id=' % self.net.port \
            + id + '&uploaded=0&downloaded=0&left=100'
            
        return client.getPage(url)
        
    def run(self):
        if self.use_tracker:
            
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
                self.net.router.pm.try_register(addrs)
                reactor.callLater(self.interval, self.run)
                
            def do_error(err):
                logger.warning('tracker request failed: '+str(err))
                reactor.callLater(self.interval, self.run)
            
            logger.info('sending a request to tracker: %s' % self.tracker)
            d = self.tracker_request()
            d.addCallback(do_response)
            d.addErrback(do_error)
            
            
            
