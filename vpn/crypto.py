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

# encryption classes
from Crypto.Cipher import AES, Blowfish
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
import cPickle as pickle
import hashlib
import struct
import hmac
import os

try:
    from pycryptopp.cipher import aes
    from pycryptopp.hash import sha256
except ImportError:
    aes = None

class AESCrypterPP(object):
    def __init__(self, key, mode=None): #pycryptopp uses CTR mode
        self.key = hashlib.md5(key).digest()
        self.BLOCK_SIZE = 16
        self.iv = 0
        self.iv_sz = 16 # IV size must be 16 bytes
        self.iv_salt = os.urandom(8)    # Added salt, to make it resistant against stream cipher attacks (repeated IV+key = very bad)
        
    def encrypt(self, string):
        self.iv += 1
        iv = self.iv_salt+struct.pack('>Q', self.iv)
        return aes.AES(self.key, iv=iv).process(string) + iv
        
    def decrypt(self, string):
        iv = string[-self.iv_sz:]
        return aes.AES(self.key, iv=iv).process(string[:-self.iv_sz])
        
    def _reset(self):
        # re-salt & reset counter
        self.iv_salt = os.urandom(8)
        self.iv = 0

class AESCrypterPP2(object):
    def __init__(self, key, mode=None): #pycryptopp uses CTR mode
        self.key = hashlib.md5(key).digest()
        self.BLOCK_SIZE = 16
        self.pos_q = 0
        self.pos_r = 0
        self.pos_sz = 17 
        self.iv_salt = os.urandom(8)
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

class AESCrypterPP3(object):
    def __init__(self, key, mode=None): #pycryptopp uses CTR mode
        self.key = hashlib.md5(key).digest()
        self.hmac = hashlib.sha256
        self.hmac_key = self.hmac(key).digest()
        self.SIG_SIZE = self.hmac().digest_size
        self.BLOCK_SIZE = 16
        self.pos_q = 0
        self.pos_r = 0
        self.pos_sz = 17 
        self.iv_salt = os.urandom(8)
        self.obj = aes.AES(self.key, iv=self.iv_salt+'\x00'*8)
        
    def encrypt(self, string):
        l = len(string)
        iv = chr(self.pos_r) + self.iv_salt + struct.pack('>Q', self.pos_q)

        self.pos_q += (self.pos_r + l) // 16
        self.pos_r = (self.pos_r + l) % 16 
        data = self.obj.process(string) + iv
        sig = hmac.new(self.hmac_key, data, self.hmac).digest()
        return data + sig
        
    def decrypt(self, string):
        string, sig = string[:-self.SIG_SIZE], string[-self.SIG_SIZE:]
        if hmac.new(self.hmac_key, string, self.hmac).digest() != sig:
            raise AuthenticationError("message authentication failed")
        r, iv = ord(string[-self.pos_sz]), string[-self.pos_sz+1:]
        e = aes.AES(self.key, iv=iv)
        e.process('\x00'*r)
        return e.process(string[:-self.pos_sz])

class AESCrypter(object):
    def __init__(self, key, mode=AES.MODE_CBC):
        self.key = hashlib.md5(key).digest()
        self.mode = mode
        self.BLOCK_SIZE = AES.block_size
        self.iv_sz = 16
        iv = os.urandom(16)
        self.obj = AES.new(self.key, self.mode, iv)
        
    def encrypt(self, string):
        pad = self.BLOCK_SIZE - len(string) % self.BLOCK_SIZE
        string = string + pad * chr(pad)
        iv = self.obj.IV
        
        return self.obj.encrypt(string) + iv
        
    def decrypt(self, string):
        iv = string[-self.iv_sz:]
        string = AES.new(self.key, self.mode, iv).decrypt(string[:-self.iv_sz])
        return string[:-ord(string[-1])]

class AESCrypter2(object):
    def __init__(self, key, mode=AES.MODE_CBC):
        self.key = hashlib.md5(key).digest()
        self.mode = mode
        self.BLOCK_SIZE = AES.block_size
        self.iv_sz = 16/2
        self.iv = 0
        
    def encrypt(self, string):
        pad = self.BLOCK_SIZE - len(string) % self.BLOCK_SIZE
        string = string + pad * chr(pad)

        self.iv += 1
        iv = struct.pack('>Q', self.iv)        
        return AES.new(self.key, self.mode, '\x00'*8+iv).encrypt(string) + iv
        
    def decrypt(self, string):
        iv = string[-self.iv_sz:]
        string = AES.new(self.key, self.mode, '\x00'*8+iv).decrypt(string[:-self.iv_sz])
        return string[:-ord(string[-1])]

class BFCrypter(object):
    def __init__(self, key, mode=Blowfish.MODE_ECB):
        # hash key to Blowfish's max key size 448 bits
        key = hashlib.sha512(key).digest()[:56]
        self._obj = Blowfish.new(key, mode)
        self.BLOCK_SIZE = self._obj.block_size

    def encrypt(self, string):
        pad = self.BLOCK_SIZE - len(string) % self.BLOCK_SIZE
        string = string + pad * chr(pad)
        return self._obj.encrypt(string)
    
    def decrypt(self, string):
        string = self._obj.decrypt(string)
        return string[:-ord(string[-1])]

# testing different encryption wayz
#Crypter = BFCrypter
#Crypter = AESCrypterPP
Crypter = AESCrypterPP2
#Crypter = AESCrypterPP3
#Crypter = AESCrypter

class RSAxe(object):
    def __init__(self, key=None):
        self._key = key

    def get_pubkey(self):
        return self._key.publickey()
        
    def get_fullkey(self):
        return self._key
        
    def gen_key(self, bits=1024):
        self._key = RSA.generate(bits, os.urandom)
        
    def encrypt(self, string):
        return pickle.dumps(self._key.encrypt(string, 0), -1)
        
    def decrypt(self, string):
        return self._key.decrypt(pickle.loads(string))
    

# PyCrypto-based authenticated symetric encryption
# example from an activestate post...
#import cPickle as pickle

class AuthenticationError(Exception): pass

class Crypticle(object):
    """Authenticated encryption class
    
    Encryption algorithm: AES-CBC
    Signing algorithm: HMAC-SHA256
    """

    PICKLE_PAD = "pickle::"
    AES_BLOCK_SIZE = 16
    SIG_SIZE = hashlib.sha256().digest_size

    def __init__(self, key_string, key_size=192):
        self.keys = self.extract_keys(key_string, key_size)
        self.key_size = key_size

    @classmethod
    def generate_key_string(cls, passwd=None, key_size=192):
        if passwd is None:
            key = os.urandom(key_size / 8 + cls.SIG_SIZE)
        else:
            size = key_size / 8 + cls.SIG_SIZE
            key = hashlib.sha256(passwd).digest()
            key = key * ((size - 1) // len(key) + 1)
            key = key[:size]
        return key.encode("base64").replace("\n", "")

    @classmethod
    def extract_keys(cls, key_string, key_size):
        key = key_string.decode("base64")
        assert len(key) == key_size / 8 + cls.SIG_SIZE, "invalid key"
        return key[:-cls.SIG_SIZE], key[-cls.SIG_SIZE:]

    def encrypt(self, data):
        """encrypt data with AES-CBC and sign it with HMAC-SHA256"""
        aes_key, hmac_key = self.keys
        pad = self.AES_BLOCK_SIZE - len(data) % self.AES_BLOCK_SIZE
        data = data + pad * chr(pad)
        iv_bytes = os.urandom(self.AES_BLOCK_SIZE)
        cypher = AES.new(aes_key, AES.MODE_CBC, iv_bytes)
        data = iv_bytes + cypher.encrypt(data)
        sig = hmac.new(hmac_key, data, hashlib.sha256).digest()
        return data + sig

    def decrypt(self, data):
        """verify HMAC-SHA256 signature and decrypt data with AES-CBC"""
        aes_key, hmac_key = self.keys
        sig = data[-self.SIG_SIZE:]
        data = data[:-self.SIG_SIZE]
        if hmac.new(hmac_key, data, hashlib.sha256).digest() != sig:
            raise AuthenticationError("message authentication failed")
        iv_bytes = data[:self.AES_BLOCK_SIZE]
        data = data[self.AES_BLOCK_SIZE:]
        cypher = AES.new(aes_key, AES.MODE_CBC, iv_bytes)
        data = cypher.decrypt(data)
        return data[:-ord(data[-1])]

    def dumps(self, obj, pickler=pickle):
        """pickle and encrypt a python object"""
        return self.encrypt(self.PICKLE_PAD + pickler.dumps(obj))

    def loads(self, data, pickler=pickle):
        """decrypt and unpickle a python object"""
        data = self.decrypt(data)
        # simple integrity check to verify that we got meaningful data
        assert data.startswith(self.PICKLE_PAD), "unexpected header"
        return pickler.loads(data[len(self.PICKLE_PAD):])


if __name__ == "__main__":
    # usage example
#    key = Crypticle.generate_key_string()
#    data = {"dict": "full", "of": "secrets"}
#    crypt = Crypticle(key)
#    safe = crypt.dumps(data)
#    assert data == crypt.loads(safe)
#    print "encrypted data:"
#    print safe.encode("base64")


    # test some speeeeeeeds
    key16 = os.urandom(16)
    key56 = os.urandom(56)

    data = os.urandom(1023)
    
    #
    e = AESCrypterPP(key16)
    pd = []
    print "Testing speed AESCrypterPP"
    from time import time
    t1 = time()
    n = 0
    enc = e.encrypt # dot reference lookups are costly
    ap = pd.append 
    lchr = chr # local function lookups are faster than global function lookups
    while True:
        for i in xrange(200):
#            pd.append(e.encrypt(chr(i)+data))
            ap(enc(lchr(i)+data))
#            ap(enc(data))
        n += 200
        t2 = time()
        if t2 - t1 > 5:
            break
    print "%d MB encrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    t1 = time()
    n = 0
    for blk in pd:
        e.decrypt(blk)
    n = len(pd)
    t2 = time()
    print "%d MB decrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    print
    
    #
    e = AESCrypterPP2(key16)
    pd = []
    print "Testing speed AESCrypterPP2"
    from time import time
    t1 = time()
    n = 0
    enc = e.encrypt # dot reference lookups are costly
    ap = pd.append 
    lchr = chr # local function lookups are faster than global function lookups
    while True:
        for i in xrange(200):
#            pd.append(e.encrypt(chr(i)+data))
            ap(enc(lchr(i)+data))
#            ap(enc(data))
        n += 200
        t2 = time()
        if t2 - t1 > 5:
            break
    print "%d MB encrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    t1 = time()
    n = 0
    for blk in pd:
        e.decrypt(blk)
    n = len(pd)
    t2 = time()
    print "%d MB decrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    print
    
    #
    e = AESCrypterPP3(key16)
    pd = []
    print "Testing speed AESCrypterPP3"
    from time import time
    t1 = time()
    n = 0
    enc = e.encrypt # dot reference lookups are costly
    ap = pd.append 
    lchr = chr # local function lookups are faster than global function lookups
    while True:
        for i in xrange(200):
#            pd.append(e.encrypt(chr(i)+data))
            ap(enc(lchr(i)+data))
        n += 200
        t2 = time()
        if t2 - t1 > 5:
            break
    print "%d MB encrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    t1 = time()
    n = 0
    for blk in pd:
        e.decrypt(blk)
    n = len(pd)
    t2 = time()
    print "%d MB decrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    print
    
    #
    e = AESCrypter(key16)
    pd = []
    print "Testing speed AESCrypter"
    from time import time
    t1 = time()
    n = 0
    enc = e.encrypt # dot reference lookups are costly
    ap = pd.append 
    lchr = chr # local function lookups are faster than global function lookups
    while True:
        for i in xrange(200):
#            pd.append(e.encrypt(chr(i)+data))
            ap(enc(lchr(i)+data))
        n += 200
        t2 = time()
        if t2 - t1 > 5:
            break
    print "%d MB encrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    t1 = time()
    n = 0
    for blk in pd:
        e.decrypt(blk)
    n = len(pd)
    t2 = time()
    print "%d MB decrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    print    

    #
    e = AESCrypter2(key16)
    pd = []
    print "Testing speed AESCrypter2"
    from time import time
    t1 = time()
    n = 0
    enc = e.encrypt # dot reference lookups are costly
    ap = pd.append 
    lchr = chr # local function lookups are faster than global function lookups
    while True:
        for i in xrange(200):
#            pd.append(e.encrypt(chr(i)+data))
            ap(enc(lchr(i)+data))
        n += 200
        t2 = time()
        if t2 - t1 > 5:
            break
    print "%d MB encrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    t1 = time()
    n = 0
    for blk in pd:
        e.decrypt(blk)
    n = len(pd)
    t2 = time()
    print "%d MB decrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    print    

    #
    e = BFCrypter(key56)
    pd = []
    print "Testing speed BFCrypter"
    from time import time
    t1 = time()
    n = 0
    enc = e.encrypt # dot reference lookups are costly
    ap = pd.append 
    lchr = chr # local function lookups are faster than global function lookups
    while True:
        for i in xrange(200):
#            pd.append(e.encrypt(chr(i)+data))
            ap(enc(lchr(i)+data))
        n += 200
        t2 = time()
        if t2 - t1 > 5:
            break
    print "%d MB encrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    t1 = time()
    n = 0
    for blk in pd:
        e.decrypt(blk)
    n = len(pd)
    t2 = time()
    print "%d MB decrypted in %0.1f seconds: %0.1f MB/s" % (n/1024., t2-t1, n/(t2-t1)/1024. )
    print    


