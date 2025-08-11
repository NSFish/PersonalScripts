#!/opt/homebrew/bin/bash

# 检查是否提供了文件夹名称参数
if [ $# -eq 0 ]; then
    echo "请提供要压缩的文件夹名称，例如：./compress_to_epub.sh 我的书籍文件夹"
    exit 1
fi

# 检查文件夹是否存在
if [ ! -d "$1" ]; then
    echo "错误：文件夹 '$1' 不存在"
    exit 1
fi

# 压缩文件夹内的所有内容（不含外层文件夹本身），排除隐藏文件和__MACOSX
# 使用 "$1"/* 确保只压缩文件夹内的内容，而非文件夹本身
zip -r "$1.epub" "$1"/* -x "*/\.*" -x "__MACOSX" -x "$1/__MACOSX"

# 检查压缩是否成功
if [ $? -eq 0 ]; then
    echo "压缩完成，输出文件为 $1.epub"
else
    echo "压缩失败，请检查文件夹权限或内容是否正常"
    exit 1
fi