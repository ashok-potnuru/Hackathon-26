#!/bin/bash
# One-time setup script for a fresh EC2 instance (Ubuntu 22.04).
# Run as: bash deploy/setup.sh
set -e

echo "=== Installing Docker ==="
sudo apt-get update -y
sudo apt-get install -y docker.io docker-compose-plugin awscli nginx
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker "$USER"

echo "=== Creating app directory ==="
sudo mkdir -p /opt/autofix
sudo chown "$USER":"$USER" /opt/autofix

echo "=== Configuring nginx ==="
sudo cp "$(dirname "$0")/nginx.conf" /etc/nginx/sites-available/autofix
sudo ln -sf /etc/nginx/sites-available/autofix /etc/nginx/sites-enabled/autofix
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

echo ""
echo "=== Setup complete. Next steps ==="
echo "1. Copy your .env file to /opt/autofix/.env"
echo "2. Copy docker-compose.yml to /opt/autofix/docker-compose.yml"
echo "3. Log out and back in (for docker group to take effect)"
echo "4. Authenticate to ECR:"
echo "   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <ecr-url>"
echo "5. Start the app:"
echo "   cd /opt/autofix && ECR_IMAGE=<ecr-repo>:latest docker compose up -d"
