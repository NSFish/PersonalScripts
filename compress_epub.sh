#!/opt/homebrew/bin/bash

zip -r "$1.zip" "$1" -x "*/\.*" -x "__MACOSX"
echo "压缩完成，输出文件为 $1.zip"