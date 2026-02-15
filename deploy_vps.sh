#!/bin/bash
# RAGF v2.0 - VPS Deployment Script
# Server: crono-apps (65.19.178.76)

set -e
echo "🚀 Deploying RAGF v2.0..."

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
apt install docker-compose -y

# Clone repo
cd /opt
git clone https://github.com/cronocom/rafg.git || (cd rafg && git pull)
cd rafg

# Setup environment
cp .env.example .env
sed -i "s/CHANGEME/$(openssl rand -hex 32)/g" .env

# Deploy
docker-compose up -d

# Install Nginx
apt install nginx -y
cat > /etc/nginx/sites-available/ragf << 'EOF'
server {
    listen 80;
    server_name 65.19.178.76;
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
    }
}
EOF
ln -sf /etc/nginx/sites-available/ragf /etc/nginx/sites-enabled/
systemctl reload nginx

echo "✅ Deployed! Access: http://65.19.178.76"
