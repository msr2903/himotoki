#!/bin/bash
# Script to fork himotoki to himotoki-split

TARGET_DIR="../himotoki-split"

echo "Creating fork at $TARGET_DIR..."

# Create target directory
mkdir -p "$TARGET_DIR"

# Rsync files, excluding heavy/unnecessary items
rsync -av \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.DS_Store' \
  --exclude 'himotoki.db' \
  --exclude '*.egg-info' \
  --exclude 'dist' \
  --exclude 'build' \
  --exclude '.pytest_cache' \
  --exclude 'fork_project.sh' \
  . "$TARGET_DIR"

echo "---------------------------------------------------"
echo "Fork created successfully at $TARGET_DIR"
echo "Please open this new directory in your editor to proceed."
echo "---------------------------------------------------"
