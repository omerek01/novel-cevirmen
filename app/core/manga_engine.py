"""Yerel manga çeviri motoru (manga-image-translator) köprüsü — KOTASIZ görü.

Ağır görü işi (balon algılama + OCR + inpaint/temiz-silme + dizgi) motorda YEREL çalışır
(bulut vision çağrısı YOK); yalnız metin çevirisi Gemini'ye gider (ucuz). Motor AYRI bir
venv'de kurulu (torch vb. app venv'ini kirletmez); subprocess ile çağrılır.

Kurulum: `manga-image-translator` deposu app'in kardeş dizininde (`../manga-image-translator`),
kendi venv'i (`venv/`) ve Türkçe config'i (bu app'in `manga_engine_config.json`'u). Motor
yoksa `available()` False döner → pipeline Gemini-vision yedeğine düşer.

Env: `MANGA_ENGINE_DIR` motor dizinini geçersiz kılar; `MANGA_ENGINE_FONT` dizgi fontu
(varsayılan Windows Arial — Türkçe glif destekli).
"""
from __future__ import annotations

import glob
import io
import os
import subprocess
import tempfile
from pathlib import Path

from . import media

_CONFIG = Path(__file__).resolve().parent / "manga_engine_config.json"
_TIMEOUT = 900  # sn: CPU'da uzun sayfa + ilk model indirmesi uzun sürebilir


def engine_dir() -> Path:
    override = os.getenv("MANGA_ENGINE_DIR", "").strip()
    if override:
        return Path(override)
    # app kardeşi: .../gstack/manga-image-translator
    return Path(__file__).resolve().parent.parent.parent.parent / "manga-image-translator"


def engine_python() -> Path:
    d = engine_dir()
    for rel in ("venv/Scripts/python.exe", "venv/bin/python", ".venv/Scripts/python.exe"):
        p = d / rel
        if p.is_file():
            return p
    return d / "venv" / "Scripts" / "python.exe"


def _font() -> str:
    f = os.getenv("MANGA_ENGINE_FONT", "").strip()
    if f and os.path.isfile(f):
        return f
    for cand in (r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.isfile(cand):
            return cand
    return ""


def available() -> bool:
    """Motor kullanılabilir mi (venv python + config var)."""
    return engine_python().is_file() and _CONFIG.is_file()


def translate_manga_page_engine(slug: str, page_no: int, api_key: str) -> str:
    """Sayfayı yerel motorla çevir → çevrilmiş PNG media'ya + <img> HTML döndür.

    Motor içeride algılama+OCR+inpaint+dizgi yapar (yerel), metni Gemini'ye çevirtir.
    Orijinal yazı TEMİZCE silinir (inpaint) ve Türkçe balona düzgün dizilir — kutu
    bindirme yok."""
    from PIL import Image

    from .translate import TranslateError

    src = media.book_dir(slug) / f"src-{page_no}"
    if not src.is_file():
        raise TranslateError("Manga sayfası bulunamadı (yeniden içe aktarın).")

    with tempfile.TemporaryDirectory() as td:
        inp_dir = Path(td) / "in"
        out_dir = Path(td) / "out"
        inp_dir.mkdir()
        # Motorun beklediği isimli PNG'ye yeniden kodla (kaynak jpg/webp olabilir).
        Image.open(str(src)).convert("RGB").save(str(inp_dir / f"{page_no}.png"), "PNG")

        env = dict(os.environ)
        if api_key:
            env["GEMINI_API_KEY"] = api_key
        # Motor GEMINI_MODEL'i API model listesinde arar; proje modeliyle hizala.
        env.setdefault("GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
        cmd = [
            str(engine_python()), "-m", "manga_translator", "local",
            "-i", str(inp_dir), "-o", str(out_dir),
            "--config-file", str(_CONFIG), "--overwrite",
        ]
        font = _font()
        if font:
            cmd += ["--font-path", font]
        try:
            subprocess.run(
                cmd, cwd=str(engine_dir()), env=env, timeout=_TIMEOUT,
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            tail = (exc.stderr or b"").decode("utf-8", "ignore")[-400:]
            raise TranslateError(f"Manga motoru hatası: {tail}") from exc
        except subprocess.TimeoutExpired as exc:
            raise TranslateError("Manga motoru zaman aşımına uğradı (uzun sayfa/CPU).") from exc

        # Folder-mode: çıktı out_dir altında girdiyle AYNI adı korur (1.png). Görsel
        # dosyasını bul (out_dir yalnız çıktıyı içerir).
        outs = [
            p for p in glob.glob(str(out_dir / "**" / "*"), recursive=True)
            if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]
        if not outs:
            # Metin bulunamadıysa (saf sanat sayfası) motor çıktı üretmeyebilir → orijinali kullan.
            data = src.read_bytes()
            with Image.open(io.BytesIO(data)) as im:
                w, h = im.size
        else:
            data = Path(outs[0]).read_bytes()
            with Image.open(io.BytesIO(data)) as im:
                if im.mode != "RGB":
                    im = im.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, "PNG")
                data = buf.getvalue()
                w, h = im.size

    rel = media.write_bytes(slug, f"page-{page_no}.png", data)
    from .import_translate import page_image_html

    return page_image_html(rel, page_no, w, h)
