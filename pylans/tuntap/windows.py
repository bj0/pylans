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
# windows_tuntap.py
# TunTapDevice interface for windows

from __future__ import absolute_import
from struct import pack, calcsize
import atexit
import platform
from winerror import ERROR_IO_PENDING
import _winreg as reg
import logging
import pywintypes
import win32event as w32e
import win32file as w32f
import winerror
from . import util
from ..net.getadaptersinfo import GetAdaptersInfo
from . import TunTapBase

logger = logging.getLogger(__name__)

FILE_DEVICE_UNKNOWN = 0x22
METHOD_BUFFERED = 0x0
FILE_ANY_ACCESS = 0x0

def CTL_CODE(DeviceType, Function, Method, Access):
    return (DeviceType << 16) | (Access << 14) | (Function << 2) | Method

def TAP_CONTROL_CODE(function, method):
    return CTL_CODE(FILE_DEVICE_UNKNOWN, function, method, FILE_ANY_ACCESS)

TAP_IOCTL_GET_MAC               = TAP_CONTROL_CODE (1, METHOD_BUFFERED)
TAP_IOCTL_GET_VERSION           = TAP_CONTROL_CODE (2, METHOD_BUFFERED)
TAP_IOCTL_GET_MTU               = TAP_CONTROL_CODE (3, METHOD_BUFFERED)
TAP_IOCTL_GET_INFO              = TAP_CONTROL_CODE (4, METHOD_BUFFERED)
TAP_IOCTL_CONFIG_POINT_TO_POINT = TAP_CONTROL_CODE (5, METHOD_BUFFERED)
TAP_IOCTL_SET_MEDIA_STATUS      = TAP_CONTROL_CODE (6, METHOD_BUFFERED)
TAP_IOCTL_CONFIG_DHCP_MASQ      = TAP_CONTROL_CODE (7, METHOD_BUFFERED)
TAP_IOCTL_GET_LOG_LINE          = TAP_CONTROL_CODE (8, METHOD_BUFFERED)
TAP_IOCTL_CONFIG_DHCP_SET_OPT   = TAP_CONTROL_CODE (9, METHOD_BUFFERED)
TAP_IOCTL_CONFIG_TUN            = TAP_CONTROL_CODE (10, METHOD_BUFFERED)


USERMODEDEVICEDIR = "\\\\.\\Global\\"
TAPSUFFX = ".tap"
class_key = 'SYSTEM\\CurrentControlSet\\Control\\Class\\{4D36E972-E325-11CE-BFC1-08002BE10318}'
net_key = 'SYSTEM\\CurrentControlSet\\Control\\Network\\{4D36E972-E325-11CE-BFC1-08002BE10318}'
HKLM = reg.HKEY_LOCAL_MACHINE

try:
    from twisted.python.procutils import which
except ImportError:
    # no twisted
    from .which import which

cmd = which('netsh')[0]

class TunTapWindows(TunTapBase):
    TUNMODE = 0
    TAPMODE = 1

    def __init__(self, mode="TAP", handle=None):

        self._handle = None

        # check mode, should come in as 'TUN' or 'TAP'
        if isinstance(mode, str):
            mode = self.TUNMODE if mode == 'TUN' else self.TAPMODE

        if handle is None:
            handle, devid = self._get_tap_handle()

        if handle is None:
            logger.critical('Could not get TAP adapter handle')
            raise Exception('Could not get TAP adapter handle')

        logger.debug('got tap handle: {0}'.format(handle))
        
        self._handle = handle
        self.ifname = devid
        self.__idx = GetAdaptersInfo(ifname=devid)[0]['Index']
        self.overlapped_read = pywintypes.OVERLAPPED()
        self.overlapped_write = pywintypes.OVERLAPPED()

        self.overlapped_read.hEvent = w32e.CreateEvent(None,True,False,None)
        self.overlapped_write.hEvent = w32e.CreateEvent(None,True,False,None)

        self.mtu = 1500
        self.mode = mode
        # mac, ip, mask, mtu
        
        # close device on exit
        atexit.register(self.close)
        

#    def get_mac(self):
#        # get mac handle
#        return w32f.DeviceIoControl(handle, TAP_IOCTL_GET_MAC, None, 6)

    def up(self):
        # enable dev
        self._enable_iface()
        
    def down(self):
        # disable dev
        self._disable_iface()

    def set_mtu(self, mtu):
        raise Exception('not implimented!')
        
    def get_mtu(self):
        raise Exception('not implimented!')

    def _shell(self, cmd):
        return sp.call(cmd)

    def _netsh(self, address, netmask):
        '''Invoke M$' netsh command to set ip address and netmask'''
        ver = platform.win32_ver()[0]
        if ver == 'XP':
            return self._shell((cmd,
                'interface','ip','set','address',
                self.ifname,'static',address,netmask))
        elif ver == '7' or ver == 'post2008Server':
            return self._shell((cmd,
                'interface','ipv4','set','address',
                str(self.__idx),'static',address,netmask))
        else:
            raise OSError, 'Unsupported version of Windows: {0}.'.format(ver)

    def configure_iface(self, **options):

        logger.info('configuring interface {1} to: {0}'
                                .format(options, self.ifname))
    
        # check for spurious args
        err = [arg for arg in options.keys() 
                            if arg not in ['addr','mtu','hwaddr']]
        if len(err) > 0:
            logger.error('configure_iface passed unrecognized arguments: {0}'
                    .format(err))

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
                                +' {1}: {2}'.format(addr, self.ifname, ret[0]))
                    raise Exception()

            ret = self._netsh(ip, subnet)
            response(ret)

                
        if 'mtu' in options:
            mtu = options['mtu']
            self.set_mtu(mtu)                
        
        if 'hwaddr' in options:
            raise Exception('not implimented!')


    def _enable_iface(self):
        w32f.DeviceIoControl(self._handle, TAP_IOCTL_SET_MEDIA_STATUS, pack('I',True), calcsize('I'))

    def _disable_iface(self):
        w32f.DeviceIoControl(self._handle, TAP_IOCTL_SET_MEDIA_STATUS, pack('I',False), calcsize('I'))

    def __del__(self):
        self.close()

    def close(self):
        if self._handle is not None:
            w32f.CloseHandle(self._handle)
            self._handle = None

    def _get_tap_handle(self):
        '''Get a file handle to an available TAP adapter'''
        def findTaps():
            '''get a list of TAP adapters'''
            h = reg.OpenKey(HKLM, class_key)
            devs = []
            for i in range(0,30):
                try:
                    k = reg.EnumKey(h, i)
                    h2 = reg.OpenKey(HKLM, '%s\\%s'%(class_key, k))
                    cid = reg.QueryValueEx(h2, 'ComponentId')[0]
                    if cid.startswith('tap'):
                        devid = reg.QueryValueEx(h2, 'NetCfgInstanceId')[0]
                        devs.append(devid)
                except WindowsError, s: # no more keys to enum
                    if s.errno == 259:
                        break
                    continue
                except Exception:
                    continue
            return devs

        # iterate through TAP adapters, trying to find one available for use
        for devid in findTaps():
            f = None
            path = '%s\\%s\\Connection' % (net_key, devid)
            try:
                h2 = reg.OpenKey(HKLM, path)
            except:
                continue

            tapname = '%s%s%s' % (USERMODEDEVICEDIR, devid, TAPSUFFX)
            try:
                f = w32f.CreateFile(tapname,
                        w32f.GENERIC_READ | w32f.GENERIC_WRITE,
                        0,
                        None,
                        w32f.OPEN_EXISTING,
                        w32f.FILE_ATTRIBUTE_SYSTEM | w32f.FILE_FLAG_OVERLAPPED,
                        0)
            except Exception, s:
                print repr(s)
                continue
            else:
                logger.debug('found tap device {0}'.format(tapname))
                return (f, devid)

            return None

    def read(self):
        '''Read data from TAP adapter (blocking)'''
        w32e.ResetEvent(self.overlapped_read.hEvent)

        (err, data) = w32f.ReadFile(self._handle, self.mtu, self.overlapped_read)
        if err == ERROR_IO_PENDING:
            w32e.WaitForSingleObject(self.overlapped_read.hEvent, w32e.INFINITE)
            size = w32f.GetOverlappedResult(self._handle, self.overlapped_read, False)
        else:
            # need to get size
            size = w32f.GetOverlappedResult(self._handle, self.overlapped_read, False)

        return str(data[:size])

    def write(self, data):
        '''Write data to TAP adapter (blocking)'''
        w32e.ResetEvent(self.overlapped_write.hEvent)

        (err, size) = w32f.WriteFile(self._handle, data, self.overlapped_write)

        if err != 0: # must be IO_PENDING
            w32e.WaitForSingleObject(self.overlapped_write.hEvent, w32e.INFINITE)
            size = w32f.GetOverlappedResult(self._handle, self.overlapped_write, False)

        return size
        
        
        

