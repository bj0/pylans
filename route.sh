#!/bin/bash

# external (peer) IPs to create static routes to
# this prevents traffic from being routed through the pylans gateway
# which isn't necessary since it's encrypted already
static='205.185.125.201 68.98.88.79'

# try to find the current gateway
gw=`ip route get 8.8.8.8 | awk ' /8.8.8.8/ { print $2,$3,$4,$5 } '`

# grab the gateway to the pylans box to route through
# it must have ip forwarding enabled and NAT setup in iptables
# either through MASQUERADE or SNAT:
# iptables -t nat -A POSTROUTING -o venet0 -j MASQUERADE
# iptables -t nat -A POSTROUTING -o venet0 -j SNAT --to 205.185.125.201
pygw=`ip route get 10.0.1.1 | awk ' /10.0.1.1/ { print $1,$2,$3 } '`

# add static routes
for ip in $static
do
    ip route add $ip $gw
done

# remove gateway
ip route del default

# add new gateway
ip route add default via $pygw
