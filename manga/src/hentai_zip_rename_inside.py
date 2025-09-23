import os
import sys
import zipfile
import shutil
from Foundation import NSURL

def get_zip_tag(zip_path):
    url = NSURL.fileURLWithPath_(zip_path)
    values, _ = url.resourceValuesForKeys_error_(['NSURLTagNamesKey'], None)
    tags = values.get('NSURLTagNamesKey', [])
    return tags

def set_zip_tag(zip_path, tags):
    url = NSURL.fileURLWithPath_(zip_path)
    error = None
    success = url.setResourceValue_forKey_error_(tags, 'NSURLTagNamesKey', error)
    if not success:
        print(f"标签写入失败: {zip_path}")

def main():
    if len(sys.argv) != 2:
        print('用法: python zip_rename_inside.py <文件夹路径>')
        sys.exit(1)
    folder = sys.argv[1]
    for filename in os.listdir(folder):
        if filename.lower().endswith('.zip'):
            zip_path = os.path.join(folder, filename)
            tags = get_zip_tag(zip_path)
            print(f"{filename} 标签: {', '.join(tags)}")

            zip_name = os.path.splitext(filename)[0]
            extract_dir = os.path.join(folder, zip_name + '_tmp')

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
                    new_inner_folder_path = os.path.join(extract_dir, zip_name)
                    os.rename(inner_folder_path, new_inner_folder_path)
                    print(f"已重命名文件夹: {inner_folder} -> {zip_name}")
                else:
                    new_inner_folder_path = inner_folder_path
            else:
                # 如果不是只有一个文件夹，直接用解压目录
                new_inner_folder_path = extract_dir

            # 重新压缩为原文件名
            new_zip_path = os.path.join(folder, filename)
            shutil.make_archive(os.path.splitext(new_zip_path)[0], 'zip', new_inner_folder_path)

            # 给新压缩包写入标签
            set_zip_tag(new_zip_path, tags)

            # 清理临时文件夹
            shutil.rmtree(extract_dir)

            print(f'已生成新压缩包并写入标签: {new_zip_path}')

if __name__ == "__main__":
    main()
