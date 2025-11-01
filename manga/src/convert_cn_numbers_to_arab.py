import os
import sys
import re
import cn2an  # 需提前安装: pip install cn2an

def main():
    if len(sys.argv) != 2:
        print("错误: 请提供文件夹路径作为参数。")
        print("用法: python3 rename_folders.py <文件夹路径>")
        sys.exit(1)

    folder_path = sys.argv[1]

    if not os.path.exists(folder_path):
        print(f"错误: 路径 '{folder_path}' 不存在。")
        sys.exit(1)

    # 获取所有子文件夹（排除文件）
    items = os.listdir(folder_path)
    subfolders = [item for item in items if os.path.isdir(os.path.join(folder_path, item))]

    if not subfolders:
        print("未找到子文件夹。")
        sys.exit(0)

    # 存储需要处理的文件夹信息: (原名称, 中文数字, 转换后的阿拉伯数字)
    folder_data = []
    # 匹配"第XXX条"或"第XXX话"中的中文数字部分[1,2](@ref)
    chinese_num_pattern = re.compile(r'第(.*?)[条话]')
    # 匹配已存在序号的文件夹（如"07 第七条：XX"）
    existing_seq_pattern = re.compile(r'^\d+\s')

    for foldername in subfolders:
        # 检查是否已经存在序号
        if existing_seq_pattern.match(foldername):
            print(f"跳过已有序号的文件夹: '{foldername}'")
            continue

        match = chinese_num_pattern.search(foldername)
        if not match:
            print(f"警告: 跳过不符合格式的文件夹 '{foldername}'")
            continue

        chinese_num = match.group(1)  # 提取中文数字（如"二十九"或"六十"）
        try:
            arabic_num = cn2an.cn2an(chinese_num, "normal")  # 中文数字转阿拉伯数字[1](@ref)
            folder_data.append((foldername, chinese_num, arabic_num))
        except Exception as e:
            print(f"警告: 转换文件夹 '{foldername}' 的数字时出错: {e}")
            continue

    if not folder_data:
        print("未找到需要处理的文件夹。")
        sys.exit(0)

    # 按阿拉伯数字从小到大排序
    folder_data.sort(key=lambda x: x[2])

    # 确定序列号位数（例如10个文件夹用2位，100个用3位）
    total_folders = len(folder_data)
    num_width = len(str(total_folders))  # 序列号位数

    print(f"找到 {total_folders} 个需要处理的文件夹，序列号位数为 {num_width}。")
    print("开始重命名...")

    # 直接重命名文件夹（无需确认）[6](@ref)
    for index, (foldername, _, arabic_num) in enumerate(folder_data):
        seq_num = index + 1
        formatted_seq = str(seq_num).zfill(num_width)  # 格式化序列号（补零）
        new_name = f"{formatted_seq} {foldername}"  # 新名称格式: "序号 原名称"
        old_path = os.path.join(folder_path, foldername)
        new_path = os.path.join(folder_path, new_name)

        try:
            os.rename(old_path, new_path)
            print(f"✓ 重命名: {foldername} -> {new_name}")
        except OSError as e:
            print(f"✗ 错误: 重命名 {foldername} 失败: {e}")

    print("\n处理完成！")

if __name__ == "__main__":
    main()