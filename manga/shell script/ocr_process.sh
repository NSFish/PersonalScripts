#!/opt/homebrew/bin/bash

# OCR 批量处理器
# 功能：递归处理目录中的图片，使用OCR识别文字并保存为JSON文件
#
# 使用示例：
#   ./ocr_processor.sh /path/to/parent
#
# 选项说明：
#   -v, --verbose  显示详细处理信息
#   -h, --help     显示帮助文档
#
# 输出结构：
#   <父目录的父目录>/<输入目录名>_ocr_result/
#     ├── 子目录A/
#     │   ├── 图片1.json
#     │   └└── ...
#     └└── ...

# 初始化变量
PARENT_DIR=""
VERBOSE=false
REC_LANGS="zh-Hans,zh-Hant,en-US"
OUTPUT_DIR=""

# ANSI 颜色代码
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # 重置颜色

# 帮助信息
show_help() {
    echo "用法: $0 [选项] <父文件夹路径>"
    echo "图片 OCR 处理器，输出目录为 <父目录的父目录>/<输入目录名>_ocr_result"
    echo ""
    echo "选项:"
    echo "  -v, --verbose    显示详细处理信息"
    echo "  -h, --help       显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 /path/to/parent  # 输出目录为 /path/to/parent_ocr_result"
}

# 检查依赖
check_dependencies() {
    ! command -v macos-vision-ocr-arm64 &>/dev/null && {
        echo -e "${RED}错误: 未找到 macos-vision-ocr-arm64${NC}"
        echo "请确保 OCR 工具已正确安装"
        exit 1
    }

    ! command -v jq &>/dev/null && {
        echo -e "${RED}错误: 未找到 jq${NC}"
        echo "请安装: brew install jq"
        exit 1
    }

    if ! macos-vision-ocr-arm64 --help 2>&1 | grep -q "\--img-dir"; then
        echo -e "${RED}错误: OCR 工具不支持批量模式 (缺少 --img-dir 参数)${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ 所有依赖已安装并支持批量模式${NC}"
}

# 解析参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -v|--verbose)    VERBOSE=true; shift ;;
            -h|--help)       show_help; exit 0 ;;
            *)
                [ -z "$PARENT_DIR" ] && PARENT_DIR="${1%/}"
                shift
                ;;
        esac
    done

    [ -z "$PARENT_DIR" ] && { echo -e "${RED}错误: 必须指定父文件夹路径${NC}"; show_help; exit 1; }
    [ ! -d "$PARENT_DIR" ] && { echo -e "${RED}错误: 文件夹不存在: $PARENT_DIR${NC}"; exit 1; }

    echo -e "${GREEN}✅ 参数解析完成${NC}"
    echo "   父目录: $PARENT_DIR"
}

# 处理子目录（执行OCR）
process_subdir() {
    local sub_dir="$1"
    local sub_name=$(basename "$sub_dir")
    local sub_output_dir="$OUTPUT_DIR/$sub_name"
    local ocr_error_log="$sub_output_dir/ocr_errors.log"

    # 创建输出目录
    mkdir -p "$sub_output_dir"

    # 运行批量 OCR 处理
    $VERBOSE && echo "   运行批量 OCR: macos-vision-ocr-arm64 --img-dir \"$sub_dir\" --output-dir \"$sub_output_dir\" --rec-langs \"$REC_LANGS\""

    # 临时保存错误输出
    local ocr_errors=""
    ocr_errors=$(macos-vision-ocr-arm64 --img-dir "$sub_dir" --output-dir "$sub_output_dir" --rec-langs "$REC_LANGS" 2>&1 >/dev/null)

    # 检查 OCR 是否成功
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌❌ OCR 处理失败: $sub_dir${NC}"
        echo "$ocr_errors" > "$ocr_error_log"
        cat "$ocr_error_log"
        return 1
    else
        if [ -n "$ocr_errors" ]; then
            $VERBOSE && echo -e "${YELLOW}⚠️ OCR 处理完成但有警告: $sub_dir${NC}"
            echo "$ocr_errors" > "$ocr_error_log"
            $VERBOSE && cat "$ocr_error_log"
        else
            $VERBOSE && echo -e "${GREEN}✅ OCR 处理成功${NC}"
            [ -f "$ocr_error_log" ] && rm -f "$ocr_error_log"
        fi
    fi

    echo "----------------------------------------"
}

# 主程序
main() {
    parse_args "$@"
    check_dependencies

    # 设置输出目录（使用输入目录名 + _ocr_result）
    local parent_dir_name=$(basename "$PARENT_DIR")  # 获取输入目录的名称
    OUTPUT_BASE=$(dirname "$PARENT_DIR")             # 获取输入目录的父目录
    OUTPUT_DIR="$OUTPUT_BASE/${parent_dir_name}_ocr_result"  # 组合输出目录路径
    
    # 创建输出目录（若已存在则先删除）
    if [ -d "$OUTPUT_DIR" ]; then
        rm -rf "$OUTPUT_DIR"
    fi
    mkdir -p "$OUTPUT_DIR"
    echo -e "${GREEN}📁📁 创建输出目录: $OUTPUT_DIR${NC}"

    # 记录开始时间
    local start_time
    start_time=$(date +%s)

    # 获取所有子目录
    local subdirs=()
    while IFS= read -r -d $'\0' dir; do
        subdirs+=("$dir")
    done < <(find "$PARENT_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
    local total_dirs=${#subdirs[@]}

    if [ $total_dirs -eq 0 ]; then
        echo -e "${RED}❌❌ 在 $PARENT_DIR 中找不到子目录${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ 找到 $total_dirs 个子目录${NC}"

    # 处理子目录
    local processed=0
    for sub_dir in "${subdirs[@]}"; do
        processed=$((processed + 1))
        echo "🔄🔄 处理进度: $processed/$total_dirs - $(basename "$sub_dir")"
        process_subdir "$sub_dir"
    done

    # 计算耗时
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    printf "\n${GREEN}✅ OCR 处理完成! 耗时: %d 分 %d 秒${NC}\n" $((duration/60)) $((duration%60))
    echo "处理了 $total_dirs 个子目录"
    
    # 输出结果位置
    echo -e "${GREEN}📁📁 OCR 结果保存在: $OUTPUT_DIR${NC}"
}

# 启动主程序
main "$@"