import os
import shutil
import subprocess
import sys
import zipfile

from _common import IMAGE_EXTS, get_mac_tags, set_mac_tags

# ===================== 配置区（可根据需求修改） =====================
# 图片支持的格式（与 _common.IMAGE_EXTS 保持一致）
SUPPORTED_IMG_FORMATS = IMAGE_EXTS
# 压缩时排除的隐藏文件（macOS 自带 .DS_Store 等）
EXCLUDE_HIDDEN_FILES = ['.DS_Store', '__MACOSX']
# =================================================================

def convert_to_avif(input_path, output_path):
    """调用 primage 将图片转换为 AVIF（-q 90 保证高质量）"""
    try:
        subprocess.run(
            ['primage', '-f', 'avif', '-q', '90', '-o', output_path, input_path],
            check=True,
            capture_output=True,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 转换失败 {input_path}: {e.stderr}")
        return False

def zip_folder(folder_path, zip_output_path):
    """压缩文件夹（排除隐藏文件），生成zip"""
    folder_name = os.path.basename(folder_path)
    parent_dir = os.path.dirname(folder_path)

    with zipfile.ZipFile(zip_output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 遍历文件夹所有文件
        for root, dirs, files in os.walk(folder_path):
            # 跳过隐藏文件夹
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in EXCLUDE_HIDDEN_FILES]

            for file in files:
                # 跳过隐藏文件
                if file.startswith('.') or file in EXCLUDE_HIDDEN_FILES:
                    continue

                file_path = os.path.join(root, file)
                # 压缩包内的相对路径
                arcname = os.path.relpath(file_path, parent_dir)
                zf.write(file_path, arcname)

    print(f"✅ 压缩完成: {zip_output_path}")

def process_single_zip(zip_file_path, input_dir, output_dir):
    """处理单个zip文件：解压→转格式→压缩→复制标签"""
    zip_name = os.path.splitext(os.path.basename(zip_file_path))[0]
    print(f"\n===== 开始处理: {zip_name}.zip =====")

    # 1. 解压路径（临时解压到输入目录；先清掉上次运行可能残留的同名目录）
    extract_folder = os.path.join(input_dir, zip_name)
    if os.path.exists(extract_folder):
        shutil.rmtree(extract_folder)
    os.makedirs(extract_folder)

    # 解压zip
    with zipfile.ZipFile(zip_file_path, 'r') as zf:
        zf.extractall(extract_folder)
    print(f"📂 解压完成: {extract_folder}")

    # 2. 遍历图片，检查是否全为AVIF
    all_avif = True
    img_files = []
    for root, _, files in os.walk(extract_folder):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_IMG_FORMATS:
                img_files.append(os.path.join(root, f))
                if ext != '.avif':
                    all_avif = False

    if not img_files:
        print(f"❌ {zip_name}.zip 内未找到任何支持的图片，终止处理")
        shutil.rmtree(extract_folder, ignore_errors=True)
        sys.exit(1)

    # ===================== 无需处理 → 直接复制原文件 =====================
    if all_avif:
        print(f"ℹ️ {zip_name}.zip 内全是AVIF格式，无需处理，直接复制到输出目录")

        # 目标路径
        target_zip_path = os.path.join(output_dir, os.path.basename(zip_file_path))

        # 复制原压缩包
        shutil.copy2(zip_file_path, target_zip_path)
        print(f"✅ 已复制原压缩包: {target_zip_path}")

        # 复制标签
        original_tags = get_mac_tags(zip_file_path)
        if original_tags:
            if set_mac_tags(target_zip_path, original_tags):
                print(f"🏷️ 已复制标签到复制文件: {original_tags}")
            else:
                print(f"⚠️ 标签写入失败: {target_zip_path}")

        # 删除临时解压文件夹
        shutil.rmtree(extract_folder, ignore_errors=True)
        return
    # ================================================================================

    # 3. 转换非AVIF图片为AVIF
    converted_count = 0
    for img_path in img_files:
        file_dir, file_name = os.path.split(img_path)
        file_base = os.path.splitext(file_name)[0]
        avif_path = os.path.join(file_dir, file_base + '.avif')

        # 转换；任一图片失败直接报错退出（不再静默打包混入非 avif 图）
        if not convert_to_avif(img_path, avif_path):
            print(f"❌ 转换失败，终止处理: {img_path}")
            sys.exit(1)
        # 删除原图片
        os.remove(img_path)
        converted_count += 1

    print(f"🔄 转换完成: 共转换 {converted_count} 张图片为AVIF")

    # 4. 将处理后的文件夹移动到输出目录
    output_folder = os.path.join(output_dir, zip_name)
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
    shutil.move(extract_folder, output_dir)

    # 5. 压缩文件夹为zip（输出目录）
    output_zip_path = os.path.join(output_dir, f"{zip_name}.zip")
    zip_folder(output_folder, output_zip_path)

    # 6. 删除临时文件夹
    shutil.rmtree(output_folder, ignore_errors=True)

    # 7. 复制原zip的标签到新zip
    original_tags = get_mac_tags(zip_file_path)
    if original_tags:
        if set_mac_tags(output_zip_path, original_tags):
            print(f"🏷️ 已复制标签: {original_tags}")
        else:
            print(f"⚠️ 标签写入失败: {output_zip_path}")
    else:
        print(f"ℹ️ 原文件无标签，无需复制")

    print(f"===== 处理完成: {zip_name}.zip =====")

def main():
    # 1. 获取输入文件夹（命令行参数）
    if len(sys.argv) != 2:
        print(f"使用方法: python3 {sys.argv[0]} /path/to/输入文件夹A")
        sys.exit(1)

    input_dir = sys.argv[1].rstrip('/')
    if not os.path.isdir(input_dir):
        print(f"❌ 输入目录不存在: {input_dir}")
        sys.exit(1)

    # 2. 创建输出目录（输入目录同级，命名：A_avif）
    output_dir = f"{input_dir}_avif"
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 输出目录: {output_dir}")

    # 3. 获取所有zip文件，并按文件名从小到大排序
    zip_files = []
    for f in os.listdir(input_dir):
        if f.lower().endswith('.zip'):
            zip_files.append(os.path.join(input_dir, f))
    zip_files.sort()  # 按文件名排序

    if not zip_files:
        print("ℹ️ 输入目录中未找到任何zip文件")
        return

    print(f"📦 共找到 {len(zip_files)} 个压缩包待处理")

    # 4. 逐个处理压缩包
    for zip_path in zip_files:
        process_single_zip(zip_path, input_dir, output_dir)

    print("\n🎉 所有压缩包处理完毕！")

if __name__ == '__main__':
    main()