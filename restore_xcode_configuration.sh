#!/bin/bash

Backup_Path="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Xcode"
Xcode_config_path="$HOME/Library/Developer/Xcode"

echo "Restoring code snippets..."
ln -s "$Backup_Path/UserData/CodeSnippets" "$Xcode_config_path/UserData"
echo "Restoring user breakpoints..."
ln -s "$Backup_Path/UserData/xcdebugger" "$Xcode_config_path/UserData"
echo "Restoring font and color themes..."
ln -s "$Backup_Path/UserData/FontAndColorThemes" "$Xcode_config_path/UserData"
echo "Restoring templates..."
ln -s "$Backup_Path/Templates" "$Xcode_config_path"
echo "All set!"