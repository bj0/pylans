# Copyright (C) 2011  Brian Parma (execrable@gmail.com)
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
import util
from vpn.crypto import Crypter
from vpn.peers import PeerInfo

class SessionManager(object):

    KEY_XCHANGE = 30
    KEY_XCHANGE_ACK = 31

    def __init__(self, router):

        self.router = util.get_weakref_proxy(router)
        self.session_objs = {}
        self.session_map = {}


    def send(self, type, data, dest, *args, **kwargs):
        #data = self.encode(dest, data)

        self.router.send(type, data, dest, *args, **kwargs)

    def open(self, sid, session_key):
        obj = Crypter(session_key, callback=self.init_key_xc, args=(sid,))
        self.session_objs[sid] = obj

    def close(self, sid):
        del self.session_objs[sid]

    def encode(self, sid, data):
        if isinstance(sid, PeerInfo):
            sid = sid.id

        if sid not in self:
            print 'wtf',sid
            raise KeyError, "unknown session id: {0}".format(sid.encode('hex'))
        return self.session_objs[sid].encrypt(data)

    def decode(self, sid, data):
        if isinstance(sid, PeerInfo):
            sid = sid.id

        if sid not in self:
            raise KeyError, "unknown session id: {0}".format(sid.encode('hex'))
        return self.session_objs[sid].decrypt(data)

    def init_key_xc(self, obj, sid):
        logger.info('new key xchange initiated')
        #TODO prevent multiple key xc at the same time?
        mynonce = os.urandom(32)
        mac = hmac.new(self.router.network.key, mynonce, hashlib.sha256).digest()

        self.router.send(self.KEY_XCHANGE, mynonce+mac, sid)

    def handle_key_xc(self, type, packet, address, src_id):
        logger.info('got new key xchange packet')
        nonce, mac = packet[:32], packet[32:]

        # verify nonce
        if hmac.new(self.router.network.key, nonce, hashlib.sha256).digest() != mac:
            logger.critical("hmac verification failed on key xchange!")
        else:
            send_key_xc_ack(nonce, sid)

    def send_key_xc_ack(self, nonce, sid):
        logger.info('sending key xchange ack')
        mynonce = os.urandom(82)
        mac = hmac.new(self.router.network.key, nonce+mynonce, hashlib.sha256).digets()

        d = self.router.send(self.KEY_XCHANGE_ACK, nonce+mynonce+mac, sid, ack=True)
        d.addCallback(lambda *x: self.key_xc_complete(nonce+mynonce, sid))
        d.addErrback(lambda *x: self.key_xc_fail(sid))

    def handle_key_xc_ack(self, type, packet, address, src_id):
        logger.info('got key xchange ack')
        mynonce, nonce, mac = packet[:32], packet[32:64], packet[64:]

        # verify nonce
        if hmac.new(self.router.network.key, nonce, hashlib.sha256).digest() != mac:
            logger.critical('hmac verification failed on key xchange!')
        else:
            self.key_xc_complete(mynonce+nonce, src_id)

    def key_xc_complete(self, salt, sid):
        logger.info('new key xchange complete')
        session_key = hashlib.sha256(self.router.network.key+salt).digest()
        self.open(pid, session_key)

    def key_xc_fail(self, sid):
        logger.critical('key xchange failed!')
        #TODO re-try key xchange, or drop session??

    ### Container Functions
    def get(self, item, default=None):
        try:
            return self[item]
        except KeyError:
            return default

    def __contains__(self, item):
        return item in self.session_objs

    def __getitem__(self, item):
        return self.session_objs[item]

    def __len__(self):
        len(self.session_objs)