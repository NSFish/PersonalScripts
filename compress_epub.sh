#!/opt/homebrew/bin/bash

# 检查是否提供了文件夹名称参数
if [ $# -eq 0 ]; then
    echo "请提供要压缩的文件夹名称，例如：./compress_to_epub.sh 我的书籍文件夹"
    exit 1
fi

# 压缩文件夹，排除隐藏文件和__MACOSX目录
zip -r "$1.zip" "$1" -x "*/\.*" -x "__MACOSX"

# 检查压缩是否成功
if [ $? -eq 0 ]; then
    # 重命名为EPUB格式
    mv "$1.zip" "$1.epub"
    echo "压缩完成，输出文件为 $1.epub"
else
    echo "压缩失败，请检查文件夹是否存在或权限是否正确"
    exit 1
fi