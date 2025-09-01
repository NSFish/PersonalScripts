#!/opt/homebrew/bin/bash

# 图片关键词匹配器
# 功能：基于OCR结果筛选包含关键词的图片
#
# 修改说明：
# 1. 适配新的OCR目录结构（无中间json目录）
# 2. 空OCR文本视为不匹配（不报错）
# 3. 图片不存在时不报错，仅打印提示
#
# 使用示例：
#   ./keyword_matcher.sh /path/to/parent /path/to/ocr_output 关键词1 关键词2
#   ./keyword_matcher.sh -n -v /path/to/parent /path/to/ocr_output 关键词1 关键词2
#
# 参数说明：
#   1. 原始图片的父目录
#   2. OCR处理结果目录（直接包含.json文件）
#   3. 关键词列表(一个或多个)
#
# 选项说明：
#   -n, --dry-run  预览模式(不实际移动文件)
#   -v, --verbose  显示详细处理信息
#   -h, --help     显示帮助文档
#
# 输出目录结构：
#   <父目录的父目录>/keyword_output/
#     ├── 子目录A（3）/
#     │   ├── 匹配图片1.jpg
#     │   └── ...
#     └── ...

# 初始化变量
DRY_RUN=false
PARENT_DIR=""
OCR_DIR=""
KEYWORDS=()
VERBOSE=false
OUTPUT_DIR=""

# ANSI 颜色代码
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # 重置颜色

# 帮助信息
show_help() {
    echo "用法: $0 [选项] <原始图片父目录> <OCR结果目录> <关键词1> <关键词2> ..."
    echo "图片关键词匹配器，输出目录为 <原始图片父目录的父目录>/keyword_output"
    echo ""
    echo "修改说明："
    echo "  - OCR目录直接包含JSON文件（无中间json目录）"
    echo "  - 空OCR文本视为不匹配（不报错）"
    echo "  - 图片不存在时不报错，仅打印提示"
    echo ""
    echo "选项:"
    echo "  -n, --dry-run    预览模式（不实际移动图片）"
    echo "  -v, --verbose    显示详细处理信息"
    echo "  -h, --help       显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 /path/to/parent /path/to/ocr_output 关键词1 关键词2"
    echo "  $0 -n -v /path/to/parent /path/to/ocr_output 关键词1 关键词2"
}

# 检查依赖
check_dependencies() {
    ! command -v jq &>/dev/null && {
        echo -e "${RED}错误: 未找到 jq${NC}"
        echo "请安装: brew install jq"
        exit 1
    }

    echo -e "${GREEN}✅ 所有依赖已安装${NC}"
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
                elif [ -z "$OCR_DIR" ]; then
                    OCR_DIR="${1%/}"
                else
                    KEYWORDS+=("$1")
                fi
                shift
                ;;
        esac
    done

    [ -z "$PARENT_DIR" ] && { echo -e "${RED}错误: 必须指定原始图片父目录${NC}"; show_help; exit 1; }
    [ -z "$OCR_DIR" ] && { echo -e "${RED}错误: 必须指定OCR结果目录${NC}"; show_help; exit 1; }
    [ ${#KEYWORDS[@]} -eq 0 ] && { echo -e "${RED}错误: 至少需要一个关键词${NC}"; show_help; exit 1; }
    
    [ ! -d "$PARENT_DIR" ] && { echo -e "${RED}错误: 原始图片目录不存在: $PARENT_DIR${NC}"; exit 1; }
    [ ! -d "$OCR_DIR" ] && { echo -e "${RED}错误: OCR目录不存在: $OCR_DIR${NC}"; exit 1; }

    echo -e "${GREEN}✅ 参数解析完成${NC}"
    echo "   原始图片目录: $PARENT_DIR"
    echo "   OCR目录: $OCR_DIR"
    echo "   关键词: ${KEYWORDS[*]}"
}

# 高亮显示匹配项
highlight_match() {
    local path="$1"
    echo -e "${GREEN}$path${NC}"
}

# 处理子目录（关键词匹配）
process_subdir() {
    local sub_name="$1"
    local sub_dir="$PARENT_DIR/$sub_name"
    local ocr_sub_dir="$OCR_DIR/$sub_name"
    local match_count=0

    # 检查OCR结果是否存在
    [ ! -d "$ocr_sub_dir" ] && {
        $VERBOSE && echo -e "${YELLOW}⚠️ 跳过: $sub_name (无OCR结果)${NC}"
        return
    }

    # 创建输出目录
    local sub_output_dir="$OUTPUT_DIR/$sub_name"
    mkdir -p "$sub_output_dir"

    # 处理JSON文件
    local found_keyword=false
    local json_files=()
    while IFS= read -r -d $'\0' file; do
        json_files+=("$file")
    done < <(find "$ocr_sub_dir" -type f -name "*.json" -print0 2>/dev/null)
    
    [ ${#json_files[@]} -eq 0 ] && {
        $VERBOSE && echo -e "${YELLOW}⚠️ 跳过: $sub_name (无JSON文件)${NC}"
        return
    }

    for json_file in "${json_files[@]}"; do
        [ -f "$json_file" ] || continue

        local json_filename=$(basename "$json_file")
        local img_name="${json_filename%.json}"
        local img_path="$sub_dir/$img_name"

        # 读取OCR文本（静默处理空文本）
        local ocr_text=$(jq -r '.texts' "$json_file" 2>/dev/null)
        if [ -z "$ocr_text" ] || [ "$ocr_text" = "null" ]; then
            # 空文本视为不匹配（不报错）
            continue
        fi

        $VERBOSE && echo "   处理文件: $img_name"
        $VERBOSE && echo "   OCR 结果: ${ocr_text:0:50}..." 

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

        # 处理匹配图片
        if [ "$keyword_found" = true ]; then
            if [ -f "$img_path" ]; then
                if $DRY_RUN; then
                    cp "$img_path" "$sub_output_dir/" && {
                        highlight_match "   预览: 复制 $img_path 到 $sub_output_dir"
                        match_count=$((match_count + 1))
                    }
                else
                    mv "$img_path" "$sub_output_dir/" && {
                        highlight_match "   匹配图片: $img_path 已移动到 $sub_output_dir"
                        match_count=$((match_count + 1))
                    }
                fi
            else
                $VERBOSE && echo -e "${YELLOW}   ⚠️ 图片不存在: $img_path${NC}"
            fi
        fi
    done

    # 更新文件夹名称
    if [ "$found_keyword" = true ] && [ $match_count -gt 0 ]; then
        local new_sub_name="${sub_name}（${match_count}）"
        local new_sub_output_dir="$OUTPUT_DIR/$new_sub_name"
        
        # 重命名子目录（包含匹配数量）
        mv "$sub_output_dir" "$new_sub_output_dir"
        echo -e "${GREEN}✅ $sub_name 中找到 $match_count 张匹配图片${NC}"
    else
        $VERBOSE && echo -e "${YELLOW}⚠️ $sub_name 中未找到匹配图片${NC}"
        # 清理空目录
        [ -d "$sub_output_dir" ] && ! $DRY_RUN && rm -rf "$sub_output_dir"
    fi

    echo "----------------------------------------"
}

# 主程序
main() {
    parse_args "$@"
    check_dependencies

    # 设置输出目录
    OUTPUT_BASE=$(dirname "$PARENT_DIR")
    OUTPUT_DIR="$OUTPUT_BASE/keyword_output"
    
    # 创建输出目录（清空旧数据）
    if [ -d "$OUTPUT_DIR" ]; then
        rm -rf "$OUTPUT_DIR"
    fi
    mkdir -p "$OUTPUT_DIR"
    echo -e "${GREEN}📁 创建输出目录: $OUTPUT_DIR${NC}"

    # 记录开始时间
    local start_time
    start_time=$(date +%s)

    # 获取所有OCR处理过的子目录
    local subdirs=()
    while IFS= read -r -d $'\0' dir; do
        subdirs+=("$(basename "$dir")")
    done < <(find "$OCR_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
    local total_dirs=${#subdirs[@]}

    if [ $total_dirs -eq 0 ]; then
        echo -e "${RED}❌ OCR目录中找不到子目录: $OCR_DIR${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ 找到 $total_dirs 个OCR处理过的子目录${NC}"

    # 处理子目录
    local processed=0
    for sub_name in "${subdirs[@]}"; do
        processed=$((processed + 1))
        echo "🔄 处理进度: $processed/$total_dirs - $sub_name"
        process_subdir "$sub_name"
    done

    # 计算耗时
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    printf "\n${GREEN}✅ 关键词匹配完成! 耗时: %d 分 %d 秒${NC}\n" $((duration/60)) $((duration%60))
    
    # 统计结果
    local output_dirs=$(find "$OUTPUT_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
    local total_matches=$(find "$OUTPUT_DIR" -type f 2>/dev/null | wc -l)
    
    echo "处理了 $total_dirs 个子目录"
    echo "找到 $output_dirs 个包含匹配图片的目录"
    echo "共找到 $total_matches 张匹配图片"
    echo -e "${GREEN}📁 匹配结果保存在: $OUTPUT_DIR${NC}"
}

# 启动主程序
main "$@"