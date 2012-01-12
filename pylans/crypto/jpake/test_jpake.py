
import unittest
from jpake import JPAKE, params_80, params_112, params_128, \
     DuplicateSignerID, SignerIDMustBeASCII
from binascii import hexlify
from hashlib import sha256
try:
    import json
    json.__version__ # this is really here to hush pyflakes, which gets
                     # confused by this import-and-alternate pattern
except ImportError:
    import simplejson as json
    json.__version__

class Basic(unittest.TestCase):
    def test_success(self):
        pw = "password"
        jA,jB = JPAKE(pw, signerid="Alice"), JPAKE(pw, signerid="Bob")
        m1A,m1B = jA.one(), jB.one()
        m2A,m2B = jA.two(m1B), jB.two(m1A)
        kA,kB = jA.three(m2B), jB.three(m2A)
        self.failUnlessEqual(hexlify(kA), hexlify(kB))
        self.failUnlessEqual(len(kA), len(sha256().digest()))

    def test_failure(self):
        pw = "password"
        jA,jB = JPAKE(pw), JPAKE("passwerd")
        m1A,m1B = jA.one(), jB.one()
        m2A,m2B = jA.two(m1B), jB.two(m1A)
        kA,kB = jA.three(m2B), jB.three(m2A)
        self.failIfEqual(hexlify(kA), hexlify(kB))
        self.failUnlessEqual(len(kA), len(sha256().digest()))
        self.failUnlessEqual(len(kB), len(sha256().digest()))

class Parameters(unittest.TestCase):
    def do_tests(self, params):
        pw = "password"
        jA,jB = JPAKE(pw, params=params), JPAKE(pw, params=params)
        m1A,m1B = jA.one(), jB.one()
        m2A,m2B = jA.two(m1B), jB.two(m1A)
        kA,kB = jA.three(m2B), jB.three(m2A)
        self.failUnlessEqual(hexlify(kA), hexlify(kB))
        self.failUnlessEqual(len(kA), len(sha256().digest()))

        jA,jB = JPAKE(pw, params=params), JPAKE("passwerd", params=params)
        m1A,m1B = jA.one(), jB.one()
        m2A,m2B = jA.two(m1B), jB.two(m1A)
        kA,kB = jA.three(m2B), jB.three(m2A)
        self.failIfEqual(hexlify(kA), hexlify(kB))
        self.failUnlessEqual(len(kA), len(sha256().digest()))
        self.failUnlessEqual(len(kB), len(sha256().digest()))

    def test_params(self):
        for params in [params_80, params_112, params_128]:
            self.do_tests(params)

    def test_default_is_80(self):
        pw = "password"
        jA,jB = JPAKE(pw, params=params_80), JPAKE(pw)
        m1A,m1B = jA.one(), jB.one()
        m2A,m2B = jA.two(m1B), jB.two(m1A)
        kA,kB = jA.three(m2B), jB.three(m2A)
        self.failUnlessEqual(hexlify(kA), hexlify(kB))
        self.failUnlessEqual(len(kA), len(sha256().digest()))

class SignerID(unittest.TestCase):
    def test_signerid(self):
        pw = "password"
        jA,jB = JPAKE(pw, signerid="a"), JPAKE(pw, signerid="b")
        m1A,m1B = jA.one(), jB.one()
        m2A,m2B = jA.two(m1B), jB.two(m1A)
        kA,kB = jA.three(m2B), jB.three(m2A)
        self.failUnlessEqual(hexlify(kA), hexlify(kB))
        self.failUnlessEqual(len(kA), len(sha256().digest()))

        jA,jB = JPAKE(pw, signerid="a"), JPAKE("passwerd", signerid="b")
        m1A,m1B = jA.one(), jB.one()
        m2A,m2B = jA.two(m1B), jB.two(m1A)
        kA,kB = jA.three(m2B), jB.three(m2A)
        self.failIfEqual(hexlify(kA), hexlify(kB))
        self.failUnlessEqual(len(kA), len(sha256().digest()))
        self.failUnlessEqual(len(kB), len(sha256().digest()))

        jA,jB = JPAKE(pw, signerid="same"), JPAKE(pw, signerid="same")
        m1A,m1B = jA.one(), jB.one()
        self.failUnlessRaises(DuplicateSignerID, jA.two, m1B)
        self.failUnlessRaises(DuplicateSignerID, jB.two, m1A)

    def test_ascii(self):
        self.failUnlessRaises(SignerIDMustBeASCII,
                              JPAKE, "pw", signerid="not-ascii\xff")
        jA,jB = JPAKE("pw", signerid="Alice"), JPAKE("pw", signerid="Bob")
        m1A = jA.one()
        m1Ap = jA.pack_one(m1A)
        # now doctor m1Ap to contain non-ascii, to exercise the check in
        # unpack_one. We happen to know that the signerid is stored at the
        # end of the packed structure
        assert m1Ap[-5:] == "Alice"
        m1Ap_bad = m1Ap[:-5] + "Alic\xff"
        self.failUnlessRaises(SignerIDMustBeASCII,
                              jA.unpack_one, m1Ap_bad)
        # same for message two
        m2A = jA.two(jB.one())
        m2Ap = jA.pack_two(m2A)
        assert m2Ap[-5:] == "Alice"
        m2Ap_bad = m2Ap[:-5] + "Alic\xff"
        self.failUnlessRaises(SignerIDMustBeASCII,
                              jA.unpack_two, m2Ap_bad)

class PRNG:
    # this returns a callable which, when invoked with an integer N, will
    # return N pseudorandom bytes.
    def __init__(self, seed):
        self.generator = self.block_generator(seed)

    def __call__(self, numbytes):
        return "".join([self.generator.next() for i in range(numbytes)])

    def block_generator(self, seed):
        counter = 0
        while True:
            for byte in sha256("prng-%d-%s" % (counter, seed)).digest():
                yield byte
            counter += 1

class OtherEntropy(unittest.TestCase):
    def test_entropy(self):
        entropy = PRNG("seed")
        pw = "password"
        jA,jB = JPAKE(pw, entropy=entropy), JPAKE(pw, entropy=entropy)
        m1A1,m1B1 = jA.one(), jB.one()
        m2A1,m2B1 = jA.two(m1B1), jB.two(m1A1)
        kA1,kB1 = jA.three(m2B1), jB.three(m2A1)
        self.failUnlessEqual(hexlify(kA1), hexlify(kB1))

        # run it again with the same entropy stream: all messages should be
        # identical
        entropy = PRNG("seed")
        jA,jB = JPAKE(pw, entropy=entropy), JPAKE(pw, entropy=entropy)
        m1A2,m1B2 = jA.one(), jB.one()
        m2A2,m2B2 = jA.two(m1B2), jB.two(m1A2)
        kA2,kB2 = jA.three(m2B2), jB.three(m2A2)
        self.failUnlessEqual(hexlify(kA2), hexlify(kB2))

        self.failUnlessEqual(m1A1, m1A2)
        self.failUnlessEqual(m1B1, m1B2)
        self.failUnlessEqual(m2A1, m2A2)
        self.failUnlessEqual(m2B1, m2B2)
        self.failUnlessEqual(kA1, kA2)
        self.failUnlessEqual(kB1, kB2)

class Serialize(unittest.TestCase):
    def replace(self, orig):
        data = json.dumps(orig.to_json())
        return JPAKE.from_json(json.loads(data))

    def test_serialize(self):
        pw = "password"
        jA,jB = JPAKE(pw, signerid="Alice"), JPAKE(pw, signerid="Bob")
        jA = self.replace(jA)
        m1A,m1B = jA.one(), jB.one()
        jA = self.replace(jA)
        m2A,m2B = jA.two(m1B), jB.two(m1A)
        jA = self.replace(jA)
        kA,kB = jA.three(m2B), jB.three(m2A)
        self.failUnlessEqual(hexlify(kA), hexlify(kB))
        self.failUnlessEqual(len(kA), len(sha256().digest()))

class Packed(unittest.TestCase):
    def test_pack(self):
        pw = "password"
        jA,jB = JPAKE(pw, signerid="Alice"), JPAKE(pw, signerid="Bob")
        m1A,m1B = jA.one(), jB.one()
        m1Ap = jA.pack_one(m1A)
        #print "m1:", len(json.dumps(m1A)), len(m1Ap)
        m2A,m2B = jA.two(m1B), jB.two(jB.unpack_one(m1Ap))
        m2Ap = jA.pack_two(m2A)
        #print "m2:", len(json.dumps(m2A)), len(m2Ap)
        kA,kB = jA.three(m2B), jB.three(jB.unpack_two(m2Ap))
        self.failUnlessEqual(hexlify(kA), hexlify(kB))
        self.failUnlessEqual(len(kA), len(sha256().digest()))

if __name__ == '__main__':
    unittest.main()

