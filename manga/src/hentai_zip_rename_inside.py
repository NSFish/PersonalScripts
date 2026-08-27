import os
import sys
import zipfile
import shutil

from _common import get_mac_tags, set_mac_tags

EXCLUDE_HIDDEN_FILES = {'.DS_Store', '__MACOSX'}


def rezip_folder(extract_dir, zip_path):
    """把 extract_dir 的内容重新压缩为 zip_path（排除 .DS_Store / __MACOSX）。"""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(extract_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_HIDDEN_FILES]
            for f in files:
                if f in EXCLUDE_HIDDEN_FILES:
                    continue
                file_path = os.path.join(root, f)
                zf.write(file_path, os.path.relpath(file_path, extract_dir))


def main():
    if len(sys.argv) != 2:
        print('用法: python hentai_zip_rename_inside.py <文件夹路径>')
        sys.exit(1)
    folder = sys.argv[1]
    for filename in sorted(os.listdir(folder)):
        if not filename.lower().endswith('.zip'):
            continue
        if filename.lower().endswith('.tmp.zip'):
            continue  # 上次运行失败残留的临时文件，不作为输入处理
        zip_path = os.path.join(folder, filename)
        tags = get_mac_tags(zip_path)
        print(f"{filename} 标签: {', '.join(tags) if tags else '(无)'}")

        zip_name = os.path.splitext(filename)[0]
        extract_dir = os.path.join(folder, zip_name + '_tmp')
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)  # 清掉上次运行残留，避免混入新压缩包

        # 解压
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # 检查解压出来的文件夹名
        extracted_items = os.listdir(extract_dir)
        # 只考虑解压出来只有一个文件夹的情况
        if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_dir, extracted_items[0])):
            inner_folder = extracted_items[0]
            inner_folder_path = os.path.join(extract_dir, inner_folder)
            if inner_folder != zip_name:
                # 重命名为和zip文件名一致
                os.rename(inner_folder_path, os.path.join(extract_dir, zip_name))
                print(f"已重命名文件夹: {inner_folder} -> {zip_name}")

        # 重新压缩为原文件名（保留与 zip 同名的顶层文件夹），先写临时文件再原子替换
        stage_path = os.path.join(folder, zip_name + '.tmp.zip')
        try:
            rezip_folder(extract_dir, stage_path)
            os.replace(stage_path, zip_path)
        finally:
            if os.path.exists(stage_path):
                os.remove(stage_path)

        # 给新压缩包写入标签
        if tags and not set_mac_tags(zip_path, tags):
            print(f"标签写入失败: {zip_path}")

        # 清理临时文件夹
        shutil.rmtree(extract_dir)

        print(f'已生成新压缩包并写入标签: {zip_path}')


if __name__ == "__main__":
    main()
