import os
import sys
import re
import cn2an

def add_sequential_prefix(folder_path):
    """
    给子文件夹添加顺序前缀
    :param folder_path: 入参文件夹路径
    """
    try:
        # 检查文件夹是否存在
        if not os.path.exists(folder_path):
            print(f"错误：文件夹 '{folder_path}' 不存在")
            return False

        # 获取所有子文件夹
        items = os.listdir(folder_path)
        subfolders = [item for item in items if os.path.isdir(os.path.join(folder_path, item))]

        if not subfolders:
            print("未找到任何子文件夹")
            return True

        print(f"找到 {len(subfolders)} 个子文件夹")

        # 提取序号并排序
        folder_data = []

        for folder_name in subfolders:
            # 使用正则表达式匹配"第X条"或"第X话"格式[3](@ref)
            match = re.search(r'第([零一二三四五六七八九十百千万]+)(条|话)', folder_name)
            if match:
                chinese_num = match.group(1)
                unit = match.group(2)  # 条或话
                try:
                    # 将中文数字转换为阿拉伯数字[3](@ref)
                    arabic_num = cn2an.cn2an(chinese_num, 'normal')
                    folder_data.append({
                        'original_name': folder_name,
                        'chinese_num': chinese_num,
                        'arabic_num': arabic_num,
                        'unit': unit
                    })
                    print(f"匹配: {folder_name} -> 中文数字: {chinese_num} -> 阿拉伯数字: {arabic_num} -> 单位: {unit}")
                except Exception as e:
                    print(f"转换失败: {folder_name}, 错误: {e}")
            else:
                print(f"格式不匹配: {folder_name}")

        if not folder_data:
            print("未找到符合'第X条'或'第X话'格式的子文件夹")
            return False

        # 按阿拉伯数字序号排序
        folder_data.sort(key=lambda x: x['arabic_num'])

        # 计算需要的位数
        total_folders = len(folder_data)
        num_digits = len(str(total_folders - 1))

        print(f"\n排序结果:")
        for i, data in enumerate(folder_data):
            print(f"{i:>{num_digits}} -> {data['original_name']}")

        # 重命名子文件夹[5](@ref)
        print(f"\n开始重命名...")
        for i, data in enumerate(folder_data):
            old_path = os.path.join(folder_path, data['original_name'])
            new_name = f"{i:0{num_digits}} {data['original_name']}"
            new_path = os.path.join(folder_path, new_name)

            try:
                # 检查新路径是否已存在[5](@ref)
                if os.path.exists(new_path):
                    print(f"目标路径已存在，跳过: {new_name}")
                    continue

                os.rename(old_path, new_path)
                print(f"重命名成功: {data['original_name']} -> {new_name}")
            except Exception as e:
                print(f"重命名失败: {data['original_name']}, 错误: {e}")
                return False

        print(f"\n处理完成! 共处理 {len(folder_data)} 个子文件夹")
        return True

    except Exception as e:
        print(f"处理过程中发生错误: {e}")
        return False

def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("用法: python3 folder_renamer.py <文件夹路径>")
        print("示例: python3 folder_renamer.py /path/to/your/folder")
        sys.exit(1)

    folder_path = sys.argv[1]

    # 解析路径（处理Mac上的路径格式）
    folder_path = os.path.expanduser(folder_path)
    folder_path = os.path.abspath(folder_path)

    print(f"处理文件夹: {folder_path}")
    print("-" * 50)

    # 直接执行重命名，去掉确认步骤[5](@ref)
    success = add_sequential_prefix(folder_path)

    if success:
        print("\n✅ 所有操作已完成!")
    else:
        print("\n❌ 处理过程中出现错误")
        sys.exit(1)

if __name__ == "__main__":
    main()