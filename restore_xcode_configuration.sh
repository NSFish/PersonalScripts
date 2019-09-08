#!/bin/bash

Backup_Path="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Xcode"
Xcode_config_path="$HOME/Library/Developer/Xcode"

echo "Restoring code snippets..."
ln -s "$Backup_Path/CodeSnippets" "$Xcode_config_path/UserData"
echo "Restoring user breakpoints..."
ln -s "$Backup_Path/XcodeUserData/xcdebugger" "$Xcode_config_path/UserData/xcdebugger"
echo "Restoring templates..."
ln -s "$Backup_Path/Empty Application.xctemplate" "$Xcode_config_path/Templates/Project Templates/Application"
echo "Restoring font and color themes..."
ln -s "$Backup_Path/XcodeUserData/FontAndColorThemes" "$Xcode_config_path/UserData"
echo "All set!"