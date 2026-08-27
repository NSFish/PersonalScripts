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
