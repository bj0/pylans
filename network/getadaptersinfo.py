from ctypes import Structure, windll, sizeof
from ctypes import POINTER, byref
from ctypes import c_ulong, c_uint, c_ubyte, c_char

AF_IMPLINK = 3
AF_INET6 = 23
AF_UNSPEC = 0
AF_PUP = 4
AF_IRDA = 26
AF_BAN = 21
AF_DATAKIT = 9
AF_CHAOS = 5
AF_HYLINK = 15
AF_FIREFOX = 19
AF_IPX = 6
AF_ATM = 22
AF_CCITT = 10
AF_UNIX = 1
AF_APPLETALK = 16
AF_DECnet = 12
AF_VOICEVIEW = 18
AF_SNA = 11
AF_DLI = 13
AF_UNKNOWN1 = 20
AF_LAT = 14
AF_ECMA = 8
AF_CLUSTER = 24
AF_ISO = 7
AF_NETBIOS = 17
AF_12844 = 25
AF_LINK = -1000
AF_NS = 6
AF_INET = 2
AF_NETDES = 28

#Some other type of network interface.
MIB_IF_TYPE_OTHER = 1

#An Ethernet network interface.
MIB_IF_TYPE_ETHERNET = 6

#MIB_IF_TYPE_TOKENRING
IF_TYPE_ISO88025_TOKENRING = 9

#A PPP network interface.
MIB_IF_TYPE_PPP = 23

#A software loopback network interface.
MIB_IF_TYPE_LOOPBACK = 24

#An ATM network interface.
MIB_IF_TYPE_SLIP = 28

#An IEEE 802.11 wireless network interface.
#Note  This adapter type is returned on Windows Vista and later. On Windows Server 2003 and Windows XP , an IEEE 802.11 wireless network interface returns an adapter type of MIB_IF_TYPE_ETHERNET.
IF_TYPE_IEEE80211 = 71

ERROR_SUCCESS           = 0
ERROR_NOT_SUPPORTED     = 50
ERROR_INVALID_PARAMETER = 87
ERROR_BUFFER_OVERFLOW   = 111
ERROR_NO_DATA           = 232
MAX_ADAPTER_DESCRIPTION_LENGTH = 128
MAX_ADAPTER_NAME_LENGTH = 256
MAX_ADAPTER_ADDRESS_LENGTH = 8
    
class IP_ADDR_STRING(Structure):
    pass
        
PIP_ADDR_STRING = POINTER(IP_ADDR_STRING)
IP_ADDR_STRING._fields_ = [
    ("Next", PIP_ADDR_STRING),
    ("IpAddress", c_char * 16),
    ("IpMask", c_char * 16),
    ("Context", c_ulong)]
    
class IP_ADAPTER_INFO (Structure):
    pass
        
PIP_ADAPTER_INFO = POINTER(IP_ADAPTER_INFO)
IP_ADAPTER_INFO._fields_ = [
    ("Next", PIP_ADAPTER_INFO),
    ("ComboIndex", c_ulong),
    ("AdapterName", c_char * (MAX_ADAPTER_NAME_LENGTH + 4)),
    ("Description", c_char * (MAX_ADAPTER_DESCRIPTION_LENGTH + 4)),
    ("AddressLength", c_uint),
    ("Address", c_ubyte * MAX_ADAPTER_ADDRESS_LENGTH),
    ("Index", c_ulong),
    ("Type", c_uint),
    ("DhcpEnabled", c_uint),
    ("CurrentIpAddress", PIP_ADDR_STRING),
    ("IpAddressList", IP_ADDR_STRING),
    ("GatewayList", IP_ADDR_STRING),
    ("DhcpServer", IP_ADDR_STRING),
    ("HaveWins", c_uint),
    ("PrimaryWinsServer", IP_ADDR_STRING),
    ("SecondaryWinsServer", IP_ADDR_STRING),
    ("LeaseObtained", c_ulong),
    ("LeaseExpires", c_ulong)]

_GetAdaptersInfo = windll.iphlpapi.GetAdaptersInfo
_GetAdaptersInfo.restype = c_ulong
_GetAdaptersInfo.argtypes = [PIP_ADAPTER_INFO, POINTER(c_ulong)]

def iter_list(node):
    '''Turn a returned linked-list into a generator'''
    while node:
        yield node
        node = node.Next


#    buflen = c_ulong(0) #sizeof(adapter_list)
#    rc = GetAdaptersInfo(None, byref(buflen))
#    
#    # Make the API call
#    while rc == ERROR_BUFFER_OVERFLOW:
#        sz = buflen.value / sizeof(IP_ADAPTER_INFO)
#        adapter_list = (IP_ADAPTER_INFO * sz)()
#        rc = GetAdaptersInfo(byref(adapter_list[0]), byref(buflen))

#    if rc != ERROR_SUCCESS and rc != ERROR_NO_DATA:
#        raise OSError, "Unable to obtain adapter information."
#    
#    result = {}
#    hwaddr = []
#    for pinfo in adapter_list:
#        if pinfo.AdapterName == '':
#            continue
#        
#        # filter based on ifname
#        if ifname is not None and ifname != pinfo.AdapterName:
#            continue
#        #TODO test this on windows
#        # hw address AF_LINK
#        if ifname is None:
#            hwaddr = result.get(AF_LINK, {})
#            hwaddr[ifname] = ':'.join('{0:02x}'.format(i) for i in pinfo.Address[:pinfo.AddressLength])
#            result[AF_LINK] = hwaddr
#        else:
#            result[AF_LINK]={'addr':':'.join('{0:02x}'.format(i) for i in pinfo.Address[:pinfo.AddressLength])}
#        
#        # other addrs AF_INET
#        for ip_addr in iter_list(pinfo.IpAddressList):
#            addr = {'address':ip_addr.IpAddress,
#                    'netmask':ip_addr.IpMask,
#                    'broadcast':None}
#                    
#            if pinfo.Type != MIB_IF_TYPE_LOOPBACK:
#                # get broadcast
#                from socket import inet_ntoa, inet_aton
#                add = struct.unpack('!L',inet_aton(ip_addr.IpAddress))[0]
#                mask = struct.unpack('!L',inet_aton(ip_addr.IpMask))[0]
#                bcast = inet_ntoa(struct.pack('!L',(add | ~mask) & 0xffffffff))
#                addr['broadcast'] = bcast
#                
#            # if we're collecting them all...
#            if ifname is None: 
##                addr['interface'] = pinfo.AdapterName
#                addr = (pinfo.AdapterName, addr)
#                
#            x = result.get(AF_INET,[])
#            x.append(addr)
#            result[AF_INET] = x
#    
#    if len(result) == 0:
#        raise ValueError, 'You must specify a valid interface name.'
#        
#    return result

class DictObject(dict):
    def __setattr__(self, attr, value):
        self[attr] = value
    def __getattr__(self, attr):
        return self[attr]

def GetAdaptersInfo(full=True, return_dict=False, ifname=None):
    buflen = c_ulong(0) #sizeof(adapter_list)
    rc = _GetAdaptersInfo(None, byref(buflen))
    
    # Make the API call
    while rc == ERROR_BUFFER_OVERFLOW:
        sz = buflen.value / sizeof(IP_ADAPTER_INFO)
        adapter_list = (IP_ADAPTER_INFO * sz)()
        rc = _GetAdaptersInfo(byref(adapter_list[0]), byref(buflen))

    if rc != ERROR_SUCCESS and rc != ERROR_NO_DATA:
        raise OSError, "Unable to obtain adapter information."
    
    result = []
    hwaddr = []
    for pinfo in adapter_list:
        # full = False means we just want an adapter list
        if not full:
            if pinfo.AdapterName != '':
                result.append(pinfo.AdapterName)
            continue
            
        # filter
        if ifname is not None and ifname != pinfo.AdapterName:
            continue
            
        dinfo = DictObject()
        #dinfo = {}
        dinfo['AdapterName'] = pinfo.AdapterName
        dinfo['Address'] = ':'.join('%02x'%i for i in pinfo.Address[:pinfo.AddressLength])
        dinfo['AddressLength'] = pinfo.AddressLength
        dinfo['ComboIndex'] = pinfo.ComboIndex
        dinfo['CurrentIpAddress'] = (pinfo.CurrentIpAddress.IpAddress, pinfo.CurrentIpAddress.IpMask) if pinfo.CurrentIpAddress else None
        dinfo['Description'] = pinfo.Description
        dinfo['DhcpEnabled'] = bool(pinfo.DhcpEnabled)
        dinfo['DhcpServer'] = (pinfo.DhcpServer.IpAddress, pinfo.DhcpServer.IpMask) if pinfo.DhcpServer else None
        dinfo['GatewayList'] = [(node.IpAddress, node.IpMask) for node in iter_list(pinfo.GatewayList)]
        dinfo['HaveWins'] = bool(pinfo.HaveWins)
        dinfo['Index'] = pinfo.Index
        dinfo['IpAddressList'] = [(node.IpAddress, node.IpMask) for node in iter_list(pinfo.IpAddressList)]
        dinfo['LeaseExpires'] = pinfo.LeaseExpires
        dinfo['LeaseObtained'] = pinfo.LeaseObtained
#        dinfo['Next'] = pinfo.Next
        dinfo['PrimaryWinsServer'] = (pinfo.PrimaryWinsServer.IpAddress, pinfo.PrimaryWinsServer.IpMask) if pinfo.PrimaryWinsServer else None
        dinfo['Type'] = pinfo.Type
    
        result.append(dinfo)           
            
    if return_dict:
        return dict(((x['AdapterName'], x) for x in result))
    return result
    
if __name__ == '__main__':
    from pprint import pprint
    pprint(GetAdaptersInfo())
    
