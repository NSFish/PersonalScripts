#!/opt/homebrew/bin/bash
# 中文数字文件夹重命名工具（优化版）

# 初始化变量
DRY_RUN=false  # 默认执行模式
FOLDER_PATH=""
VERBOSE=false   # 控制详细输出

# 帮助信息
show_help() {
    echo "用法: $0 [选项] <文件夹路径>"
    echo "将指定文件夹下的子文件夹名称从中文数字格式转换为阿拉伯数字格式"
    echo ""
    echo "选项:"
    echo "  -n, --dry-run    显示重命名操作但不实际执行 (预览模式)"
    echo "  -v, --verbose    显示详细处理过程"
    echo "  -h, --help       显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 /path/to/folders          (执行重命名)"
    echo "  $0 --dry-run /path/to/folders  (预览模式)"
    echo "  $0 -v /path/to/folders         (详细执行模式)"
}

# 检查Bash版本
check_bash_version() {
    local major_version=${BASH_VERSION%%.*}
    if [[ $major_version -lt 4 ]]; then
        echo "错误: 需要Bash 4.0或更高版本" >&2
        exit 1
    fi
}

# 解析命令行参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -n|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                if [[ -n "$FOLDER_PATH" ]]; then
                    echo "错误：只能指定一个文件夹路径" >&2
                    show_help
                    exit 1
                fi
                FOLDER_PATH="$1"
                shift
                ;;
        esac
    done
    
    if [[ -z "$FOLDER_PATH" ]]; then
        echo "错误：请指定文件夹路径" >&2
        show_help
        exit 1
    fi
}

# 中文数字映射表
declare -A chinese_numbers=(
    ["$(printf "\\u4e00")"]="1"  # 一
    ["$(printf "\\u4e8c")"]="2"  # 二
    ["$(printf "\\u4e09")"]="3"  # 三
    ["$(printf "\\u56db")"]="4"  # 四
    ["$(printf "\\u4e94")"]="5"  # 五
    ["$(printf "\\u516d")"]="6"  # 六
    ["$(printf "\\u4e03")"]="7"  # 七
    ["$(printf "\\u516b")"]="8"  # 八
    ["$(printf "\\u4e5d")"]="9"  # 九
    ["$(printf "\\u96f6")"]="0"  # 零
    ["$(printf "\\u5341")"]="10" # 十
    ["$(printf "\\u767e")"]="100" # 百
    ["$(printf "\\u5343")"]="1000" # 千
    ["$(printf "\\u4e07")"]="10000" # 万
    ["$(printf "\\u4ebf")"]="100000000" # 亿
)

# 中文数字转换函数
convert_chinese_number() {
    local chinese="$1"
    local result=0
    local temp_digit=0
    local char
    local digit_val
    
    # 处理纯阿拉伯数字的情况
    if [[ $chinese =~ ^[0-9]+$ ]]; then
        echo "$chinese"
        return 0
    fi
    
    # 处理零的特殊情况
    if [[ "$chinese" == "$(printf "\\u96f6")" ]]; then
        echo "0"
        return 0
    fi
    
    # 处理单位字符的Unicode码点
    local units="$(printf "\\u5341")|$(printf "\\u767e")|$(printf "\\u5343")|$(printf "\\u4e07")|$(printf "\\u4ebf")"
    
    # 优化转换逻辑：先处理所有单位
    for unit in $(printf "\\u4ebf") $(printf "\\u4e07") $(printf "\\u5343") $(printf "\\u767e") $(printf "\\u5341"); do
        if [[ $chinese == *"$unit"* ]]; then
            local part="${chinese%%"$unit"*}"
            local remainder="${chinese#*"$unit"}"
            
            if [[ -n "$part" ]]; then
                local part_value=$(convert_chinese_number "$part")
                result=$((result + part_value * ${chinese_numbers[$unit]}))
            else
                # 处理"十"这样的单位单独出现的情况
                result=$((result + ${chinese_numbers[$unit]}))
            fi
            chinese="$remainder"
        fi
    done
    
    # 处理剩余的数字
    for ((i=0; i<${#chinese}; i++)); do
        char="${chinese:$i:1}"
        digit_val="${chinese_numbers[$char]}"
        
        if [[ -n "$digit_val" ]]; then
            temp_digit=$((temp_digit * 10 + digit_val))
        fi
    done
    
    result=$((result + temp_digit))
    
    if [[ $result -gt 0 ]]; then
        echo "$result"
        return 0
    else
        echo "错误：无法识别数字格式" >&2
        return 1
    fi
}

# 文件夹处理函数
process_folder() {
    local folder="$1"
    local folder_name=$(basename "$folder")
    local new_name=""
    local is_processed=false
    local status=""
    
    # 优化正则表达式：支持更多中文数字格式
    if [[ $folder_name =~ ^[第]?([^话章]+)[话章](.*)$ ]]; then
        local chinese_num="${BASH_REMATCH[1]}"
        local rest_text="${BASH_REMATCH[2]}"
        local arabic_num=$(convert_chinese_number "$chinese_num" 2>/dev/null)
        
        if [[ $? -eq 0 ]]; then
            # 处理剩余文本中的前缀空格
            rest_text=$(echo "$rest_text" | sed -e 's/^[[:space:]]*//' -e 's/^[[:punct:]]*//')
            
            if [[ -z "$rest_text" ]]; then
                new_name="$arabic_num"
            else
                new_name="$arabic_num $rest_text"
            fi
            
            # 总是显示转换过程
            echo "$folder_name -> $new_name"
            is_processed=true
            
            if [[ $DRY_RUN == true ]]; then
                if [[ $VERBOSE == true ]]; then
                    echo "  (预览) 重命名: $folder -> $(dirname "$folder")/$new_name" >&2
                fi
            else
                mv -- "$folder" "$(dirname "$folder")/$new_name"
            fi
        else
            # 显示转换失败信息
            echo "$folder_name -> 转换失败 (无法识别的数字格式: $chinese_num)"
        fi
    else
        # 检查是否是纯数字文件夹名
        if [[ $folder_name =~ ^[0-9]+[[:space:]]*.*$ ]]; then
            echo "$folder_name -> 无须处理 (已经是数字格式)"
        else
            echo "$folder_name -> 无须处理 (不符合转换格式)"
        fi
    fi
}

# 主程序
main() {
    check_bash_version
    parse_args "$@"
    
    echo "开始处理文件夹: $FOLDER_PATH" >&2
    local mode_text=$(if [[ $DRY_RUN == true ]]; then echo "预览模式"; else echo "执行模式"; fi)
    echo "操作模式: $mode_text" >&2
    echo ""
    
    # 递归处理所有子文件夹
    find "$FOLDER_PATH" -mindepth 1 -maxdepth 1 -type d -print0 | while IFS= read -r -d $'\0' folder; do
        process_folder "$folder"
    done
}

# 启动程序
main "$@"