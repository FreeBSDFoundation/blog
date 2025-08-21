#!/usr/bin/env zsh

if [ "$(uname -s)" != "FreeBSD" ]; then
    echo "Run on a FreeBSD host"
    exit 1
fi

set -eo pipefail

SNAP=${2:-$(zfs list -t snapshot -H -o name | grep "jails/_base" | cut -f3 -d/)}

if [ -z $1 ]; then
    echo "pass new jail name"
    exit 1
else
    new=$1
fi

zfs clone zroot/jails/${SNAP} zroot/jails/${new}

test -d /etc/jail.conf.d || mkdir -p /etc/jail.conf.d
cat > /etc/jail.conf.d/${new}.conf <<EOF
${new} {
    host.hostname = "${new}.jail";
    path = "/jails/${new}";
}
EOF

sysrc jail_list+=${new}
