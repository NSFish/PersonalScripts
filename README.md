# PersonalScripts

- `ffmpeg` ffmpeg 官方编译版，直接拿来用省得 brew list 里一堆依赖项
- 漫画处理：日漫的一卷拆分成章、重命名每一页、双页漫画的裁剪、韩漫拼接等。OCR 走 macOS 原生 Vision 框架（pyobjc 直接调用，详见 `src/ocr_process.py`），无需外部二进制
- 电子书处理：把电子书的多余部分去掉，只保留有用内容

## 目录结构

```
src/            全部 python 脚本（平铺模块，不是包）
resources/      脚本用的模板与静态资源
tests/          pytest 回归测试
tools/          工程工具（binsync 垫片生成器）
bin/            just binsync 生成的全局命令垫片（不入库）
```

## 脚本清单

### Python（`src/`）
| 脚本 | 作用 |
| --- | --- |
| `compress_epub.py` | 把文件夹压成合规 EPUB（mimetype 不压缩且置首） |
| `content_opf_generate.py` | 生成 EPUB 的 `content.opf`（manifest + spine，元数据留空待填） |
| `toc_ncx_generate.py` | 扫描 xhtml 生成 EPUB 的 `toc.ncx`（按卷/部/番外/章分层） |
| `_common.py` | 公共工具：图片扩展名判断、自然排序、零填充、中文数字转阿拉伯、macOS 标签读写 |
| `chapter_pages_rename_by_order.py` | 递归把每个子目录里的文件按排序重命名为零填充序号（也可直接处理单个 .zip/.cbz；命名规则唯一来源，被 `ebook_2_zip.py` 复用） |
| `check_page_width.py` | 扫描文件夹，统计图片主流宽度并列出不符合的图片 |
| `cn_numbers_rename.py` | 把子文件夹名里的中文/阿拉伯数字序号规范化（`--style prefix` 加序号前缀 / `replace` 原地替换，均幂等） |
| `convert_image_format_to.py` | 图片格式万能转换（jpeg/png/webp/avif）：单张图/图片文件夹/单个 .zip/.cbz/批量包文件夹，输出到父目录 `result/` |
| `double_page_crop.py` | 把宽幅双页漫画图按中线裁切成左右两张单页 |
| `ebook_2_zip.py` | 把 MOBI/EPUB 转成 CBZ（漫画模式抽取 image/images 目录重新打包，支持批量与断点续跑） |
| `edge_clean.py` | 清理 Microsoft Edge 堆积的更新备份与组件缓存 |
| `epub_2_md.py` | 扫描版 EPUB → Markdown（Vision OCR + 按 TOC 切章） |
| `epub_2_zip.py` | 把 EPUB 转成 CBZ/zip（抽取图片与 XHTML 重新打包） |
| `export_cookies.py` | 导出浏览器 cookies 为 Netscape 格式（`--browser edge/chrome`；`read_cookies` 供其它脚本复用） |
| `exhentai_unblock.py` | 修复 exhentai 白屏：诊断节点是否被拉黑，只删坏掉的 `igneous` 并保留登录状态 |
| `format_xhtml.py` | EPUB XHTML 文件格式化（文件名排序处理） |
| `generate_source_file.py` | 规范化文件名/文件夹名并生成 source.txt 排序列表 |
| `hentai_download.py` | 下载本子漫画 |
| `hentai_polish.py` | 本子一键整理（数字重命名→AVIF→CBZ） |
| `hentai_rename.py` | 本子重命名 |
| `hentai_zip_rename_inside.py` | 重新打包目录下的 zip（规范化内部结构与文件名，保留 macOS 标签） |
| `jpeg_2_jpg.py` | 递归把 .jpeg 扩展名改为 .jpg |
| `local_network_clean.py` | 清理 macOS「隐私与安全性 > 本地网络」里堆积的残留条目（该权限存在 NetworkExtension 的 network privacy 配置里，不在 TCC，`tccutil` 重置不了） |
| `keywords_searching.py` | 基于 OCR 结果(JSON)筛选含关键词的图片 |
| `ocr_process.py` | 递归对子目录图片做 OCR（macOS Vision），结果存 JSON |
| `page_blender.py` | 图片裁剪与拼接 |
| `page_concat.py` | 水平/垂直拼接两张图片（韩漫拼接） |
| `pages_organize_into_chapters.py` | 按文件名倒数第二段下划线内容把图片归类进对应子文件夹 |
| `primage_wrapper.py` | 单张图片格式转换（primage 封装） |
| `table_diff.py` | 表格差异对比（双读校验） |
| `unzip_all.py` | 递归解压 .zip/.cbz，把图片抽到以压缩包命名的子文件夹 |
| `verify_pairs.py` | 配对校验 |
| `volume_split_into_chapters.py` | 按章节信息文件把一卷图片拆分成章节子文件夹 |
| `workbuddy_checkin.py` | WorkBuddy / CodeBuddy CN 每日签到（零依赖） |
| `zip_all.py` | 把每个子文件夹压缩为同名 .zip（排除 .DS_Store/__MACOSX） |

