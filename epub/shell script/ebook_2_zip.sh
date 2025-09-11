#!/opt/homebrew/bin/bash

# 初始化变量
comic_mode=0

# 解析选项
while [ $# -gt 0 ]; do
    case "$1" in
        -c|--comic)
            comic_mode=1
            shift
            ;;
        *)
            break
            ;;
    esac
done

# 检查输入
if [ $# -ne 1 ]; then
    echo "用法: $0 [-c|--comic] <输入文件.mobi/.epub 或 输入文件夹>"
    echo "选项:"
    echo "  -c, --comic   漫画模式 (仅打包图片内容)"
    exit 1
fi

INPUT="$1"
OUTPUT_ZIP_DIR=""

# 检查依赖工具
if ! command -v ebook-convert &> /dev/null || ! command -v zip &> /dev/null; then
    echo "错误: 请确保安装了 Calibre (含 ebook-convert) 和 zip 工具!"
    exit 1
fi

# 处理单个文件
process_file() {
    local INPUT_FILE="$1"
    local OUTPUT_DIR="$2"
    
    # 获取文件名 (不含扩展名)
    FILENAME=$(basename -- "$INPUT_FILE")
    FILENAME="${FILENAME%.*}"
    
    # 创建临时工作区
    local TMP_DIR=$(mktemp -d)
    local LOG_FILE="${TMP_DIR}/convert.log"
    echo "处理: $INPUT_FILE"
    
    # 根据文件类型处理
    if [[ "$INPUT_FILE" =~ \.[mM][oO][bB][iI]$ ]]; then
        # MOBI 处理流程
        local EPUB_OUTPUT="${TMP_DIR}/${FILENAME}.epub"
        
        # 转换为 EPUB
        echo "→ 转换为 EPUB..."
        if ! ebook-convert "$INPUT_FILE" "$EPUB_OUTPUT" > "$LOG_FILE" 2>&1; then
            echo "错误: EPUB 转换失败!"
            echo "=== 错误日志 ==="
            cat "$LOG_FILE"
            echo "================"
            rm -rf "$TMP_DIR"
            return 1
        fi
        
        # 解压 EPUB 内容
        local UNPACK_DIR="${TMP_DIR}/content"
        mkdir -p "$UNPACK_DIR"
        echo "→ 解压 EPUB 内容..."
        if ! unzip -q -o "$EPUB_OUTPUT" -d "$UNPACK_DIR" 2>/dev/null; then
            echo "错误: EPUB 解压失败!"
            rm -rf "$TMP_DIR"
            return 1
        fi
        
    elif [[ "$INPUT_FILE" =~ \.[eE][pP][uU][bB]$ ]]; then
        # EPUB 直接处理
        local UNPACK_DIR="${TMP_DIR}/content"
        mkdir -p "$UNPACK_DIR"
        
        # 解压原始 EPUB
        echo "→ 解压 EPUB 内容..."
        if ! unzip -q -o "$INPUT_FILE" -d "$UNPACK_DIR" 2>/dev/null; then
            echo "错误: EPUB 解压失败!"
            rm -rf "$TMP_DIR"
            return 1
        fi
    else
        echo "错误: 不支持的文件类型! 仅支持 .mobi 和 .epub 文件。"
        rm -rf "$TMP_DIR"
        return 1
    fi

    # 漫画模式处理: 仅打包图片文件夹
    if [ $comic_mode -eq 1 ]; then
        echo "→ 漫画模式启用 (仅打包图片内容)"
        local IMAGE_DIR=""
        
        # 改进的图片目录查找逻辑
        find_image_dir() {
            local base_dir="$1"
            
            # 检查常见图片目录名称
            for name in "image" "images"; do
                if [ -d "${base_dir}/${name}" ]; then
                    echo "${base_dir}/${name}"
                    return 0
                fi
            done
            
            # 检查一级子目录中的图片目录
            for sub_dir in "$base_dir"/*; do
                if [ -d "$sub_dir" ]; then
                    for name in "image" "images"; do
                        if [ -d "${sub_dir}/${name}" ]; then
                            echo "${sub_dir}/${name}"
                            return 0
                        fi
                    done
                fi
            done
            
            return 1
        }
        
        # 尝试查找图片目录
        IMAGE_DIR=$(find_image_dir "$UNPACK_DIR")
        
        if [ -z "$IMAGE_DIR" ]; then
            echo "错误: 无法找到图片目录 (image/images)"
            rm -rf "$TMP_DIR"
            return 1
        else
            echo "→ 找到图片目录: $(basename "$IMAGE_DIR")"
            # 使用图片目录作为打包源
            UNPACK_DIR="$IMAGE_DIR"
        fi
    fi

    # 打包为 ZIP
    local OUTPUT_ZIP="${OUTPUT_DIR}/${FILENAME}.zip"
    echo "→ 创建 ZIP 包: $(basename "$OUTPUT_ZIP")"
    (cd "$UNPACK_DIR" && zip -q -r -9 "$OUTPUT_ZIP" ./* >/dev/null 2>&1)
    
    # 清理临时文件
    rm -rf "$TMP_DIR"
    echo "√ 处理完成"
    echo ""
    return 0
}

# 主处理逻辑
if [ -f "$INPUT" ]; then
    # 单个文件处理
    OUTPUT_DIR=$(dirname "$INPUT")
    process_file "$INPUT" "$OUTPUT_DIR"
    
elif [ -d "$INPUT" ]; then
    # 文件夹处理
    OUTPUT_DIR="${INPUT}_zip"
    mkdir -p "$OUTPUT_DIR"
    
    echo "处理文件夹: $INPUT"
    if [ $comic_mode -eq 1 ]; then
        echo "模式: 漫画 (仅打包图片内容)"
    fi
    echo "输出目录: $OUTPUT_DIR"
    echo ""
    
    # 查找并处理所有 MOBI/EPUB 文件
    find "$INPUT" -type f \( -iname "*.mobi" -o -iname "*.epub" \) | while read -r file; do
        process_file "$file" "$OUTPUT_DIR"
    done
    
    echo "文件夹转换完成! 输出目录: $OUTPUT_DIR"
else
    echo "错误: '$INPUT' 不是有效的文件或目录!"
    exit 1
fi

exit 0