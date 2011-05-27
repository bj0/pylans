from util import *
from util import event
from twisted.internet import reactor

def emit_async(*x):
    reactor.callLater(0, event.emit, *x)
