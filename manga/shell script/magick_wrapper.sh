#!/opt/homebrew/bin/bash
set -euo pipefail  # 开启严格模式，捕获未定义变量/命令失败/管道错误

# ===================== 配置与常量定义 =====================
SCRIPT_NAME=$(basename "$0")
MAGICK_CMD="magick"
BREW_INSTALL_URL="https://brew.sh/"
DEFAULT_EXT="jpg"  # 默认转换格式

# ===================== 函数定义 =====================
# 打印脚本使用说明
print_usage() {
    echo "用法: $SCRIPT_NAME <图片路径> [目标扩展名]"
    echo "示例:"
    echo "  $SCRIPT_NAME ~/Pictures/test.webp        # 默认转换为 test.jpg"
    echo "  $SCRIPT_NAME ~/Pictures/test.webp png   # 转换为 test.png"
    echo "  $SCRIPT_NAME ./photo.png webp           # 转换为 photo.webp"
    echo "注意:"
    echo "  1. 若省略目标扩展名，默认转换为 ${DEFAULT_EXT} 格式"
    echo "  2. 目标扩展名无需带点（如输入 jpg 而非 .jpg）"
    echo "  3. 转换后的文件会保存在原图片同目录下，文件名与原图一致仅扩展名变更"
    echo "  4. 若原图扩展名与目标扩展名一致（忽略大小写），则不执行任何操作"
}

# 检查 ImageMagick 是否安装
check_imagemagick() {
    if ! command -v "$MAGICK_CMD" &> /dev/null; then
        echo "错误: 未检测到 ImageMagick (magick 命令)，请先安装！"
        echo "macOS 下可通过 Homebrew 安装："
        echo "  1. 若未安装 Homebrew，请先执行：/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        echo "  2. 安装 ImageMagick：brew install imagemagick"
        exit 1
    fi
}

# 提取并标准化文件扩展名（去掉点 + 转小写）
get_normalized_ext() {
    local filename="$1"
    # 提取扩展名（无则为空）
    local ext="${filename##*.}"
    # 如果文件名就是扩展名（如无点的文件），返回空
    if [ "$ext" = "$filename" ]; then
        echo ""
        return
    fi
    # 标准化：去掉可能的前置点 + 转小写
    echo "${ext#.}" | tr '[:upper:]' '[:lower:]'
}

# 校验输入参数并设置目标扩展名
validate_params() {
    # 检查参数数量（仅支持 1 个或 2 个参数）
    if [ $# -lt 1 ] || [ $# -gt 2 ]; then
        echo "错误: 参数数量不正确！"
        print_usage
        exit 1
    fi

    # 检查图片文件是否存在
    local image_path="$1"
    if [ ! -f "$image_path" ]; then
        echo "错误: 图片文件不存在 → $image_path"
        exit 1
    fi

    # 设置目标扩展名（处理默认值 + 清理前置点 + 转小写）
    if [ $# -eq 1 ]; then
        target_ext=$(echo "$DEFAULT_EXT" | tr '[:upper:]' '[:lower:]')
    else
        # 清理前置点 + 转小写
        target_ext=$(echo "${2#.}" | tr '[:upper:]' '[:lower:]')
        # 检查扩展名是否为空
        if [ -z "$target_ext" ]; then
            echo "错误: 目标扩展名不能为空！"
            exit 1
        fi
    fi

    # 提取并标准化原始文件的扩展名
    original_filename=$(basename "$image_path")
    original_ext=$(get_normalized_ext "$original_filename")

    # 对比扩展名：如果一致则直接退出（无操作）
    if [ "$original_ext" = "$target_ext" ]; then
        echo "ℹ️  原图扩展名（$original_ext）与目标扩展名（$target_ext）一致，无需转换"
        exit 0
    fi
}

# 执行图片格式转换
convert_image() {
    local original_path="$1"
    local target_ext="$2"

    # 解析文件路径组件
    local dir=$(dirname "$original_path")       # 文件所在目录
    local filename=$(basename "$original_path") # 带扩展名的文件名
    local filename_no_ext="${filename%.*}"      # 去掉扩展名的文件名

    # 构建新文件路径
    local new_path="${dir}/${filename_no_ext}.${target_ext}"

    # 避免覆盖已有文件（可选：如果需要覆盖，可删除此段）
    if [ -f "$new_path" ]; then
        read -p "警告: 目标文件已存在 → $new_path，是否覆盖？(y/N) " confirm
        if [[ ! $confirm =~ ^[Yy]$ ]]; then
            echo "转换取消"
            exit 0
        fi
    fi

    # 执行转换命令
    echo "正在转换: $original_path → $new_path"
    if "$MAGICK_CMD" "$original_path" "$new_path"; then
        echo "✅ 转换成功！生成文件：$new_path"
    else
        echo "❌ 转换失败！"
        exit 1
    fi
}

# ===================== 主流程 =====================
main() {
    # 1. 校验输入参数 + 检查扩展名是否一致
    validate_params "$@"
    
    # 2. 检查 ImageMagick 依赖
    check_imagemagick
    
    # 3. 执行转换
    convert_image "$1" "$target_ext"
}

# 启动主流程
main "$@"