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
from Crypto.PublicKey import RSA
import cPickle as pickle
import hashlib
import hmac
import os

class Crypter(object):
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
    key = Crypticle.generate_key_string()
    data = {"dict": "full", "of": "secrets"}
    crypt = Crypticle(key)
    safe = crypt.dumps(data)
    assert data == crypt.loads(safe)
    print "encrypted data:"
    print safe.encode("base64")



#if __name__ == '__main__':
#    ec = Encryptor('tehKey')
#    dat = ec.encrypt('encrypt teh stuffs')
#    print dat
#    print ec.decrypt(dat) 
    
