from __future__ import absolute_import
from twisted.internet import reactor, utils, defer
from twisted.internet.interfaces import IReadDescriptor
from twisted.internet.threads import deferToThread
from zope.interface import implements
import logging
from . import util

logger = logging.getLogger(__name__)


class TunTapUnsupported:
    def __init__(*x,**y):
        raise OSError, "cannot use this device on this platform"

import platform
if platform.system() == 'Linux':
    logger.info('Linux detected, using TapTunLinux')
    from .linux import TunTapLinux

    class TunTapWindows(TunTapUnsupported): pass

elif platform.system() == 'Windows':
    logger.info('Windows detected, using TapTunWindows')
    from .windows import TunTapWindows

    class TunTapLinux(TunTapUnsupported): pass

else:
    raise OSError, "Unsupported platform for tuntap"


class TwistedTTL(TunTapLinux):
    '''
        Class for using the tun/tap device in twisted.
    '''

    # so it can be used in twisted's main loop
    implements(IReadDescriptor)

    def __init__(self, callback, **kwargs):
        '''
            initialize tun/tap device.

            callback(data) - function that gets called with data when something is
            read on the tun/tap wire.
        '''
        self.callback = callback
        super(TwistedTTL, self).__init__(**kwargs)

    def start(self):
        '''Start monitoring tun/tap for input'''
        # add to twisted mainloop
        reactor.addReader(self)
        logger.info('linux tun/tap started')

    def stop(self):
        '''Stop monitoring tun/tap for input'''
        reactor.removeReader(self)
        logger.info('linux tun/tap stopped')

    def _shell(self, cmd):
        '''function for calling something through the shell'''
        return utils.getProcessValue(cmd[0],cmd[1:])

    @defer.inlineCallbacks
    def up(self):
        '''bring up interface'''
        ret = yield self._shell(('/sbin/ip','link','set',self.ifname,'up'))
        if ret != 0:
            raise Exception()

    @defer.inlineCallbacks
    def down(self):
        '''bring down interface'''
        ret = yield self._shell(('/sbin/ip','link','set',self.ifname,'down'))
        if ret != 0:
            raise Exception()


    @defer.inlineCallbacks
    def configure_iface(self, **options):

        logger.info('configuring interface {1} to: {0}'
                                    , options, self.ifname)
        def response(retval):
            if retval != 0:
                logger.error('error configuring interface {1} to: {0}'
                                    ,options, self.ifname)
                raise Exception('retval={0}'.format(retval))

        # check for spurious args
        err = [arg for arg in options.keys()
                            if arg not in ['addr','mtu','hwaddr']]
        if len(err) > 0:
            logger.error('configure_iface passed unrecognized arguments: {0}'
                    , err)

        if 'addr' in options:
            addr = options['addr']
            if '/' not in addr:
                addr = addr+'/32'

            ret = yield self._shell(
                        ('/sbin/ip','addr','add',addr,'dev',self.ifname))
            response(ret)

        if 'mtu' in options:
            mtu = options['mtu']
            self.set_mtu(mtu)

        if 'hwaddr' in options:
            hwaddr = options['hwaddr']

            ret = yield self._shell(
                ('/sbin/ip','link','set','dev',self.ifname,'address',hwaddr))
            response(ret)



    def doRead(self):
        '''
            New data is coming in on the tun/tap 'wire'.  Called by twisted.
        '''
        data = self.read()
        self.callback(data)

    def doWrite(self, data):
        '''
            Write some data out to the tun/tap 'wire'.
        '''
#        try:
        self.write(data)
#        except:
#            import traceback
#            traceback.print_exc()
#            logger.warning('Got Exception trying to os.write()\nself.f: {0}\ndata: {1} ({2})',
#                        self.f, data.encode('hex'), len(data))

    def fileno(self):
        '''Return the file identifier from os.open.  Required for twisted to
        select() our stream.'''
        return self._f

    def logPrefix(self):
        '''Required but not used?'''
        return '.>'

    def connectionLost(self, reason):
        logger.warning('connectionLost called on tuntap')
        self.stop()





class TwistedTTW(TunTapWindows):
    '''
        Class for using the tun/tap device in twisted.

        In windows, we can't have the file descriptor, so twisted can't use it
        in select().  Instead, we have to create a thread that polls the device
        and returns data when it's available.
    '''
    def __init__(self, callback, **kwargs):
        self.callback = callback
        self._running = False
        super(TwistedTTW, self).__init__(**kwargs)

    def start(self):
        self._running = True
        self.run()
        logger.info('windows tun/tap started')

    def stop(self):
        self._running = False
        logger.info('windows tun/tap stopped')

    @util.threaded
    def run(self):
        IPV4_HIGH = 0x08
        IPV4_LOW = 0x00
        IPV4_UDP = 17
        while self._running:
            data = self.read()
            if not data:
                continue
            if data[12] == IPV4_HIGH \
                    and data[13] == IPV4_LOW \
                    and data[14+9] == IPV4_UDP:
                logger.warning('IPV4 udp: {0}'
                                    , util.decode_ip(data[26:30]))

            reactor.callFromThread(self.callback, data)


    def _shell(self, cmd):
        return utils.getProcessOutputAndValue(cmd[0],cmd[1:])

    @defer.inlineCallbacks
    def configure_iface(self, **options):

        logger.info('configuring interface {1} to: {0}'
                                        , options, self.ifname)

        if 'addr' in options:
            addr = options['addr']
            if '/' not in addr:
                addr += '/32'


            ip = addr.split('/')[0]
            _, host, subnet = util.ip_to_net_host_subnet(addr)
            ipb = util.encode_ip(ip)
            hostb = util.encode_ip(host)
            subnetb = util.encode_ip(subnet)

            # for the windows driver, the 'internal' IP address has to be set
            if self.mode == self.TUNMODE:
                w32f.DeviceIoControl(self._handle, TAP_IOCTL_CONFIG_TUN,
                                            ipb+hostb+subnetb, 12)
                logger.critical('WE IN TUN MODE!')


            def response(ret):
                if ret[2] != 0:
                    logger.error('error configuring address {0} on interface'
                                +' {1}: {2}', addr, self.ifname, ret[0])
                    raise Exception()

            ret = yield self._netsh(ip, subnet)
            response(ret)


        if 'mtu' in options:
            mtu = options['mtu']
            self.set_mtu(mtu)

        if 'hwaddr' in options:
            raise Exception('not implimented!')


    def doWrite(self, data):
        '''
            Write some data out to the tun/tap 'wire'.
        '''
        deferToThread(self.write, data)



if platform.system() == 'Linux':
    TwistedTunTap = TwistedTTL

elif platform.system() == 'Windows':
    TwistedTunTap = TwistedTTW

else:
    TwistedTunTap = TunTapUnsupported
    raise OSError, "Unsupported platform for tuntap"
