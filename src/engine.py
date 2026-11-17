# -*- coding: utf-8 -*-
"""Движок конвертации: форматы, ffmpeg, картинки. Без интерфейса."""
import os
import re
import shutil
import subprocess
import sys
import threading

APP_NAME = "Конвертер файлов"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW — без чёрных консолей

# ---------- Форматы ----------
VIDEO_IN = {"mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "m4v", "3gp", "mpg", "mpeg", "ts", "mts", "m2ts", "ogv"}
AUDIO_IN = {"mp3", "wav", "m4a", "aac", "ogg", "oga", "flac", "opus", "wma", "aiff", "aif", "amr", "ac3"}
IMAGE_IN = {"jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff", "ico", "heic", "heif", "avif", "jfif"}
GIF_IN = {"gif"}

AUDIO_OUT = ["mp3", "wav", "m4a", "ogg", "flac", "opus", "aac", "wma"]
VIDEO_OUT = ["mp4", "mkv", "avi", "mov", "webm", "gif"]
IMAGE_OUT = ["jpg", "png", "webp", "bmp", "ico", "tiff", "pdf"]

LABELS = {
    "mp3": "MP3 — аудио", "wav": "WAV — аудио без сжатия", "m4a": "M4A — аудио (iPhone)",
    "ogg": "OGG — аудио", "flac": "FLAC — аудио без потерь", "opus": "OPUS — аудио",
    "aac": "AAC — аудио", "wma": "WMA — аудио",
    "mp4": "MP4 — видео", "mkv": "MKV — видео", "avi": "AVI — видео", "mov": "MOV — видео",
    "webm": "WEBM — видео", "gif": "GIF — анимация",
    "jpg": "JPG — картинка", "png": "PNG — картинка", "webp": "WEBP — картинка",
    "bmp": "BMP — картинка", "ico": "ICO — иконка", "tiff": "TIFF — картинка", "pdf": "PDF — документ",
}


def ext_of(path):
    return os.path.splitext(path)[1].lower().lstrip(".")


def targets_for(path):
    """Во что можно превратить этот файл."""
    e = ext_of(path)
    if e in VIDEO_IN:
        out = VIDEO_OUT + AUDIO_OUT
    elif e in AUDIO_IN:
        out = list(AUDIO_OUT)
    elif e in GIF_IN:
        out = ["mp4", "webm", "mkv"] + [x for x in IMAGE_OUT]
    elif e in IMAGE_IN:
        out = list(IMAGE_OUT)
    else:
        return []
    same = {e, "jpg" if e in ("jpeg", "jfif") else e, "tiff" if e == "tif" else e}
    return [t for t in out if t not in same]


ALL_INPUT = sorted(VIDEO_IN | AUDIO_IN | IMAGE_IN | GIF_IN)


def _app_dir():
    """Папка программы: рядом с exe (собранная версия) или рядом с этим файлом."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_tool(name):
    """Ищем ffmpeg: сначала свой (в папке программы), потом в системе."""
    exe = name + ".exe"
    for folder in (os.path.join(_app_dir(), "ffmpeg"), _app_dir()):
        p = os.path.join(folder, exe)
        if os.path.exists(p):
            return p
    p = shutil.which(name)
    if p:
        return p
    base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(base):
        for root, _dirs, files in os.walk(base):
            if exe in files:
                return os.path.join(root, exe)
    return None


FFMPEG = find_tool("ffmpeg")


def free_name(src, target):
    folder = os.path.dirname(src)
    stem = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(folder, f"{stem}.{target}")
    n = 1
    while os.path.exists(out):
        out = os.path.join(folder, f"{stem} ({n}).{target}")
        n += 1
    return out


# ---------- Конвертация ----------
class ConvertError(Exception):
    pass


def probe(path):
    """Длительность и наличие видео — читаем из вывода самого ffmpeg (ffprobe не нужен)."""
    info = {"duration": None, "video": True}
    if not FFMPEG:
        return info
    try:
        r = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-i", path],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=NO_WINDOW, timeout=60)
        out = r.stderr
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
        if m:
            info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) or None
        streams = re.findall(r"Stream #\S+.*?: Video: .*", out)
        info["video"] = any("attached pic" not in st for st in streams)
    except Exception:
        pass
    return info


def ffmpeg_args(target, src):
    a = {
        "mp3": ["-vn", "-c:a", "libmp3lame", "-q:a", "2"],
        "wav": ["-vn", "-c:a", "pcm_s16le"],
        "m4a": ["-vn", "-c:a", "aac", "-b:a", "192k"],
        "aac": ["-vn", "-c:a", "aac", "-b:a", "192k"],
        "ogg": ["-vn", "-c:a", "libvorbis", "-q:a", "6"],
        "opus": ["-vn", "-c:a", "libopus", "-b:a", "160k"],
        "flac": ["-vn", "-c:a", "flac"],
        "wma": ["-vn", "-c:a", "wmav2", "-b:a", "192k"],
        "mp4": ["-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"],
        "mov": ["-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:a", "aac", "-b:a", "192k"],
        "mkv": ["-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"],
        "avi": ["-map", "0:v:0", "-map", "0:a?", "-c:v", "mpeg4", "-q:v", "3",
                "-c:a", "libmp3lame", "-q:a", "2"],
        "webm": ["-map", "0:v:0", "-map", "0:a?", "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0",
                 "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", "-c:a", "libopus", "-b:a", "128k"],
        "gif": ["-vf", "fps=12,scale='min(480,iw)':-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
                "-loop", "0", "-an"],
    }
    return a[target]


def run_ffmpeg(src, dst, target, on_progress, cancel):
    if not FFMPEG:
        raise ConvertError("Не найден ffmpeg — переустанови программу")
    info = probe(src)
    if target in VIDEO_OUT and ext_of(src) not in GIF_IN and not info["video"]:
        raise ConvertError("В файле нет видео — выбери аудиоформат")
    dur = info["duration"]
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-i", src] + ffmpeg_args(target, src) + \
          ["-progress", "pipe:1", "-nostats", dst]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    err_lines = []

    def read_err():
        for line in proc.stderr:
            err_lines.append(line)
            if len(err_lines) > 40:
                del err_lines[0]

    t = threading.Thread(target=read_err, daemon=True)
    t.start()
    for line in proc.stdout:
        if cancel.is_set():
            proc.kill()
            break
        m = re.match(r"out_time_us=(\d+)", line.strip())
        if m and dur:
            on_progress(min(99, int(int(m.group(1)) / 1e6 / dur * 100)))
    proc.wait()
    t.join(timeout=2)
    if cancel.is_set():
        _remove(dst)
        raise ConvertError("Отменено")
    if proc.returncode != 0:
        _remove(dst)
        tail = "".join(err_lines[-6:]).strip()
        raise ConvertError(tail.splitlines()[-1] if tail else "ffmpeg завершился с ошибкой")


def _remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def convert_image(src, dst, target):
    from PIL import Image, ImageOps
    try:
        im = Image.open(src)
        im = ImageOps.exif_transpose(im)
    except Exception:
        # Pillow не смог — пробуем через ffmpeg
        if not FFMPEG:
            raise ConvertError("Не удалось открыть картинку")
        tmp = dst + ".tmp.png"
        r = subprocess.run([FFMPEG, "-hide_banner", "-y", "-i", src, "-frames:v", "1", tmp],
                           capture_output=True, creationflags=NO_WINDOW)
        if r.returncode != 0 or not os.path.exists(tmp):
            raise ConvertError("Не удалось открыть картинку")
        im = Image.open(tmp)
        im.load()
        _remove(tmp)

    def flat(img):
        """Убираем прозрачность (подкладываем белый фон) для форматов без неё."""
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            return bg
        return img.convert("RGB")

    if target == "jpg":
        flat(im).save(dst, "JPEG", quality=95, subsampling=0)
    elif target == "bmp":
        flat(im).save(dst, "BMP")
    elif target == "pdf":
        flat(im).save(dst, "PDF", resolution=150.0)
    elif target == "png":
        im = im if im.mode in ("RGB", "RGBA", "L", "LA", "P") else im.convert("RGBA")
        im.save(dst, "PNG", optimize=True)
    elif target == "webp":
        im = im if im.mode in ("RGB", "RGBA") else im.convert("RGBA")
        im.save(dst, "WEBP", quality=92, method=5)
    elif target == "tiff":
        im = im if im.mode in ("RGB", "RGBA", "L") else im.convert("RGBA")
        im.save(dst, "TIFF", compression="tiff_lzw")
    elif target == "ico":
        im = im.convert("RGBA")
        side = max(im.size)
        sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
        sizes = [s for s in (16, 24, 32, 48, 64, 128, 256) if s <= max(side, 16)]
        sq.save(dst, "ICO", sizes=[(s, s) for s in sizes])
    else:
        raise ConvertError(f"Не умею сохранять в {target}")


def convert(src, target, on_progress, cancel):
    if not os.path.isfile(src):
        raise ConvertError("Файл не найден")
    if target not in targets_for(src):
        raise ConvertError(f"Нельзя перевести .{ext_of(src)} в {target.upper()}")
    dst = free_name(src, target)
    e = ext_of(src)
    image_job = target in IMAGE_OUT and (e in IMAGE_IN or e in GIF_IN)
    if image_job:
        try:
            convert_image(src, dst, target)
        except ConvertError:
            _remove(dst)
            raise
        except Exception as ex:
            _remove(dst)
            raise ConvertError(str(ex) or "Ошибка картинки")
    else:
        run_ffmpeg(src, dst, target, on_progress, cancel)
    if not os.path.exists(dst) or os.path.getsize(dst) == 0:
        _remove(dst)
        raise ConvertError("Готовый файл пустой")
    return dst


def kind_of(path):
    e = ext_of(path)
    if e in VIDEO_IN:
        return "video"
    if e in AUDIO_IN:
        return "audio"
    if e in GIF_IN:
        return "gif"
    if e in IMAGE_IN:
        return "image"
    return "other"


def group_of(target):
    if target in AUDIO_OUT:
        return "audio"
    if target in VIDEO_OUT:
        return "video"
    return "image"
