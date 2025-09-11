import os
import re
import shutil
import zipfile
from lxml import etree
from tempfile import TemporaryDirectory

def epub_to_cbz(epub_path, output_path):
    # 支持的图片类型
    image_types = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/webp': '.webp'
    }
    html_type = 'application/xhtml+xml'

    with TemporaryDirectory() as tempdir:
        # 解压 EPUB 文件
        with zipfile.ZipFile(epub_path, 'r') as epub_zip:
            epub_zip.extractall(tempdir)

        # 自动定位解压后的根目录
        epub_root = None
        for root, dirs, files in os.walk(tempdir):
            if 'META-INF' in dirs and os.path.exists(os.path.join(root, 'META-INF', 'container.xml')):
                epub_root = root
                break
        if epub_root is None:
            raise Exception('未找到 EPUB 根目录')

        # 解析 container.xml
        with open(os.path.join(epub_root, 'META-INF', 'container.xml'), 'r', encoding='utf-8') as f:
            container = etree.parse(f)
            rootfile = container.xpath('//ns:rootfile', namespaces={'ns': 'urn:oasis:names:tc:opendocument:xmlns:container'})[0]
            content_opf = os.path.join(epub_root, rootfile.attrib['full-path'])

        # 解析 content.opf
        opf = etree.parse(content_opf)
        ns = {'opf': 'http://www.idpf.org/2007/opf'}

        # 获取封面信息
        cover_id = opf.xpath('//opf:meta[@name="cover"]/@content', namespaces=ns)
        cover_href = None
        if cover_id:
            cover_item = opf.xpath(f'//opf:item[@id="{cover_id[0]}"]', namespaces=ns)
            if cover_item:
                cover_href = cover_item[0].attrib['href']

        # 按 spine 顺序收集图片
        sorted_images = []
        for spine_pos, itemref in enumerate(opf.xpath('//opf:spine/opf:itemref', namespaces=ns)):
            item_id = itemref.attrib['idref']
            items = opf.xpath(f'//opf:item[@id="{item_id}"]', namespaces=ns)
            if not items:
                continue
            item = items[0]
            item_href = item.attrib['href']
            item_media_type = item.attrib['media-type']
            item_path = os.path.join(epub_root, item_href)

            if item_media_type == html_type:
                with open(item_path, 'r', encoding='utf-8', errors='ignore') as f:
                    html_content = f.read()
                img_pattern = r'<img\s+[^>]*src=["\']([^"\']+)["\']'
                img_srcs = re.findall(img_pattern, html_content, re.DOTALL)
                for img_src in img_srcs:
                    img_name = os.path.basename(img_src)
                    img_full_path = os.path.join(epub_root, os.path.dirname(item_href), img_src) \
                        if not os.path.exists(os.path.join(epub_root, img_src)) \
                        else os.path.join(epub_root, img_src)
                    sorted_images.append(img_full_path)

        # 保存图片到临时目录
        with TemporaryDirectory() as output_temp:
            written = set()
            count = 0
            # 处理封面
            if cover_href:
                cover_path = os.path.join(epub_root, cover_href)
                cover_ext = os.path.splitext(cover_href)[1]
                if os.path.exists(cover_path):
                    shutil.copyfile(cover_path, os.path.join(output_temp, f'{count:05d}{cover_ext}'))
                    written.add(cover_path)
                    count += 1
            else:
                cover_ext = '.jpg'

            # 按顺序保存页面图片
            for img_path in sorted_images:
                if img_path not in written and os.path.exists(img_path):
                    ext = cover_ext if cover_ext else os.path.splitext(img_path)[1]
                    shutil.copyfile(img_path, os.path.join(output_temp, f'{count:05d}{ext}'))
                    written.add(img_path)
                    count += 1

            # 打包为 CBZ
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as cbz:
                for file in sorted(os.listdir(output_temp)):
                    cbz.write(os.path.join(output_temp, file), arcname=file)

    print(f'转换完成 : {output_path}')

import argparse

def main():
    parser = argparse.ArgumentParser(description='将 EPUB 文件转换为 CBZ 格式')
    parser.add_argument('epub_path', help='EPUB 文件路径')
    args = parser.parse_args()

    output_path = os.path.splitext(args.epub_path)[0] + '.cbz'
    epub_to_cbz(args.epub_path, output_path)

if __name__ == '__main__':
    main()