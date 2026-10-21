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
- **单项目仓库**（原先 manga/ 与 epub/ 两个子项目已合并）：根 `pyproject.toml` + `uv.lock` 统一管理，Python ≥3.13（`.python-version` 只定下限，实际跟随 Homebrew 的解释器，不用 uv 自托管版本）。
  全部脚本平铺在 `src/`（历史 shell 脚本已迁移完毕）、模板资源在 `resources/`、回归测试在 `tests/`、工程工具在 `tools/`。
- 根目录的 `ffmpeg` / `ffprobe` 是官方编译版二进制，已用 `.gitattributes` 以 **git-lfs** 跟踪，不要改动或提交到普通对象。
- 全仓库只有一套全局命令机制：`just binsync`（`tools/binsync.py`）扫描 `src/*.py`（`shell script/*.sh` 规则保留备用，当前无 shell 脚本），在**仓库根 `bin/`** 生成 bash 垫片（模块名下划线转横线即命令名，下划线开头的模块不生成；python 脚本走 `uv run --project`，shell 脚本直调；`ffmpeg`/`ffprobe` 软链到根目录本体）。带固定参数等特例写在 `tools/binsync.py` 的 `EXTRA_COMMANDS` 里。用户 `$PATH` 只含 `bin/` 与仓库根两个目录。`bin/` 在根 `.gitignore` 中不入库；新增/删除/重命名脚本或改垫片模板后跑一次 `just binsync`（加 `--check` 只校验），平时改代码不用跑。

## Python 约定
- 依赖与运行统一用 **uv**：跑脚本/测试用 `uv run <命令>`；`uv.lock` 已锁定，新增依赖改根 `pyproject.toml` 后让 uv 更新锁文件。
- 纯脚本仓库：`[tool.uv] package = false`，源码全部平铺在 `src/` 下作为模块（不是包），靠 `pythonpath = ["src"]` 与 `sys.path[0]` 互相导入——所以任何脚本都能直接 `from 其它脚本 import ...` 复用，无需额外配置。
- 公共逻辑抽到 `src/_common.py`（图片/压缩包判断、自然排序与递归收集、隐藏文件排除、`result/` 输出目录、零填充、中文数字转阿拉伯、macOS 标签读写、primage 封装）；新脚本优先复用它，不要重复造轮子。
- 脚本入口规范：用 `argparse` 定义 CLI，函数名 `main()`，并以 `if __name__ == "__main__": main()` 收尾（见 `src/jpeg_2_jpg.py`）。
- 复用其它脚本时**直接 import 它**，不要复制其逻辑、也不要 subprocess 调垫片；CLI 行为保持不变的前提下，可把核心逻辑抽成函数供两边共用（见 `chapter_pages_rename_by_order.plan_names`）。
- 跨平台优先写纯 Python（pathlib 等），避免再引入 shell；很多脚本的 docstring 明确是“替代原 xxx.sh”。用户消息里允许用 emoji（✅❌💡）做终端提示。

## 测试
- 回归测试在 `tests/`，用 pytest，配置写在根 `pyproject.toml` 的 `[tool.pytest.ini_options]`（`pythonpath = ["src"]`）。
- 运行全部测试：`just test`；项目有 `justfile` 时优先 `just <任务>`。

## Shell 脚本约定
- 历史 shell 脚本已全部迁移为 Python（`shell script/` 已取消）。再新增能力一律写 Python，不要新增 shell。
- 新建能力优先用上面的 Python 约定，而非新增 shell 脚本。

## macOS 特性
- OCR 直接通过 **pyobjc** 调用系统 Vision 框架（`src/ocr_process.py`），不依赖外部二进制。
- 读/写 Finder 标签用 `Foundation.NSURL` 的 `resourceValuesForKeys_error_` / `setResourceValue_forKey_error_`（`_common.get_mac_tags` / `set_mac_tags`）。

## 按需求选脚本
接到漫画 / 电子书相关任务时，优先复用下列已有脚本，不要从零重写：

| 需求 | 脚本 |
| --- | --- |
| 扩展名 .jpeg → .jpg | `src/jpeg_2_jpg.py` |
| 单张图片格式转换 | `src/primage_wrapper.py` |
| 文件夹内图片批量转格式 | `src/convert_image_format_to.py` |
| zip 内图片批量转 AVIF | `src/convert_image_format_to.py avif <文件夹>` |
| 双页漫画裁切成单页 | `src/double_page_crop.py` |
| 两张图片拼接（韩漫） | `src/page_concat.py` |
| 图片裁剪 + 拼接 | `src/page_blender.py` |
| 递归解压 .zip/.cbz | `src/unzip_all.py` |
| 子文件夹压缩为 .zip | `src/zip_all.py` |
| 一卷按章节信息拆分 | `src/volume_split_into_chapters.py` |
| 按文件名归类到章节 | `src/pages_organize_into_chapters.py` |
| 子目录文件顺序重命名 | `src/chapter_pages_rename_by_order.py` |
| 中文/阿拉伯数字序号规范化 | `src/cn_numbers_rename.py`（`--style prefix` 加顺序前缀 / `replace` 原地替换，两者均幂等；已合并原 `insert_numbers_in_front_of_chapter_titles.py`） |
| 检查图片宽度是否一致 | `src/check_page_width.py` |
| 生成 source.txt 排序列表 | `src/generate_source_file.py` |
| 番剧/剧集按 source.txt 猜集数重命名 | `src/bangumi_rename.py`（自动从文件名猜集数，无需正则；替代 BangumiRenamer） |
| OCR（macOS Vision） | `src/ocr_process.py` |
| 按关键词筛选图片 | `src/keywords_searching.py` |
| zip/cbz 重新打包/规范化（包名同步到包内顶层文件夹） | `src/hentai_zip_rename_inside.py` |
| 本子一键整理（数字重命名→AVIF→CBZ） | `src/hentai_polish.py` |
| EPUB → CBZ/zip | `src/epub_2_zip.py` |
| MOBI/EPUB → CBZ（电子书转漫画包） | `src/ebook_2_zip.py` |
| EPUB XHTML 格式化 | `src/format_xhtml.py` |
| 文件夹 → 合规 EPUB（mimetype 不压缩置首） | `src/compress_epub.py` |
| 生成 EPUB 的 content.opf | `src/content_opf_generate.py` |
| 生成 EPUB 的 toc.ncx（卷/章导航） | `src/toc_ncx_generate.py` |
| exhentai 白屏（IP 被拉黑 / 残留 `igneous=mystery`） | `src/exhentai_unblock.py`（`check` 只诊断，`fix` 删坏 cookie） |
| 导出浏览器 cookie 给 gallery-dl 用 | `src/export_cookies.py` |

> 公共逻辑一律走 `src/_common.py`；需要新能力时先复用上面脚本再扩展。
