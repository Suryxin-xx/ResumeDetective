"""
核心转换模块 — PDF 导出为图片

支持格式: PNG / JPEG / TIFF / BMP / WEBP
"""

import os
from pathlib import Path
from typing import Callable, Optional

ProgressCB = Callable[[int, int, str], None]

# 格式 → (Pillow format, 文件后缀, 说明)
SUPPORTED_FORMATS = {
    "PNG":  ("PNG",  ".png",  "无损，适合截图/存档"),
    "JPEG": ("JPEG", ".jpg",  "有损压缩，适合照片（可调质量）"),
    "TIFF": ("TIFF", ".tif",  "无损，适合印刷/出版"),
    "BMP":  ("BMP",  ".bmp",  "无损，文件较大"),
    "WEBP": ("WEBP", ".webp", "Google 格式，平衡质量与大小"),
}

FORMAT_KEYS = list(SUPPORTED_FORMATS.keys())
DEFAULT_FORMAT = "PNG"


def pdf_to_images(
    pdf_path: str,
    output_dir: str,
    fmt: str = "PNG",
    dpi: int = 200,
    quality: int = 90,
    pages: Optional[list] = None,
    progress_cb: Optional[ProgressCB] = None,
) -> list[str]:
    """
    将 PDF 每页导出为图片。

    参数:
        pdf_path:    输入 PDF 路径
        output_dir:  输出目录
        fmt:         图片格式 (PNG/JPEG/TIFF/BMP/WEBP)
        dpi:         渲染 DPI
        quality:     JPEG/WEBP 质量 (1-100)
        pages:       指定页码列表 (0-based)，None=全部
        progress_cb: 进度回调 (current, total, stage)

    返回:
        生成的文件路径列表
    """
    import fitz
    from PIL import Image

    fmt_key = fmt.upper()
    if fmt_key not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的格式: {fmt}，可选: {', '.join(FORMAT_KEYS)}")

    pil_fmt, ext, _ = SUPPORTED_FORMATS[fmt_key]

    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    doc = fitz.open(pdf_path)
    total = len(doc)

    if pages is None:
        pages = list(range(total))
    else:
        pages = [p for p in pages if 0 <= p < total]

    if not pages:
        doc.close()
        raise ValueError("没有需要处理的页面")

    os.makedirs(output_dir, exist_ok=True)
    base_name = Path(pdf_path).stem

    generated = []
    save_kwargs = _get_save_kwargs(pil_fmt, quality)

    for idx, page_num in enumerate(pages):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=mat)

        # 通过 Pillow 保存（支持更多格式参数）
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        out_name = f"{base_name}_p{page_num + 1:04d}{ext}"
        out_path = os.path.join(output_dir, out_name)
        img.save(out_path, format=pil_fmt, **save_kwargs)

        generated.append(out_path)

        if progress_cb:
            progress_cb(idx + 1, len(pages), "")

    doc.close()
    return generated


def _get_save_kwargs(pil_fmt: str, quality: int = 90) -> dict:
    """根据格式返回 Pillow save 的额外参数"""
    kwargs = {}
    if pil_fmt in ("JPEG",):
        kwargs["quality"] = quality
        kwargs["optimize"] = True
        kwargs["progressive"] = True
    elif pil_fmt == "WEBP":
        kwargs["quality"] = quality
        kwargs["method"] = 6  # 编码质量 0-6，6=最好
    elif pil_fmt == "TIFF":
        kwargs["compression"] = "lzw"
    # PNG/BMP 使用默认参数
    return kwargs
