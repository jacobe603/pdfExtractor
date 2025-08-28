#!/bin/bash

# Script to mount the S: drive
# This needs to be run with sudo privileges

if [ "$EUID" -ne 0 ]; then 
    echo "Please run this script with sudo:"
    echo "  sudo ./mount_s_drive.sh"
    exit 1
fi

echo "Mounting S: drive to /mnt/s..."

# Create mount point if it doesn't exist
mkdir -p /mnt/s

# Mount the drive
mount -t drvfs S: /mnt/s

# Check if mount was successful
if mount | grep -q "/mnt/s"; then
    echo "✓ S: drive successfully mounted at /mnt/s"
    ls -la /mnt/s | head -5
else
    echo "✗ Failed to mount S: drive"
    echo ""
    echo "Troubleshooting:"
    echo "1. Make sure S: is a valid Windows drive"
    echo "2. Try running: wsl --shutdown (in Windows PowerShell)"
    echo "3. Then restart WSL"
    exit 1
fi