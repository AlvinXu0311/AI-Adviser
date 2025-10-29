#!/bin/bash
# Database backup script

set -e

# Configuration
DB_PATH="${DB_PATH:-database/data/mis520.db}"
BACKUP_DIR="database/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/mis520_backup_$TIMESTAMP.db"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "[ERROR] Database file not found: $DB_PATH"
    exit 1
fi

# Create backup
echo "[INFO] Creating backup of $DB_PATH..."
cp "$DB_PATH" "$BACKUP_FILE"

# Compress backup
echo "[INFO] Compressing backup..."
gzip "$BACKUP_FILE"
BACKUP_FILE="$BACKUP_FILE.gz"

echo "[SUCCESS] Backup created: $BACKUP_FILE"
echo "[INFO] Backup size: $(du -h $BACKUP_FILE | cut -f1)"

# Keep only last 7 backups
echo "[INFO] Cleaning old backups (keeping last 7)..."
ls -t $BACKUP_DIR/mis520_backup_*.gz | tail -n +8 | xargs -r rm

echo "[SUCCESS] Backup complete!"
