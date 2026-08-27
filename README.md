# PersonalScripts

- `ffmpeg` ffmpeg 官方编译版，直接拿来用省得 brew list 里一堆依赖项
- `manga` 漫画相关，包括但不限于日漫的一卷拆分成章、重命名每一页、双页漫画的裁剪和韩漫拼接等等。OCR 走 macOS 原生 Vision 框架（pyobjc 直接调用，详见 `manga/src/ocr_process.py`），无需外部二进制
- `epub` 电子书相关，把电子书的多余部分去掉，只保留有用内容
