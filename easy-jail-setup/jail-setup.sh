#!/bin/sh

if [ "$(uname -s)" != "FreeBSD" ]; then
    echo "Run on a FreeBSD host"
    exit 1
fi

set -eo pipefail

REL="$(freebsd-version)"
ARCH="$(uname -m)"
URL="https://download.freebsd.org/ftp/releases/${ARCH}/${REL}"

sysrc jail_enable="YES" && sysrc jail_parallel_start="YES"

POOL=$(zpool list -Ho name)
zfs list ${POOL}/jails >/dev/null 2>&1 || zfs create -o mountpoint=/jails ${POOL}/jails
zfs list ${POOL}/jails/media >/dev/null 2>&1 || zfs create ${POOL}/jails/media
zfs list ${POOL}/jails/_base >/dev/null 2>&1 || zfs create ${POOL}/jails/_base

if [ ! -f /jails/media/${REL}-base.txz ]; then
    fetch ${URL}/base.txz -o /jails/media/${REL}-base.txz
fi

if [ ! -f /jails/_base/etc/localtime ]; then 
    tar -xf /jails/media/${REL}-base.txz -C /jails/_base/ --unlink
    cp /etc/resolv.conf /jails/_base/etc/resolv.conf
    cp /etc/localtime /jails/_base/etc/localtime
    freebsd-update -b /jails/_base/ fetch install
    pkg -c /jails/_base install -y pkg python zsh
    zfs snapshot zroot/jails/_base@${REL}-$(date +%d-%b-%y)
fi

if [ ! -f /etc/jail.conf ]; then
    cat > /etc/jail.conf <<EOF
# https://man.freebsd.org/jail.conf
# https://man.freebsd.org/jail
#
ip4 = inherit;
ip6 = inherit;

# defaults to apply to all jails
exec.start = "/bin/sh /etc/rc";
exec.stop = "/bin/sh /etc/rc.shutdown jail";
exec.clean;

# filesystem
mount.devfs;
devfs_ruleset=4;
enforce_statfs=1;
securelevel=2;
#allow.mount.zfs;
#allow.mount;

# disable all the shiny things
allow.mount.nodevfs;
allow.mount.nofdescfs;
allow.mount.nolinprocfs;
allow.mount.nonullfs;
allow.mount.noprocfs;
allow.mount.notmpfs;
allow.nochflags;

# but these are always useful
allow.raw_sockets;
allow.reserved_ports;
allow.sysvipc=1;

# misc
allow.nomlock;
allow.noquotas;
allow.noread_msgbuf;
allow.noset_hostname;
allow.nosocket_af;
allow.nosysvipc;
sysvmsg=disable;
sysvsem=disable;
children.max=0;
.include "/etc/jail.conf.d/*.conf";
EOF
fi
