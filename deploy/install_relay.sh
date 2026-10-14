#!/usr/bin/env bash
set -euo pipefail
# Run on a dedicated Ubuntu/Debian VPS, never on the owner's Windows computer.
if [[ ${EUID} -ne 0 ]]; then echo 'Run as root on the dedicated VPS'; exit 1; fi
if [[ $# -ne 1 || ! $1 =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ .*)?$ ]]; then echo 'Pass the dedicated public SSH key as one quoted argument'; exit 1; fi
if [[ $1 == *$'\n'* || $1 == *$'\r'* ]]; then echo 'Public key must be one line'; exit 1; fi
task_source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
apt-get update
apt-get install -y python3 openssh-server
install -d -m 755 /opt/medpravo-relay
install -m 644 "$task_source_dir/russian_proxy.py" "$task_source_dir/network.py" "$task_source_dir/sources.json" /opt/medpravo-relay/
if ! id medpravo-relay >/dev/null 2>&1; then useradd --create-home --shell /bin/sh medpravo-relay; fi
install -d -m 700 -o medpravo-relay -g medpravo-relay /home/medpravo-relay/.ssh
printf 'restrict,port-forwarding,permitopen="127.0.0.1:8118" %s\n' "$1" >/home/medpravo-relay/.ssh/authorized_keys
chown medpravo-relay:medpravo-relay /home/medpravo-relay/.ssh/authorized_keys
chmod 600 /home/medpravo-relay/.ssh/authorized_keys
cat >/etc/ssh/sshd_config.d/70-medpravo-relay.conf <<'CONF'
Match User medpravo-relay
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    AllowTcpForwarding local
    AllowAgentForwarding no
    X11Forwarding no
    PermitTTY no
    PermitOpen 127.0.0.1:8118
    ForceCommand /usr/bin/false
Match all
CONF
cat >/etc/systemd/system/medpravo-relay.service <<'UNIT'
[Unit]
Description=MedPravo relay for official legal sources
After=network-online.target
Wants=network-online.target
[Service]
DynamicUser=yes
WorkingDirectory=/opt/medpravo-relay
ExecStart=/usr/bin/python3 /opt/medpravo-relay/russian_proxy.py --port 8118
Restart=on-failure
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
RestrictAddressFamilies=AF_INET AF_UNIX
[Install]
WantedBy=multi-user.target
UNIT
/usr/sbin/sshd -t
systemctl daemon-reload
systemctl enable --now medpravo-relay
systemctl reload ssh
echo 'Relay installed; port 8118 listens only on loopback, accessible through SSH'
echo 'SSH server public host key (verify through the provider console):'
cat /etc/ssh/ssh_host_ed25519_key.pub
