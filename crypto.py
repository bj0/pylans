#!/usr/bin/python

# encryption classes

from Crypto.Cipher import Blowfish

class Crypter(object):
    def __init__(self, key, mode=Blowfish.MODE_ECB):
        self._obj = Blowfish.new(key, mode)
        self.BLOCK_SIZE = self._obj.block_size

    def encrypt(self, string):
        pad = self.BLOCK_SIZE - len(string) % self.BLOCK_SIZE
        string = string + pad*chr(pad)
        return self._obj.encrypt(string)
    
    def decrypt(self, string):
        string = self._obj.decrypt(string)
        return string[:-ord(string[-1])]



# PyCrypto-based authenticated symetric encryption
import cPickle as pickle
import hashlib
import hmac
import os
from Crypto.Cipher import AES

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
            key = key*((size-1)//len(key)+1)
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
    
