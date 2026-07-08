"""
核心转换模块
功能：
  1. Word (.docx) → 临时 PDF（通过 Microsoft Word COM 接口）
  2. PDF → 图片版 PDF（每页渲染为图片再合成，文字不可选）
"""

import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

from . import file_ops

# ---------------------------------------------------------------------------
# 回调类型：(current, total, stage_msg)
#   current / total : 进度数值，total=0 表示不确定进度
#   stage_msg       : 阶段描述文字（可选）
# ---------------------------------------------------------------------------
ProgressCB = Callable[[int, int, str], None]


def word_to_pdf(word_path: str, pdf_path: str) -> None:
    """通过 Microsoft Word COM 将 .docx 导出为 PDF"""
    import comtypes.client
    import comtypes

    comtypes.CoInitialize()
    word_app = None
    try:
        word_app = comtypes.client.CreateObject("Word.Application")
        word_app.Visible = False
        word_app.DisplayAlerts = False

        doc = word_app.Documents.Open(os.path.abspath(word_path))
        # 17 = wdFormatPDF
        doc.SaveAs(os.path.abspath(pdf_path), FileFormat=17)
        doc.Close()
    finally:
        if word_app:
            try:
                word_app.Quit()
            except Exception:
                pass
        comtypes.CoUninitialize()


def pdf_to_image_pdf(
    input_pdf: str,
    output_pdf: str,
    dpi: int = 200,
    progress_cb: Optional[ProgressCB] = None,
) -> str:
    """
    将可复制 PDF 转为图片版 PDF。

    - 用 PyMuPDF 逐页渲染为 PNG 图片（dpi 控制清晰度）
    - 将每张图片作为全页插入新 PDF
    - 最终 PDF 仅包含图片，文字不可选中/复制
    """
    import fitz  # PyMuPDF

    zoom = dpi / 72.0  # fitz 默认 72 DPI
    mat = fitz.Matrix(zoom, zoom)

    src = fitz.open(input_pdf)
    total = len(src)
    if total == 0:
        src.close()
        raise ValueError("输入 PDF 为空，无页面可处理")

    dst = fitz.open()

    for i in range(total):
        page = src[i]
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")

        rect = page.rect
        pw = rect.width * zoom
        ph = rect.height * zoom

        new_page = dst.new_page(width=pw, height=ph)
        new_page.insert_image(new_page.rect, stream=img_bytes)

        if progress_cb:
            progress_cb(i + 1, total, "")

    src.close()
    dst.save(output_pdf, deflate=True, garbage=4)
    dst.close()
    return output_pdf


def convert_to_image_pdf(
    input_path: str,
    output_path: str,
    dpi: int = 200,
    progress_cb: Optional[ProgressCB] = None,
) -> str:
    """
    统一入口。

    - .docx  → 临时 PDF（Word COM）→ 图片版 PDF
    - .pdf   → 直接转图片版 PDF
    """
    ext = Path(input_path).suffix.lower()

    if ext == ".docx":
        # ---- Word → 临时 PDF → 图片版 PDF ----
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            temp_pdf = f.name
        try:
            if progress_cb:
                progress_cb(0, 0, "正在通过 Word 转换为 PDF（请勿操作 Office）...")
            word_to_pdf(input_path, temp_pdf)

            if progress_cb:
                progress_cb(0, 0, "正在转换为图片版 PDF...")
            pdf_to_image_pdf(temp_pdf, output_path, dpi, progress_cb)
        finally:
            if os.path.exists(temp_pdf):
                ok, msg = file_ops.recycle_path(temp_pdf)
                if not ok:
                    print(f"[临时文件] {msg}: {temp_pdf}")

    elif ext == ".pdf":
        pdf_to_image_pdf(input_path, output_path, dpi, progress_cb)

    else:
        raise ValueError(
            f"不支持的文件格式: {ext}，仅支持 .docx / .pdf"
        )

    return output_path
