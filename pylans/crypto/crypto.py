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
# crypto.py
# TODO: make pycrypto and pycryptopp consistent wrt CTR counters
# TODO: cython?

# import python modules
import cPickle as pickle
import hashlib
import struct
from binascii import hexlify, unhexlify
import hmac
import os
import logging

logger = logging.getLogger(__name__)

# encryption classes
try:
    from Crypto.Cipher import AES, Blowfish
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import RSA
except ImportError:
    AES = None

try:
    from pycryptopp.cipher import aes
    from pycryptopp.hash import sha256
except ImportError:
    aes = None
    if AES is None:
        logger.critical('No encryption modules found, exiting...')
        exit(1)
    else:
        logger.warning('No pycryptopp found, trying to use pycrypto...')



## PyCrypto's CTR mode requires a custom counter
class _Counter(object):
    def __init__(self, n=0, maxn=0xEFFFFFFFFFFFFFFF, salt=None, iv=None):
        salt = salt or os.urandom(8)
        if iv is None:
            self.n = n
            self.salt = salt
        else:
            self.n = struct.unpack('<Q',iv[8:])[0]
            self.salt = iv[:8]
        self.maxn = maxn

    def __call__(self):
        iv = struct.pack('<Q',self.n) + self.salt
        self.inc()
        return iv

    def inc(self):
        self.n += 1
        if self.n == self.maxn:
            self.n = 0
            self.salt = os.urandom(8)

    def iv(self):
        return struct.pack('<Q',self.n) + self.salt

class _BCounter(object):
    def __init__(self, n=0, maxn=0xEFFFFFFFFFFFFFFF, salt=os.urandom(8), iv=None):
        if iv is None:
            self._iv = bytearray(struct.pack('<Q',n) + salt)
        else:
            self._iv = bytearray(iv)

    def __call__(self):
        iv = bytes(self._iv)
        self.inc()
        return iv

    def iv(self):
        return str(self._iv)

    def inc(self):
        j = 0
        while self._iv[j] == 0xff:
            if j == 15: # reset at  2^15
                self._iv = bytearray('\x00'*8 + os.urandom(8))
            else:
                j += 1
        self._iv[j] += 1

# testing cython stuff
try:
    from cutil import Counter, BCounter
    from cutil import AESCrypterPP2
    print 'using cython'
except ImportError,e:
    logger.debug('could not import cython counters, using python ones')
    print e
    Counter = _Counter
    BCounter = _BCounter

    # test pycryptopp, using one object for all encryptions.  need to keep track of count/position
    # faster encryption, slower decryption
    class AESCrypterPP2(object):
        '''aes in ctr mode with one object for all encrypts, new object for decrypts'''
        block_size = 16
        key_size = 16
        def __init__(self, key): #pycryptopp uses CTR mode
            self.key = hashlib.md5(key).digest()
            self.pos_q = 0
            self.pos_r = 0
            self.pos_sz = 17
            self.iv_salt = os.urandom(8) # Added salt, to make it resistant against stream cipher attacks (repeated IV+key = very bad)
            self.obj = aes.AES(self.key, iv=self.iv_salt+'\x00'*8)

        def encrypt(self, string):
            # need to reset before 64-bit counter overflows
            if self.pos_q > 0xEFFFFFFFFFFFFFFF:
                self._reset()

            l = len(string)
            iv = chr(self.pos_r) + self.iv_salt + struct.pack('>Q', self.pos_q)

            # keep track of pos
            self.pos_q += (self.pos_r + l) // 16
            self.pos_r = (self.pos_r + l) % 16
            return self.obj.process(string) + iv

        def decrypt(self, string):
            # create a CTR obj with the right iv, then process stream to starting spot
            r, iv = ord(string[-self.pos_sz]), string[-self.pos_sz+1:]
            e = aes.AES(self.key, iv=iv)
            e.process('\x00'*r)
            return e.process(string[:-self.pos_sz])

        def _reset(self):
            # re-salt & reset counter
            self.pos_q = 0
            self.pos_r = 0
            self.iv_salt = os.urandom(8)
            self.obj = aes.AES(self.key, iv=self.iv_salt+'\x00'*8)


def hmac_authentication(auth_f, cauth_f):
    '''
    Class decorator to add hmac authentication.
        auth_f - encoding function to authenticate (takes and returns string)
        cauth_f - decoding function to check authentication (takes and returns string)
    '''
    def wrapper(cls):
        init = getattr(cls, '__init__')
        enc = getattr(cls, auth_f)
        dec = getattr(cls, cauth_f)
        def new_init(self, key):
            init(self, key)
            self.hmac = hashlib.md5
            self.hmac_key = self.hmac(self.key).digest() # probably not secure
            self.sig_size = self.hmac().digest_size

        def auth(self, data):
            data = enc(self, data)
            sig = hmac.new(self.hmac_key, data, self.hmac).digest()
            return data + sig

        def check_auth(self, data):
            data, sig = data[:-self.sig_size], data[-self.sig_size:]
            if hmac.new(self.hmac_key, data, self.hmac).digest() != sig:
                raise AuthenticationError("message authentication failed")
            return dec(self, data)

        setattr(cls, '__init__', new_init)
        setattr(cls, auth_f, auth)
        setattr(cls, cauth_f, check_auth)
        return cls
    return wrapper

# a little faster than above hmac
@hmac_authentication('encrypt','decrypt')
class AESCrypterPP4(AESCrypterPP2):
    '''aes in ctr mode with one object for all encrypts, new object for decrypts. hmac authentican, abstracted'''
    pass
#    __metaclass__ = HMACAuthentication


#print AESCrypterPP2
# test pycrypto, using one object for all encryptions.  need to keep track of count/position
# very slow (because it relies on python counter instead of using its own (fixed in newer pycrypto))
class AESCrypter3(object):
    '''aes in ctr mode with one object for all encrypts, new object for decrypts'''
    block_size = 16
    key_size = 16
    def __init__(self, key):
        self.key = hashlib.md5(key).digest()
        self.counter = Counter()
        self.pos_sz = 16
        self.obj = AES.new(self.key, AES.MODE_CTR, counter=self.counter)

    def encrypt(self, string):
        iv = self.counter.iv()
        pad = self.block_size - len(string) % self.block_size
        string = string + pad * chr(pad)

        return self.obj.encrypt(string) + iv

    def decrypt(self, string):
        iv = string[-self.pos_sz:]
        e = AES.new(self.key, AES.MODE_CTR, counter=Counter(iv=iv))
        string = e.decrypt(string[:-self.pos_sz])
        return string[:-ord(string[-1])]


# test pycryptopp, using one object for all encryptions.  need to keep track of count/position
# faster encryption, slower decryption
class _Crypter0(object):
    '''aes 128 (pycryptopp) in ctr mode'''
    block_size = 16
    key_size = 16
    def __init__(self, key, can_rollover=False, callback=None, args=None): #pycryptopp uses CTR mode
        assert len(key) == self.key_size, "Invalid key size"
        self.key = key
        self.can_rollover = can_rollover
        self.callback = callback
        self.args = args or ()
        self.pos_q = 0
        self.max_q = int(hexlify('\xFF'*(self.block_size-2)), 16)
        self.pos_r = 0
        self.pos_sz = self.block_size + 1
        self.__fmt = '%%0.%dx'%(self.block_size*2)
        self.obj = aes.AES(self.key, iv='\x00'*self.block_size)

    def encrypt(self, string):
        # need to reset before 64-bit counter overflows
        if self.pos_q > self.max_q:
            self._reset()

        l = len(string)
        iv = chr(self.pos_r) + unhexlify(self.__fmt%self.pos_q) #seems like fastest

        # keep track of pos
        self.pos_q += (self.pos_r + l) // self.block_size
        self.pos_r = (self.pos_r + l) % self.block_size
        return self.obj.process(string) + iv

    def decrypt(self, string):
        # create a CTR obj with the right iv, then process stream to starting spot
        r, iv = ord(string[-self.pos_sz]), string[-self.pos_sz+1:]

        e = aes.AES(self.key, iv=iv)
        e.process('\x00'*r)
        return e.process(string[:-self.pos_sz])

    def _reset(self):
        # re-salt & reset counter
        if self.callback is None:
            if self.can_rollover:
                self.pos_q = 0
                self.pos_r = 0
                self.obj = aes.AES(self.key, iv='\x00'*self.block_size)
            else:
                raise ValueError, 'AES counter rolled over'

        else:
            # so we don't keep calling this function over and over
            self.max_q = self.max_q << 1
            self.callback(self, *args)

class _Crypter1(_Crypter0):
    '''aes 256 (pycryptopp) in ctr mode'''
    key_size = 32
    block_size = 16


if aes is not None:
    Crypter = _Crypter1
else:
    raise ImportError, 'missing pycryptopp'
    #Crypter = AESCrypter3


if __name__ == "__main__":
    # test some speeeeeeeds
    key = os.urandom(56)

    data = os.urandom(1023)
    tmax = 5

    from time import time
    lchr = chr # local function lookups are faster than global function lookups
#    clses = [AESCrypterPP, AESCrypterPP2, AESCrypterPP3, AESCrypterPP4,
#                AESCrypter, AESCrypter2, AESCrypter3, BFCrypter]
    clses = [_Crypter0,_Crypter1]
    for cls in clses:
        e = cls(key[:cls.key_size])
        pd = []
        print "Testing speed {0} ({1})".format(e.__class__.__name__,e.__class__.__doc__)
        t1 = time()
        n = 0
        enc = e.encrypt # dot reference lookups are costly
        ap = pd.append
        while True:
            for i in xrange(200):
                ap(enc(lchr(i)+data))
#                ap(enc(data))
            n += 200
            t2 = time()
            if t2 - t1 > tmax:
                break
        print "%d MB encrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
        t1 = time()

        dec = e.decrypt
        for blk in pd:
            dec(blk)
        #map(dec, pd) - slower
        n = len(pd)
        t2 = time()
        print "%d MB decrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
        print
