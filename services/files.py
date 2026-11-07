"""Yuklangan fayllarni tekshirish. Fayllar hech qachon yuklab olinmaydi va ishga tushirilmaydi."""
import os
from typing import Optional

from aiogram.types import Document

import config
from utils.helpers import fmt_size


def file_extension(name: Optional[str]) -> str:
    return os.path.splitext(name or "")[1].lower()


def validate_document(doc: Document) -> Optional[str]:
    """Xato bo'lsa — o'zbekcha xabar, aks holda None."""
    ext = file_extension(doc.file_name)
    if ext not in config.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_EXTENSIONS))
        return f"❌ Fayl turi qo'llab-quvvatlanmaydi. Ruxsat etilgan turlar: <b>{allowed}</b>"
    if doc.file_size is not None and doc.file_size <= 0:
        return "❌ Fayl bo'sh. Boshqa fayl yuboring."
    if doc.file_size and doc.file_size > config.MAX_FILE_SIZE:
        return (
            f"❌ Fayl juda katta ({fmt_size(doc.file_size)}). "
            f"Maksimal hajm: <b>{fmt_size(config.MAX_FILE_SIZE)}</b>"
        )
    return None
