#!/usr/bin/env bash
# Capacity snapshot for the 1 GB Lightsail host. No secrets.
set -Eeuo pipefail

echo "=== free -h ==="
free -h
echo
echo "=== swapon --show ==="
swapon --show || true
echo
echo "=== df -h / ==="
df -h /
echo
echo "=== docker stats --no-stream ==="
docker stats --no-stream || true
echo
echo "=== docker system df ==="
docker system df || true
