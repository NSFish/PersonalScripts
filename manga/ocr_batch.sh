#!/opt/homebrew/bin/bash

# 脚本功能：基于 OCR 的图片关键词批量搜索与整理工具
# 
# 核心功能：
# 1. 递归处理指定父目录下的所有子目录
# 2. 使用 Apple Vision OCR 引擎(macos-vision-ocr-arm64)批量识别图片中的文字
# 3. 根据用户提供的关键词筛选包含关键词的图片
# 4. 支持两种操作模式：
#    - 正常模式：移动匹配图片到输出目录
#    - 预览模式(--dry-run)：复制匹配图片到输出目录
# 5. 自动组织输出结构：
#    - 按原始子目录结构组织结果
#    - 在目录名后添加匹配图片数量(如"子目录名（3）")
#    - 保存 OCR 原始结果(JSON 格式)
#    - 记录 OCR 错误日志
#
# 主要特性：
# - 多语言 OCR 支持(默认: 简体中文/繁体中文/英文)
# - 关键词逻辑：图片包含任意关键词即视为匹配
# - 自动化输出目录管理(自动清理旧输出)
# - 详细进度和统计信息
# - 彩色终端输出(匹配项高亮/错误提示)
# - 依赖检查(OCR 工具和 jq)
#
# 使用示例：
#   ./script.sh /path/to/parent 关键词1 关键词2
#   ./script.sh -n -v /path/to/parent 关键词1 关键词2
#
# 选项说明：
#   -n, --dry-run  预览模式(不实际移动文件)
#   -v, --verbose  显示详细处理信息
#   -h, --help     显示帮助文档
#
# 输出目录结构：
#   output/
#     ├── 子目录A（3）/
#     │   ├── 匹配图片 1.jpg
#     │   ├── 匹配图片 2.jpg
#     │   ├── json/
#     │   │   ├── 图片 1.json
#     │   │   └└└└── ...
#     │   └└└└── ocr_errors.log (可选)
#     └└└└── ...
#
# 依赖要求：
#   1. macos-vision-ocr-arm64: Apple Vision OCR 引擎
#   2. jq: JSON 处理工具

# 初始化变量
DRY_RUN=false
PARENT_DIR=""
KEYWORDS=()
VERBOSE=false
REC_LANGS="zh-Hans,zh-Hant,en-US"
OUTPUT_DIR="output"

# ANSI 颜色代码
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # 重置颜色

# 帮助信息
show_help() {
    echo "用法: $0 [选项] <父文件夹路径> <关键词1> <关键词2> ..."
    echo "优化的 OCR 批处理器，固定输出目录为 'output'"
    echo ""
    echo "选项:"
    echo "  -n, --dry-run    预览模式（执行 OCR 但不移动图片，而是复制图片）"
    echo "  -v, --verbose    显示详细处理信息"
    echo "  -h, --help       显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 /path/to/parent 关键词1 关键词2"
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

    # 验证 OCR 工具是否支持批量模式
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
            -n|--dry-run)    DRY_RUN=true; shift ;;
            -v|--verbose)    VERBOSE=true; shift ;;
            -h|--help)       show_help; exit 0 ;;
            *)
                if [ -z "$PARENT_DIR" ]; then
                    PARENT_DIR="${1%/}"
                else
                    KEYWORDS+=("$1")
                fi
                shift
                ;;
        esac
    done

    [ -z "$PARENT_DIR" ] && { echo -e "${RED}错误: 必须指定父文件夹路径${NC}"; show_help; exit 1; }
    [ ${#KEYWORDS[@]} -eq 0 ] && { echo -e "${RED}错误: 至少需要一个关键词${NC}"; show_help; exit 1; }
    [ ! -d "$PARENT_DIR" ] && { echo -e "${RED}错误: 文件夹不存在: $PARENT_DIR${NC}"; exit 1; }

    echo -e "${GREEN}✅ 参数解析完成${NC}"
    echo "   父目录: $PARENT_DIR"
    echo "   关键词: ${KEYWORDS[*]}"
}

# 高亮显示匹配的路径
highlight_match() {
    local path="$1"
    echo -e "${GREEN}$path${NC}"
}

# 处理子目录（处理 JSON 输出）
process_subdir() {
    local sub_dir="$1"
    local sub_name=$(basename "$sub_dir")
    local original_sub_name="$sub_name"
    local sub_output_dir="$OUTPUT_DIR/$sub_name"
    local json_output_dir="$sub_output_dir/json"
    local match_count=0
    local ocr_error_log="$sub_output_dir/ocr_errors.log"

    # 创建输出目录
    mkdir -p "$json_output_dir"

    # 1. 运行批量 OCR 处理
    $VERBOSE && echo "   运行批量 OCR: macos-vision-ocr-arm64 --img-dir \"$sub_dir\" --output-dir \"$json_output_dir\" --rec-langs \"$REC_LANGS\""

    # 临时保存错误输出
    local ocr_errors=""

    # 捕获错误输出
    ocr_errors=$(macos-vision-ocr-arm64 --img-dir "$sub_dir" --output-dir "$json_output_dir" --rec-langs "$REC_LANGS" 2>&1 >/dev/null)

    # 检查 OCR 是否成功
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ OCR 处理失败: $sub_dir${NC}"
        # 将错误写入日志
        echo "$ocr_errors" > "$ocr_error_log"
        cat "$ocr_error_log"
        return 1
    else
        # 如果有错误信息但命令成功，可能是警告
        if [ -n "$ocr_errors" ]; then
            $VERBOSE && echo -e "${YELLOW}⚠️ OCR 处理完成但有警告: $sub_dir${NC}"
            echo "$ocr_errors" > "$ocr_error_log"
            $VERBOSE && cat "$ocr_error_log"
        else
            $VERBOSE && echo -e "${GREEN}✅ OCR 处理成功${NC}"
            # 删除空的错误日志（如果有）
            [ -f "$ocr_error_log" ] && rm -f "$ocr_error_log"
        fi
    fi

    # 2. 处理 JSON 文件并查找关键词
    local found_keyword=false

    # 遍历所有 JSON 文件
    while IFS= read -r json_file; do
        [ -f "$json_file" ] || continue

        local json_filename=$(basename "$json_file")
        local img_name="${json_filename%.json}"
        local img_path="$sub_dir/$img_name"

        # 读取 JSON 内容
        local json_content=$(cat "$json_file")
        local ocr_text=$(echo "$json_content" | jq -r '.texts')

        $VERBOSE && echo "   处理文件: $img_name"
        $VERBOSE && echo "   OCR 结果: ${ocr_text:0:50}..." # 只显示前 50 个字符

        # 关键词检查
        local keyword_found=false
        for keyword in "${KEYWORDS[@]}"; do
            if [[ "$ocr_text" == *"$keyword"* ]]; then
                $VERBOSE && echo "   ✅ 找到关键词: $keyword"
                keyword_found=true
                found_keyword=true
                break
            fi
        done

        # 如果找到关键词，根据模式复制或移动图片并高亮显示路径
        if [ "$keyword_found" = true ]; then
            if $DRY_RUN; then
                if [ -f "$img_path" ]; then
                    cp "$img_path" "$sub_output_dir/" && {
                        highlight_match "   预览: 复制 $img_path 到 $sub_output_dir"
                        match_count=$((match_count + 1))
                    }
                else
                    echo -e "${RED}   ❌ 图片不存在: $img_path${NC}"
                fi
            else
                if [ -f "$img_path" ]; then
                    mv "$img_path" "$sub_output_dir/" && {
                        highlight_match "   匹配图片: $img_path 已移动到 $sub_output_dir"
                        match_count=$((match_count + 1))
                    }
                else
                    echo -e "${RED}   ❌ 图片不存在: $img_path${NC}"
                fi
            fi
        fi
    done < <(find "$json_output_dir" -type f -name "*.json")

    # 3. 更新文件夹名称（如果找到匹配）
    if [ "$found_keyword" = true ] && [ $match_count -gt 0 ]; then
        # 创建新的文件夹名称（添加匹配数量）
        local new_sub_name="${original_sub_name}（${match_count}）"
        local new_sub_output_dir="$OUTPUT_DIR/$new_sub_name"

        # 重命名文件夹（不打印重命名消息）
        if [ "$sub_output_dir" != "$new_sub_output_dir" ]; then
            mv "$sub_output_dir" "$new_sub_output_dir"
        fi

        # 打印匹配统计
        echo -e "${GREEN}✅ $original_sub_name 中找到 $match_count 张匹配图片${NC}"
    else
        echo -e "${YELLOW}⚠️ $sub_name 中未找到匹配图片${NC}"
        # 清理空目录
        if [ -d "$sub_output_dir" ] && [ ! $DRY_RUN ]; then
            rm -rf "$sub_output_dir"
        fi
    fi

    echo "----------------------------------------"
}

# 主程序
main() {
    parse_args "$@"
    check_dependencies

    # 创建输出目录
    if [ -d "$OUTPUT_DIR" ]; then
        rm -rf "$OUTPUT_DIR"
    fi
    mkdir -p "$OUTPUT_DIR"
    echo -e "${GREEN}📁 创建输出目录: $OUTPUT_DIR${NC}"

    # 记录开始时间
    local start_time
    start_time=$(date +%s)

    # 获取所有子目录并按文件夹名排序
    local subdirs=()
    while IFS= read -r -d $'\0' dir; do
        subdirs+=("$dir")
    done < <(find "$PARENT_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
    local total_dirs=${#subdirs[@]}

    if [ $total_dirs -eq 0 ]; then
        echo -e "${RED}❌ 在 $PARENT_DIR 中找不到子目录${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ 找到 $total_dirs 个子目录（已排序）${NC}"

    # 处理子目录
    local processed=0
    for sub_dir in "${subdirs[@]}"; do
        processed=$((processed + 1))
        echo "🔄 处理进度: $processed/$total_dirs - $(basename "$sub_dir")"
        process_subdir "$sub_dir"
    done

    # 计算耗时
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    printf "\n${GREEN}✅ 处理完成! 耗时: %d 分 %d 秒${NC}\n" $((duration/60)) $((duration%60))
    echo "处理了 $total_dirs 个子目录"

    # 统计结果
    local output_dirs=$(find "$OUTPUT_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
    echo "输出文件夹包含 $output_dirs 个子目录"
}

# 启动主程序
main "$@"