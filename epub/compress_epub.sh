#!/opt/homebrew/bin/bash

# 1. 检查参数
if [ $# -eq 0 ]; then
    echo "用法：$0 源文件夹路径（例如：/Users/my/Desktop/myepub）"
    exit 1
fi

target_dir="$1"

# 2. 检查源文件夹存在
if [ ! -d "$target_dir" ]; then
    echo "错误：文件夹 '$target_dir' 不存在"
    exit 1
fi

# 3. 检查EPUB核心文件（必含项）
required_files=(
    "${target_dir}/mimetype"           # 必须存在，内容为 `application/epub+zip`
    "${target_dir}/META-INF/container.xml"  # 必须存在，指向内容入口
)
for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        echo "错误：缺少EPUB必需文件 '$file'"
        exit 1
    fi
done

# 4. 分解路径（父目录 + 源文件夹名）
parent_dir=$(dirname "$target_dir")  # 例如：/Users/my/Desktop
dir_name=$(basename "$target_dir")   # 例如：myepub

# 5. 进入源文件夹内部（关键：确保压缩的是内部文件，而非父文件夹）
cd "$target_dir" || {
    echo "错误：无法进入源文件夹 '$target_dir'"
    exit 1
}

# 6. 第一步：单独添加 `mimetype`（无压缩 + 作为第一个文件）
#    压缩到父目录下的zip文件，避免路径包含源文件夹
zip -0Xq "${parent_dir}/${dir_name}.zip" mimetype

# 7. 第二步：添加其他内容（META-INF、OEBPS等，递归压缩）
zip -rXq "${parent_dir}/${dir_name}.zip" META-INF OEBPS

# 8. 重命名为.epub
mv "${parent_dir}/${dir_name}.zip" "${parent_dir}/${dir_name}.epub"

# 9. 切回原工作目录
cd - > /dev/null || exit

echo "✅ EPUB生成成功！路径：${parent_dir}/${dir_name}.epub"
echo "💡 已确保：mimetype未压缩且是第一个条目，且内容直接在EPUB根目录（无外层文件夹）。"