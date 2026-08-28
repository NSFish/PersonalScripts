# AGENTS.md

本仓库仅由我在 macOS + Homebrew 环境下使用。执行相关任务时，优先用下列工具代替系统默认工具。

## 文件查找与搜索
| 用途 | 优先工具 | 代替 |
| --- | --- | --- |
| 查找文件 | `fd` | `find` |
| 搜索内容 | `rg` (ripgrep) | `grep` |
| 交互式选择 | `fzf` | — |
| 列出文件 | `eza` | `ls` |
| 目录树 | `tree` | — |

## 文本查看与数据处理
| 用途 | 优先工具 |
| --- | --- |
| 查看文件 | `bat` |
| 处理 JSON | `jq` |
| 处理 YAML | `yq` |
| git diff pager | `git-delta` |

## Git 与 GitHub
- `gh`：PR / Issue / 仓库管理
- `git`：常规版本控制

## 脚本与任务运行
- `just`：项目有 `justfile` 时优先 `just <任务名>`
- `shellcheck`：Shell 脚本静态检查
- `shfmt`：Shell 脚本格式化

## AI 执行原则
- 有多种方式完成同一件事时，优先选择上述工具。
- 仅当需要生成跨平台脚本（给其他系统用）时，才考虑 POSIX 标准的 `grep/find`，否则默认 `rg/fd`。

## 工程结构
- 多子项目仓库，互不耦合：`manga/`（漫画处理）、`epub/`（电子书处理），各自有独立的 `pyproject.toml` 与 `.python-version`（均为 3.13）。
- 根目录的 `ffmpeg` / `ffprobe` 是官方编译版二进制，已用 `.gitattributes` 以 **git-lfs** 跟踪，不要改动或提交到普通对象。

## Python 约定
- 依赖与运行统一用 **uv**：跑脚本/测试用 `uv run --project <子项目> <命令>`；`uv.lock` 已锁定，新增依赖改 `pyproject.toml` 后让 uv 更新锁文件。
- `manga` 是纯脚本仓库：`[tool.uv] package = false`，源码全部平铺在 `manga/src/` 下作为模块（不是包），靠 `pythonpath = ["src"]` 与 `sys.path[0]` 互相导入。
- 公共逻辑抽到 `manga/src/_common.py`（图片扩展名判断、自然排序、零填充、中文数字转阿拉伯、macOS 标签读写）；新脚本优先复用它，不要重复造轮子。
- 脚本入口规范：用 `argparse` 定义 CLI，函数名 `main()`，并以 `if __name__ == "__main__": main()` 收尾（见 `manga/src/jpeg_2_jpg.py`）。
- 跨平台优先写纯 Python（pathlib 等），避免再引入 shell；很多脚本的 docstring 明确是“替代原 xxx.sh”。用户消息里允许用 emoji（✅❌💡）做终端提示。

## 测试
- `manga` 的回归测试在 `manga/tests/`，用 pytest，配置写在 `manga/pyproject.toml` 的 `[tool.pytest.ini_options]`。
- 运行全部测试：`just test`（等价 `uv run --project manga pytest -c manga/pyproject.toml`）；项目有 `justfile` 时优先 `just <任务>`。

## Shell 脚本约定
- `epub/shell script/` 下是历史 shell 脚本，shebang 固定为 `#!/opt/homebrew/bin/bash`，未使用 `set -e`；改这些脚本时保留 homebrew bash 路径。
- 新建能力优先用上面的 Python 约定，而非新增 shell 脚本。

## macOS 特性
- OCR 直接通过 **pyobjc** 调用系统 Vision 框架（`manga/src/ocr_process.py`），不依赖外部二进制。
- 读/写 Finder 标签用 `Foundation.NSURL` 的 `resourceValuesForKeys_error_` / `setResourceValue_forKey_error_`（`_common.get_mac_tags` / `set_mac_tags`）。

## 按需求选脚本
接到 manga / epub 相关任务时，优先复用下列已有脚本，不要从零重写：

| 需求 | 脚本 |
| --- | --- |
| 扩展名 .jpeg → .jpg | `manga/src/jpeg_2_jpg.py` |
| 单张图片格式转换 | `manga/src/primage_wrapper.py` |
| 文件夹内图片批量转格式 | `manga/src/convert_image_format_to.py` |
| zip 内图片批量转 AVIF | `manga/src/batch_convert_image_format_inside_zip_to_avif.py` |
| 双页漫画裁切成单页 | `manga/src/double_page_crop.py` |
| 两张图片拼接（韩漫） | `manga/src/page_concat.py` |
| 图片裁剪 + 拼接 | `manga/src/page_blender.py` |
| 递归解压 .zip/.cbz | `manga/src/unzip_all.py` |
| 子文件夹压缩为 .zip | `manga/src/zip_all.py` |
| 一卷按章节信息拆分 | `manga/src/volume_split_into_chapters.py` |
| 按文件名归类到章节 | `manga/src/pages_organize_into_chapters.py` |
| 子目录文件顺序重命名 | `manga/src/chapter_pages_rename_by_order.py` |
| 章节文件夹加顺序前缀 | `manga/src/insert_numbers_in_front_of_chapter_titles.py` |
| 中文/阿拉伯数字序号规范化 | `manga/src/cn_numbers_rename.py` |
| 检查图片宽度是否一致 | `manga/src/check_page_width.py` |
| 生成 source.txt 排序列表 | `manga/src/generate_source_file.py` |
| OCR（macOS Vision） | `manga/src/ocr_process.py` |
| 按关键词筛选图片 | `manga/src/keywords_searching.py` |
| zip 重新打包/规范化 | `manga/src/hentai_zip_rename_inside.py` |
| EPUB → CBZ/zip | `epub/src/epub_2_zip.py` |
| EPUB XHTML 格式化 | `epub/src/format_xhtml.py` |

> 公共逻辑一律走 `manga/src/_common.py`；需要新能力时先复用上面脚本再扩展。
