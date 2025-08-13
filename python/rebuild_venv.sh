#!/opt/homebrew/bin/bash

# 检查参数
if [ $# -eq 0 ]; then
    echo "❌ 错误：请提供工程文件夹路径作为参数"
    echo "用法: $0 <工程文件夹路径>"
    exit 1
fi

PROJECT_DIR="$1"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"
VENV_DIR="$PROJECT_DIR/.venv"

# 1. 验证工程路径
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ 错误：工程文件夹不存在 - $PROJECT_DIR" >&2
    exit 1
fi

# 2. 检查 requirements.txt
if [ ! -f "$REQUIREMENTS" ]; then
    echo "❌ 错误：未找到 requirements.txt - $REQUIREMENTS" >&2
    exit 1
fi

# 3. 清理旧环境
echo "[1] 清理旧虚拟环境: $VENV_DIR"
rm -rf "$VENV_DIR" 2>/dev/null

# 4. 创建新虚拟环境
echo "[2] 创建新环境 ($VENV_DIR)..."
if ! python3 -m venv "$VENV_DIR"; then
    echo "❌ 环境创建失败！请检查 Python3 是否安装" >&2
    exit 1
fi

# 5. 安装依赖
echo "[3] 安装依赖 ($REQUIREMENTS)..."
"$VENV_DIR/bin/pip" install --upgrade pip >/dev/null

if "$VENV_DIR/bin/pip" install -r "$REQUIREMENTS"; then
    echo "✅ 依赖安装成功！已安装包:"
    "$VENV_DIR/bin/pip" list --format=columns | head -n 5
else
    echo "❌ 依赖安装失败！请检查 $REQUIREMENTS 文件" >&2
    exit 1
fi

# 6. 完成提示
echo "--------------------------------------------------"
echo "✅ 虚拟环境重建完成！"
echo "👉 工程路径: $(cd "$PROJECT_DIR" && pwd)"
echo "👉 激活命令: source $VENV_DIR/bin/activate"
echo "👉 退出命令: deactivate"