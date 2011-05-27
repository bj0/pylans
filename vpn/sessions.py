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
    def __init__(self, router):

        self.router = util.get_weakref_proxy(router)
        self.session_objs = {}
        self.session_map = {}


    def send(self, type, data, dest, *args, **kwargs):
        data = self.encode(dest, data)

        self.router.send(type, data, dest, *args, **kwargs)

    def open(self, sid, session_key):
        obj = Crypter(session_key)
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