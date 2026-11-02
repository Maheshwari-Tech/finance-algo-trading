#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu 22.04/24.04 server. Run as root:
#   curl -fsSL https://raw.githubusercontent.com/Maheshwari-Tech/algo-trading/main/deploy/setup-server.sh | bash -s -- "<CircleCI deploy public key>"
# or copy this file over and run:  sudo bash setup-server.sh "<CircleCI deploy public key>"
#
# Installs Docker, enables a firewall (SSH/HTTP/HTTPS only), creates a `deploy` user that CircleCI logs in as,
# and prepares /opt/algo-trading. It does NOT write secrets: you create /opt/algo-trading/.env yourself afterwards.
set -euo pipefail

DEPLOY_KEY="${1:-}"
[ "$(id -u)" = 0 ] || { echo "Run as root (sudo)."; exit 1; }
[ -n "$DEPLOY_KEY" ] || { echo "Usage: setup-server.sh \"ssh-ed25519 AAAA... circleci-deploy\""; exit 1; }

echo "==> Updating packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q && apt-get upgrade -yq
apt-get install -yq curl ufw fail2ban unattended-upgrades

echo "==> Installing Docker"
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

echo "==> Creating deploy user"
id deploy >/dev/null 2>&1 || useradd -m -s /bin/bash deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
grep -qxF "$DEPLOY_KEY" /home/deploy/.ssh/authorized_keys 2>/dev/null || echo "$DEPLOY_KEY" >> /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys && chmod 600 /home/deploy/.ssh/authorized_keys

echo "==> App folder"
install -d -o deploy -g deploy /opt/algo-trading

echo "==> Firewall: SSH, HTTP, HTTPS only"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

echo "==> SSH hardening: keys only"
if [ -s /root/.ssh/authorized_keys ] || ls /home/*/.ssh/authorized_keys 2>/dev/null | grep -vq '^/home/deploy/'; then
  sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
  systemctl reload ssh 2>/dev/null || systemctl reload sshd
else
  echo "    Skipped: no SSH key found for your own login, so password login stays on (otherwise you'd be locked out)."
fi

echo "==> Automatic security updates + fail2ban"
dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable --now fail2ban

cat <<MSG

Done. Next:
  1. Create /opt/algo-trading/.env as the deploy user (template: deploy/.env.example in the repo):
       sudo -u deploy nano /opt/algo-trading/.env && sudo chmod 600 /opt/algo-trading/.env
  2. In CircleCI context 'production' set DEPLOY_HOST=$(curl -fsS https://api.ipify.org 2>/dev/null || echo '<this server IP>') and DEPLOY_USER=deploy
  3. Push to main; CircleCI deploys and checks https://<DOMAIN>/api/ready
MSG
