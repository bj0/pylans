import platform
import struct

_linux = False
_win32 = False
if platform.system() == 'Linux':
    _linux = True
elif platform.system() == 'Windows':
    _win32 = True


if _linux:
    # import and define linux-speciic stuph
    from getifaddrs import getifaddrs
    import socket
    from fcntl import ioctl
    
    SIOCGIFHWADDR = 0x8927
    
    __protocols = dict([(getattr(socket,x),x) for x in socket.__dict__ if x.startswith('AF_')])
    #from if.h
    #168 struct ifreq {
    #169 #define IFHWADDRLEN     6
    #170         union
    #171         {
    #172                 char    ifrn_name[IFNAMSIZ];            /* if name, e.g. "en0" */
    #173         } ifr_ifrn;
    #174         
    #175         union {
    #176                 struct  sockaddr ifru_addr;
    #177                 struct  sockaddr ifru_dstaddr;
    #178                 struct  sockaddr ifru_broadaddr;
    #179                 struct  sockaddr ifru_netmask;
    #180                 struct  sockaddr ifru_hwaddr;
    #181                 short   ifru_flags;
    #182                 int     ifru_ivalue;
    #183                 int     ifru_mtu;
    #184                 struct  ifmap ifru_map;
    #185                 char    ifru_slave[IFNAMSIZ];   /* Just fits the size */
    #186                 char    ifru_newname[IFNAMSIZ];
    #187                 void __user *   ifru_data;
    #188                 struct  if_settings ifru_settings;
    #189         } ifr_ifru;
    #190 };
    #191 
    #192 #define ifr_name        ifr_ifrn.ifrn_name      /* interface name       */
    #193 #define ifr_hwaddr      ifr_ifru.ifru_hwaddr    /* MAC address          */
    #194 #define ifr_addr        ifr_ifru.ifru_addr      /* address              */
    #195 #define ifr_dstaddr     ifr_ifru.ifru_dstaddr   /* other end of p-p lnk */
    #196 #define ifr_broadaddr   ifr_ifru.ifru_broadaddr /* broadcast address    */
    #197 #define ifr_netmask     ifr_ifru.ifru_netmask   /* interface net mask   */
    #198 #define ifr_flags       ifr_ifru.ifru_flags     /* flags                */
    #199 #define ifr_metric      ifr_ifru.ifru_ivalue    /* metric               */
    #200 #define ifr_mtu         ifr_ifru.ifru_mtu       /* mtu                  */
    #201 #define ifr_map         ifr_ifru.ifru_map       /* device map           */
    #202 #define ifr_slave       ifr_ifru.ifru_slave     /* slave device         */
    #203 #define ifr_data        ifr_ifru.ifru_data      /* for use by interface */
    #204 #define ifr_ifindex     ifr_ifru.ifru_ivalue    /* interface index      */
    #205 #define ifr_bandwidth   ifr_ifru.ifru_ivalue    /* link bandwidth       */
    #206 #define ifr_qlen        ifr_ifru.ifru_ivalue    /* Queue length         */
    #207 #define ifr_newname     ifr_ifru.ifru_newname   /* New name             */
    #208 #define ifr_settings    ifr_ifru.ifru_settings  /* Device/proto settings*/    

if _win32:
    # import windows specific stuph
    from getadaptersinfo import GetAdaptersInfo, AF_LINK, AF_INET, MIB_IF_TYPE_LOOPBACK

def _win32_interfaces():
    return GetAdaptersInfo(full=False)

   
        #TODO test this on windows
def _win32_ifaddresses(ifname=None):
    adapter_list = GetAdaptersInfo(ifname=ifname)
    
    result = {}
    hwaddr = []
    for adapter in adapter_list:
        if adapter.AdapterName == '':
            continue
        
        # hw address AF_LINK
        if ifname is None:
            hwaddr = result.get('AF_LINK', {})
            hwaddr[adapter.AdapterName] = adapter.Address
            result['AF_LINK'] = hwaddr
        else:
            result['AF_LINK']={'addr':adapter.Address}
        
        # other addrs AF_INET
        for ip_addr in adapter.IpAddressList:
            addr = {'address':ip_addr[0],
                    'netmask':ip_addr[1],
                    'broadcast':None}
                    
            if adapter.Type != MIB_IF_TYPE_LOOPBACK:
                # get broadcast
                from socket import inet_ntoa, inet_aton
                add = struct.unpack('!L',inet_aton(ip_addr[0]))[0]
                mask = struct.unpack('!L',inet_aton(ip_addr[1]))[0]
                bcast = inet_ntoa(struct.pack('!L',(add | ~mask) & 0xffffffff))
                addr['broadcast'] = bcast
                
            # if we're collecting them all...
            if ifname is None: 
                x = result.get('AF_INET',{})#(adapter.AdapterName, addr)
                y = x.get(adapter.AdapterName, [])
                y.append(addr)
                x[adapter.AdapterName] = y
                result['AF_INET'] = x
            else:                
                x = result.get('AF_INET',[])
                x.append(addr)
                result['AF_INET'] = x
    
    if len(result) == 0:
        raise ValueError, 'You must specify a valid interface name.'
        
    return result


def _linux_interfaces():
    ifaddrs = getifaddrs()
    
    return list(set(x.name for x in ifaddrs))
    
def _linux_ifaddresses(ifname=None):
    ifaddrs = getifaddrs()
    
    result = {}
    for addrs in ifaddrs:
        # sometimes there are entries with no addresses
        # -- this was preventing adapters with mac addrs but no IPs from being
        # returned
#        if addrs.addr is None:
#            continue

        # filter
        if ifname is not None and ifname != addrs.name:
            continue
            
            
        # hw address?
        s = socket.socket(type=socket.SOCK_DGRAM)   
        ifr = addrs.name + '\0'*(32-len(addrs.name))    
        ifs = ioctl(s.fileno(), SIOCGIFHWADDR, ifr)
        mac = ifs[18:24]

        if ifname is None and addrs.name not in result.get('AF_LINK', {}):        
            d = result.get('AF_LINK', {})
            d[addrs.name] = ':'.join(['{0:02x}'.format(x) for x in struct.unpack('!6B', mac)])
            result['AF_LINK'] = d
        elif ifname is not None:
            result['AF_LINK'] = {'addr':':'.join(['{0:02x}'.format(x) for x in struct.unpack('!6B', mac)])}
        
        if addrs.addr is not None:
            # ip addresses
            addr = {'address':addrs.addr[0],
                    'netmask':addrs.netmask[0],
                    'broadcast':addrs.broadcast[0] if addrs.broadcast is not None else None}
        else:
            addr = {}
                
        #if we're collecting them all...
        fam = __protocols.get(addrs.family, addrs.family)
        if ifname is None:
            x = result.get(fam, {})
            y = x.get(addrs.name, [])
            y.append(addr)
            x[addrs.name] = y
            result[fam] = x
        else:
            x = result.get(fam, [])
            x.append(addr)
            result[fam] = x
        
    if len(result) == 0:
        raise ValueError, 'You must specify a valid interface name.'
        
    return result
    
    
def interfaces():
    if _win32:
        return _win32_interfaces()
    elif _linux:
        return _linux_interfaces()
       
def ifaddresses(ifname=None):
    if _win32:
        return _win32_ifaddresses(ifname)
    elif _linux:
        return _linux_ifaddresses(ifname)
        
    
__all__ = ['interfaces', 'ifaddresses']

if __name__ == '__main__':
    import json
    print 'interfaces:'
    print json.dumps(interfaces(), indent=2)
    print 'ifaddresses:'
    print json.dumps(ifaddresses(), indent=2)
