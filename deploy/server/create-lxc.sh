#!/bin/sh
# Creates the central cardiag server as a Proxmox container, joined to Tailscale.
# Run from a checkout, on any machine that can ssh to the Proxmox host as root:
#
#   deploy/server/create-lxc.sh [--host root@192.168.0.137] [--id 133] [--storage THICC] [--authkey tskey-...]
#
# The container runs "cardiag serve --accept-uploads" on 127.0.0.1:8000, and
# Tailscale publishes it on the tailnet only, as https://<hostname>.<tailnet>.ts.net.
# Without --authkey, Tailscale prints a login link to open once.
set -eu

pve=root@192.168.0.137
id=
storage=THICC
name=cardiag
template=local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst
authkey=
while [ $# -gt 0 ]; do
    case $1 in
        --host) pve=$2; shift 2 ;;
        --id) id=$2; shift 2 ;;
        --storage) storage=$2; shift 2 ;;
        --name) name=$2; shift 2 ;;
        --template) template=$2; shift 2 ;;
        --authkey) authkey=$2; shift 2 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done
here=$(cd "$(dirname "$0")" && pwd)
checkout=$(cd "$here/../.." && pwd)
[ -n "$id" ] || id=$(ssh "$pve" pvesh get /cluster/nextid)

echo "Creating container $id ($name) on $pve"
ssh "$pve" sh -s <<EOF
set -eu
pct create $id $template \
    --hostname $name --description 'cardiag central server: collects recordings from the car boxes over Tailscale' \
    --tags cardiag --ostype debian --unprivileged 1 --features nesting=1,keyctl=1 \
    --cores 1 --memory 512 --swap 512 --rootfs $storage:8 \
    --net0 name=eth0,bridge=vmbr0,ip=dhcp,type=veth --onboot 1 --startup order=80,up=10
cat >> /etc/pve/lxc/$id.conf <<'CONF'
lxc.cgroup2.devices.allow: c 10:200 rwm
lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
CONF
pct start $id
for i in \$(seq 30); do pct exec $id -- getent hosts deb.debian.org >/dev/null 2>&1 && break; sleep 2; done
EOF

echo "Installing packages and Tailscale"
ssh "$pve" pct exec "$id" -- sh -s <<'EOF'
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq --no-install-recommends python3 python3-serial curl ca-certificates unattended-upgrades
curl -fsSL https://tailscale.com/install.sh | sh
systemctl enable --now tailscaled
useradd --system --home-dir /var/lib/cardiag --shell /usr/sbin/nologin cardiag 2>/dev/null || true
EOF

echo "Installing cardiag from $checkout"
tar -C "$checkout" --exclude=__pycache__ -cf - deploy src/cardiag |
    ssh "$pve" "pct exec $id -- sh -c 'rm -rf /root/cardiag && mkdir /root/cardiag && tar -C /root/cardiag -xf -'"
ssh "$pve" pct exec "$id" -- sh -s <<'EOF'
set -eu
/root/cardiag/deploy/pi/install.sh --user cardiag
install -d /etc/systemd/system/cardiag.service.d
cp /root/cardiag/deploy/server/central.conf /etc/systemd/system/cardiag.service.d/central.conf
rm -f /etc/polkit-1/rules.d/10-cardiag-network.rules  # Wi-Fi switching is for the box in the car
systemctl daemon-reload
systemctl restart cardiag
EOF

echo "Joining Tailscale"
ssh "$pve" pct exec "$id" -- tailscale up --ssh --hostname="$name" ${authkey:+--authkey="$authkey"}
ssh "$pve" pct exec "$id" -- tailscale serve --bg --https=443 http://127.0.0.1:8000
ssh "$pve" pct exec "$id" -- tailscale serve status
