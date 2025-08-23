import os
import shutil
import argparse
import re

def parse_contents_file(contents_path):
    """
    解析章节信息文件
    格式支持: 
      "1 第一章 3" 
      "2 第二章 65"
      "特别篇 128"
    """
    chapters = []
    with open(contents_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            # 解析三种格式：数字编号+标题、纯标题、中文编号
            match = re.match(r'(\d+)\s+([^\d]+?)\s+(\d+)$', line)  # 格式1: "1 标题 3"
            if match:
                title = f"{match.group(1)} {match.group(2).strip()}"
                start_page = int(match.group(3))
                chapters.append((title, start_page))
                continue
                
            match = re.match(r'(.+?)\s+(\d+)$', line)  # 格式2: "标题 3"
            if match:
                title = match.group(1).strip()
                start_page = int(match.group(2))
                chapters.append((title, start_page))
                
    return chapters

def extract_number(filename):
    """按文件名中的数字排序（支持多数字场景）"""
    base = os.path.splitext(filename)[0]
    numbers = re.findall(r'\d+', base)
    return int(numbers[-1]) if numbers else 0

def organize_manga(input_dir, dir_page, contents_path):
    # 解析章节信息
    chapters = parse_contents_file(contents_path)
    if not chapters:
        print("错误: 未在contents.txt中找到有效的章节信息")
        return
    
    # 添加排序：按照章节起始页码（元组第二个元素）升序排列
    chapters.sort(key=lambda x: x[1])
    
    # 获取并排序图片文件（增加对AVIF格式的支持）
    supported_formats = ('.jpg', '.jpeg', '.png', '.avif')
    all_files = sorted(
        [f for f in os.listdir(input_dir) if f.lower().endswith(supported_formats)],
        key=extract_number
    )
    
    # 定位目录页
    try:
        dir_index = all_files.index(dir_page)
    except ValueError:
        print(f"错误: 目录页 {dir_page} 未在文件夹中找到")
        return
    
    # 计算各章节页数
    chapter_counts = []
    for i in range(len(chapters) - 1):
        chapter_counts.append(chapters[i+1][1] - chapters[i][1])
    chapter_counts.append(len(all_files) - dir_index - sum(chapter_counts))  # 最后一章
    
    # 创建输出目录
    parent_dir = os.path.dirname(os.path.abspath(input_dir))
    output_dir = os.path.join(parent_dir, f"{os.path.basename(input_dir)}_split")
    os.makedirs(output_dir, exist_ok=True)
    
    # 拆分图片到章节文件夹
    current_index = dir_index + 1  # 从目录页下一页开始
    for idx, ((title, _), count) in enumerate(zip(chapters, chapter_counts)):
        chapter_dir = os.path.join(output_dir, title)
        os.makedirs(chapter_dir, exist_ok=True)
        
        # 复制当前章节的图片
        for i in range(count):
            if current_index >= len(all_files):
                print(f"警告: 章节 {title} 预期 {count} 页，但仅剩 {i} 页可用")
                break
                
            src = os.path.join(input_dir, all_files[current_index])
            dst = os.path.join(chapter_dir, all_files[current_index])
            shutil.copy2(src, dst)
            current_index += 1
            
        print(f"章节 [{title}] 已保存 {min(count, i+1)} 页")

    print(f"\n处理完成! 共拆分 {len(chapters)} 个章节到目录: {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='漫画拆分工具')
    parser.add_argument('input_dir', help='漫画图片文件夹路径')
    parser.add_argument('dir_page', help='目录页文件名 (如 "6.jpg")')
    parser.add_argument('contents_file', help='章节信息文件路径')
    
    args = parser.parse_args()
    
    organize_manga(
        input_dir=args.input_dir,
        dir_page=args.dir_page,
        contents_path=args.contents_file
    )