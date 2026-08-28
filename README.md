# PersonalScripts

- `ffmpeg` ffmpeg 官方编译版，直接拿来用省得 brew list 里一堆依赖项
- `manga` 漫画相关，包括但不限于日漫的一卷拆分成章、重命名每一页、双页漫画的裁剪和韩漫拼接等等。OCR 走 macOS 原生 Vision 框架（pyobjc 直接调用，详见 `manga/src/ocr_process.py`），无需外部二进制
- `epub` 电子书相关，把电子书的多余部分去掉，只保留有用内容

## 脚本清单

### manga（漫画处理，`manga/src/`）
| 脚本 | 作用 |
| --- | --- |
| `_common.py` | 公共工具：图片扩展名判断、自然排序、零填充、中文数字转阿拉伯、macOS 标签读写 |
| `batch_convert_image_format_inside_zip_to_avif.py` | 批量把 zip 内的图片转为 AVIF（primage 封装，-q 90） |
| `chapter_pages_rename_by_order.py` | 递归把每个子目录里的文件按排序重命名为零填充序号 |
| `check_page_width.py` | 扫描文件夹，统计图片主流宽度并列出不符合的图片 |
| `cn_numbers_rename.py` | 把子文件夹名里的中文/阿拉伯数字序号规范化 |
| `convert_image_format_to.py` | 把文件夹内图片转为指定格式（jpeg/png/webp/avif），输出到 `<文件夹>_<格式>` |
| `double_page_crop.py` | 把宽幅双页漫画图按中线裁切成左右两张单页 |
| `generate_source_file.py` | 规范化文件名/文件夹名并生成 source.txt 排序列表 |
| `hentai_zip_rename_inside.py` | 重新打包目录下的 zip（规范化内部结构与文件名，保留 macOS 标签） |
| `insert_numbers_in_front_of_chapter_titles.py` | 给章节子文件夹按“第N话/条”模式加顺序前缀（幂等） |
| `jpeg_2_jpg.py` | 递归把 .jpeg 扩展名改为 .jpg |
| `keywords_searching.py` | 基于 OCR 结果(JSON)筛选含关键词的图片 |
| `ocr_process.py` | 递归对子目录图片做 OCR（macOS Vision），结果存 JSON |
| `page_blender.py` | 图片裁剪与拼接 |
| `page_concat.py` | 水平/垂直拼接两张图片（韩漫拼接） |
| `pages_organize_into_chapters.py` | 按文件名倒数第二段下划线内容把图片归类进对应子文件夹 |
| `primage_wrapper.py` | 单张图片格式转换（primage 封装） |
| `unzip_all.py` | 递归解压 .zip/.cbz，把图片抽到以压缩包命名的子文件夹 |
| `volume_split_into_chapters.py` | 按章节信息文件把一卷图片拆分成章节子文件夹 |
| `zip_all.py` | 把每个子文件夹压缩为同名 .zip（排除 .DS_Store/__MACOSX） |

### epub（电子书处理）
#### Python（`epub/src/`）
| 脚本 | 作用 |
| --- | --- |
| `epub_2_zip.py` | 把 EPUB 转成 CBZ/zip（抽取图片与 XHTML 重新打包） |
| `format_xhtml.py` | EPUB XHTML 文件格式化（文件名排序处理） |

#### Shell（历史脚本，`epub/shell script/`，逐步迁移到 Python）
| 脚本 | 作用 |
| --- | --- |
| `compress_epub.sh` | 把文件夹压成合规 EPUB（mimetype 不压缩且置首） |
| `content_opf_generate.sh` | 生成 `content.opf` |
| `ebook_2_zip.sh` | 电子书转 zip |
| `toc_ncx_generate.sh` | 生成 `toc.ncx` |
