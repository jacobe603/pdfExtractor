#!/bin/bash

# Network Drive Mount Script with Authentication
# Supports both SMB/CIFS network shares and Windows drives

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOUNT_POINT="/mnt/s"
CREDENTIALS_FILE="$HOME/.smbcredentials"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        echo -e "${RED}Error: This script must be run with sudo${NC}"
        echo "Usage: sudo $0 [setup|mount|test]"
        exit 1
    fi
}

# Function to setup credentials
setup_credentials() {
    echo -e "${BLUE}=== Network Drive Credentials Setup ===${NC}"
    echo ""
    
    # Check if credentials file exists
    if [ -f "$CREDENTIALS_FILE" ]; then
        echo -e "${YELLOW}Credentials file already exists at: $CREDENTIALS_FILE${NC}"
        read -p "Do you want to update it? (y/n): " update
        if [[ ! "$update" =~ ^[Yy]$ ]]; then
            return 0
        fi
    fi
    
    # Get network share information
    echo -e "${GREEN}Enter your network drive information:${NC}"
    read -p "Network share path (e.g., //server/share or S:): " SHARE_PATH
    read -p "Username: " USERNAME
    read -s -p "Password: " PASSWORD
    echo ""
    read -p "Domain (press Enter if none): " DOMAIN
    
    # Create credentials file
    cat > "$CREDENTIALS_FILE" << EOF
username=$USERNAME
password=$PASSWORD
EOF
    
    if [ -n "$DOMAIN" ]; then
        echo "domain=$DOMAIN" >> "$CREDENTIALS_FILE"
    fi
    
    # Secure the credentials file
    chmod 600 "$CREDENTIALS_FILE"
    chown $(logname):$(logname) "$CREDENTIALS_FILE"
    
    echo -e "${GREEN}✓ Credentials saved securely${NC}"
    
    # Save share path for mounting
    echo "$SHARE_PATH" > "$SCRIPT_DIR/.share_path"
    chmod 600 "$SCRIPT_DIR/.share_path"
}

# Function to mount network drive
mount_drive() {
    echo -e "${BLUE}=== Mounting Network Drive ===${NC}"
    
    # Check for credentials
    if [ ! -f "$CREDENTIALS_FILE" ]; then
        echo -e "${RED}Error: No credentials found${NC}"
        echo "Please run: sudo $0 setup"
        exit 1
    fi
    
    # Get share path
    if [ -f "$SCRIPT_DIR/.share_path" ]; then
        SHARE_PATH=$(cat "$SCRIPT_DIR/.share_path")
    else
        read -p "Enter network share path (e.g., //server/share or S:): " SHARE_PATH
    fi
    
    # Create mount point if needed
    mkdir -p "$MOUNT_POINT"
    
    # Determine mount type and execute
    if [[ "$SHARE_PATH" =~ ^//.*$ ]]; then
        # SMB/CIFS network share
        echo -e "${YELLOW}Mounting SMB/CIFS share: $SHARE_PATH${NC}"
        
        # Check if cifs-utils is installed
        if ! command -v mount.cifs &> /dev/null; then
            echo -e "${YELLOW}Installing cifs-utils...${NC}"
            apt-get update && apt-get install -y cifs-utils
        fi
        
        # Mount with credentials
        mount -t cifs "$SHARE_PATH" "$MOUNT_POINT" \
            -o credentials="$CREDENTIALS_FILE",uid=$(id -u $(logname)),gid=$(id -g $(logname)),iocharset=utf8,file_mode=0777,dir_mode=0777
            
    elif [[ "$SHARE_PATH" =~ ^[A-Z]:$ ]]; then
        # Windows drive letter
        echo -e "${YELLOW}Mounting Windows drive: $SHARE_PATH${NC}"
        
        # For Windows drives in WSL, we typically don't need credentials
        # But if it's a network mapped drive, we might need special handling
        mount -t drvfs "$SHARE_PATH" "$MOUNT_POINT"
        
    else
        echo -e "${RED}Error: Invalid share path format${NC}"
        echo "Expected format: //server/share or X:"
        exit 1
    fi
    
    # Check if mount was successful
    if mount | grep -q "$MOUNT_POINT"; then
        echo -e "${GREEN}✓ Drive successfully mounted at $MOUNT_POINT${NC}"
        echo ""
        echo "Contents:"
        ls -la "$MOUNT_POINT" | head -10
    else
        echo -e "${RED}✗ Failed to mount drive${NC}"
        echo ""
        echo "Troubleshooting tips:"
        echo "1. Check network connectivity"
        echo "2. Verify credentials are correct"
        echo "3. Ensure the share path is accessible"
        echo "4. For Windows drives, make sure WSL can access them"
        exit 1
    fi
}

# Function to unmount drive
unmount_drive() {
    echo -e "${YELLOW}Unmounting $MOUNT_POINT...${NC}"
    
    if mount | grep -q "$MOUNT_POINT"; then
        umount "$MOUNT_POINT"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Drive unmounted successfully${NC}"
        else
            echo -e "${RED}Failed to unmount. Trying force unmount...${NC}"
            umount -f "$MOUNT_POINT"
        fi
    else
        echo -e "${YELLOW}Drive is not currently mounted${NC}"
    fi
}

# Function to test connection
test_connection() {
    echo -e "${BLUE}=== Testing Network Drive Connection ===${NC}"
    
    if mount | grep -q "$MOUNT_POINT"; then
        echo -e "${GREEN}✓ Drive is currently mounted${NC}"
        echo ""
        echo "Mount details:"
        mount | grep "$MOUNT_POINT"
        echo ""
        echo "Space usage:"
        df -h "$MOUNT_POINT"
    else
        echo -e "${YELLOW}Drive is not mounted${NC}"
        echo "Run 'sudo $0 mount' to mount the drive"
    fi
}

# Function to add to fstab for permanent mounting
add_to_fstab() {
    echo -e "${BLUE}=== Adding to /etc/fstab for Permanent Mounting ===${NC}"
    
    if [ ! -f "$CREDENTIALS_FILE" ]; then
        echo -e "${RED}Error: Setup credentials first${NC}"
        exit 1
    fi
    
    if [ ! -f "$SCRIPT_DIR/.share_path" ]; then
        echo -e "${RED}Error: No share path found. Run setup first.${NC}"
        exit 1
    fi
    
    SHARE_PATH=$(cat "$SCRIPT_DIR/.share_path")
    
    # Check if already in fstab
    if grep -q "$MOUNT_POINT" /etc/fstab; then
        echo -e "${YELLOW}Entry already exists in /etc/fstab${NC}"
        return 0
    fi
    
    # Add entry based on type
    if [[ "$SHARE_PATH" =~ ^//.*$ ]]; then
        echo "$SHARE_PATH $MOUNT_POINT cifs credentials=$CREDENTIALS_FILE,uid=$(id -u $(logname)),gid=$(id -g $(logname)),iocharset=utf8,file_mode=0777,dir_mode=0777 0 0" >> /etc/fstab
    elif [[ "$SHARE_PATH" =~ ^[A-Z]:$ ]]; then
        echo "$SHARE_PATH $MOUNT_POINT drvfs defaults 0 0" >> /etc/fstab
    fi
    
    echo -e "${GREEN}✓ Added to /etc/fstab${NC}"
    echo "The drive will now mount automatically on system startup"
}

# Main menu
case "$1" in
    setup)
        check_root
        setup_credentials
        ;;
    mount)
        check_root
        mount_drive
        ;;
    unmount|umount)
        check_root
        unmount_drive
        ;;
    test)
        test_connection
        ;;
    permanent)
        check_root
        add_to_fstab
        ;;
    *)
        echo "Network Drive Mount Manager"
        echo ""
        echo "Usage: $0 {setup|mount|unmount|test|permanent}"
        echo ""
        echo "Commands:"
        echo "  setup     - Configure network drive credentials"
        echo "  mount     - Mount the network drive"
        echo "  unmount   - Unmount the network drive"
        echo "  test      - Test if drive is mounted"
        echo "  permanent - Add to fstab for automatic mounting"
        echo ""
        echo "Quick start:"
        echo "  1. sudo $0 setup    (configure credentials)"
        echo "  2. sudo $0 mount    (mount the drive)"
        echo "  3. sudo $0 permanent (optional: auto-mount on boot)"
        exit 1
        ;;
esac

exit 0