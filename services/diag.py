import html
import platform
import shutil
import tempfile
import time
from pathlib import Path

import yt_dlp.version

import config
from services import catalog, downloader, utils


async def _timed(coro):
    t = time.time()
    try:
        res = await coro
        return True, res, time.time() - t
    except Exception as e:
        return False, e, time.time() - t


async def run() -> str:
    L = [
        f"🐍 Python {platform.python_version()} ({platform.system()})",
        f"📦 yt-dlp {yt_dlp.version.__version__}",
        "✅ ffmpeg bor" if shutil.which("ffmpeg") else "❌ ffmpeg TOPILMADI — o'rnating",
        f"✅ JS runtime: {', '.join(downloader.JS_RUNTIMES)}"
        if downloader.JS_RUNTIMES
        else "⚠️ deno/node topilmadi — YouTube yuklashi ishlamasligi mumkin",
        f"🍪 cookies: {'bor' if config.COOKIES_FILE else 'yo‘q'} | proxy: {'bor' if config.PROXY else 'yo‘q'}",
        "",
    ]

    ok, r, dt = await _timed(catalog._deezer("/search", {"q": "test", "limit": 1}))
    L.append(f"{'✅' if ok else '❌'} Deezer API ({dt:.1f}s)" + ("" if ok else f"\n<code>{html.escape(utils.short_err(r, 200))}</code>"))

    ok, r, dt = await _timed(downloader.search("Jamie Miller Babydoll", 3))
    L.append(f"{'✅' if ok else '❌'} YouTube qidiruv ({dt:.1f}s)" + ("" if ok else f"\n<code>{html.escape(utils.short_err(r, 200))}</code>"))

    for name, target in (("YouTube yuklash", "ytsearch1:Jamie Miller Babydoll"), ("SoundCloud yuklash", "scsearch1:Jamie Miller Babydoll")):
        wd = Path(tempfile.mkdtemp(prefix="diag_", dir=config.TMP_DIR))
        try:
            ok, r, dt = await _timed(downloader.download_audio(target, wd, "64", 600))
            if ok:
                L.append(f"✅ {name} ({dt:.1f}s, {r[0].stat().st_size // 1024} KB)")
            else:
                L.append(f"❌ {name} ({dt:.1f}s)\n<code>{html.escape(utils.short_err(r, 300))}</code>")
        finally:
            shutil.rmtree(wd, ignore_errors=True)
    return "🩺 <b>Diagnostika</b>\n\n" + "\n".join(L)
