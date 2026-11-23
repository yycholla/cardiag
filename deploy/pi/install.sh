#!/bin/sh
# Installs this checkout of cardiag as a service on a Raspberry Pi.
#
#   sudo deploy/pi/install.sh                      on the Pi itself
#   sudo deploy/pi/install.sh --root /mnt/rootfs   onto a Pi's SD card mounted on another machine
#
# Options:
#   --root DIR     root of the Pi's filesystem (default /)
#   --user NAME    account the service runs as (default: the account with user ID 1000)
#   --vendor DIR   a directory holding the pyserial package ("serial"), copied alongside the
#                  app for a Pi that cannot install python3-serial itself
set -eu

root=/
user=
vendor=
while [ $# -gt 0 ]; do
    case $1 in
        --root) root=$2; shift 2 ;;
        --user) user=$2; shift 2 ;;
        --vendor) vendor=$2; shift 2 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done
root=${root%/}
here=$(cd "$(dirname "$0")" && pwd)
checkout=$(cd "$here/../.." && pwd)

[ "$(id -u)" -eq 0 ] || { echo "run this with sudo" >&2; exit 1; }
[ -f "$root/etc/passwd" ] || { echo "$root/ does not look like a Linux system" >&2; exit 1; }
[ -n "$user" ] || user=$(awk -F: '$3 == 1000 { print $1 }' "$root/etc/passwd")
owner=$(awk -F: -v user="$user" '$1 == user { print $3 ":" $4 }' "$root/etc/passwd")
[ -n "$owner" ] || { echo "there is no account called '$user' in $root/etc/passwd" >&2; exit 1; }
version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$checkout/src/cardiag/__init__.py")
[ -n "$version" ] || { echo "could not read the version from $checkout" >&2; exit 1; }
if [ -n "$vendor" ] && [ ! -d "$vendor/serial" ]; then
    echo "$vendor does not contain the pyserial package (a directory called serial)" >&2
    exit 1
fi

home=$root/opt/cardiag
release=$home/releases/$version
install -d "$home/releases"
rm -rf "$release" "$home/src"  # "src" directly under the home is the layout before updates existed
install -d "$release/src"
cp -r "$checkout/src/cardiag" "$release/src/"
find "$release" -name __pycache__ -prune -exec rm -rf {} +
ln -sfn "releases/$version" "$home/current"
rm -f "$home/pending" "$home/pending.tried" "$home/rolled-back"
if [ -n "$vendor" ]; then
    rm -rf "$home/vendor"
    install -d "$home/vendor"
    cp -r "$vendor/serial" "$home/vendor/"
fi
chown -R "$owner" "$home"

install -D -m 0755 "$here/cardiag" "$root/usr/local/bin/cardiag"
install -d "$root/etc/systemd/system" "$root/etc/polkit-1/rules.d"
sed "s/@USER@/$user/" "$here/cardiag.service" > "$root/etc/systemd/system/cardiag.service"
sed "s/@USER@/$user/" "$here/50-cardiag-network.rules" > "$root/etc/polkit-1/rules.d/50-cardiag-network.rules"
chmod 0644 "$root/etc/systemd/system/cardiag.service" "$root/etc/polkit-1/rules.d/50-cardiag-network.rules"

if [ -z "$root" ]; then
    if [ ! -d "$home/vendor/serial" ] && ! python3 -c 'import serial' 2>/dev/null; then
        echo "pyserial is missing: run 'sudo apt install python3-serial', then 'sudo systemctl restart cardiag'" >&2
    fi
    systemctl daemon-reload
    systemctl enable cardiag.service
    systemctl restart cardiag.service
else
    systemctl --root="$root" enable cardiag.service
fi
echo "Installed cardiag $version for $user in ${root:-/}"
