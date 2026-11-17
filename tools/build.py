# -*- coding: utf-8 -*-
"""
Сборка Frenk's Converter:  python tools/build.py

1. exe через PyInstaller            -> dist/FrenksConverter/
2. ffmpeg внутрь программы          -> dist/FrenksConverter/ffmpeg/
3. портативный zip                  -> dist/FrenksConverter-<версия>-portable.zip
4. установщик через Inno Setup      -> dist/FrenksConverter-<версия>-setup.exe

Где взять ffmpeg: переменная окружения FFMPEG_DIR (папка с ffmpeg.exe) или ffmpeg в PATH
(например, `winget install Gyan.FFmpeg`).
"""
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")
APP_DIR = os.path.join(DIST, "FrenksConverter")
sys.path.insert(0, SRC)
import engine  # noqa: E402

# быстрые пункты в меню правой кнопки для каждого типа файлов
QUICK = {
    "video": ["mp3", "mp4", "gif", "wav", "m4a"],
    "audio": ["mp3", "wav", "m4a", "ogg", "flac"],
    "image": ["jpg", "png", "webp", "pdf", "ico"],
    "gif": ["mp4", "png", "jpg"],
}


def version():
    text = open(os.path.join(SRC, "frenks_converter.py"), encoding="utf-8").read()
    return re.search(r'APP_VERSION = "([^"]+)"', text).group(1)


def step(msg):
    print(f"\n=== {msg}", flush=True)


def gen_registry():
    """installer/formats.iss — пункты «Конвертировать в…» для всех поддерживаемых расширений."""
    lines = []
    exe = '"{app}\\FrenksConverter.exe"'
    for ext in engine.ALL_INPUT:
        allowed = engine.targets_for("x." + ext)
        quick = [t for t in QUICK[engine.kind_of("x." + ext)] if t in allowed]
        base = f"Software\\Classes\\SystemFileAssociations\\.{ext}\\shell\\FrenksConverter"

        def val(sub, name, data, flags=""):
            fl = f"; Flags: {flags}" if flags else ""
            name_part = f'ValueName: "{name}"; ' if name is not None else ""
            data = data.replace('"', '""')
            lines.append(f'Root: HKA; Subkey: "{sub}"; ValueType: string; {name_part}ValueData: "{data}"; '
                         f'Tasks: contextmenu{fl}')

        val(base, "MUIVerb", "{cm:MenuTitle}", "uninsdeletekey")
        val(base, "Icon", "{app}\\FrenksConverter.exe,0")
        val(base, "SubCommands", "")
        val(base, "MultiSelectModel", "Player")
        for i, t in enumerate(quick):
            sub = f"{base}\\shell\\{i:02d}{t}"
            val(sub, "MUIVerb", t.upper())
            val(sub, "MultiSelectModel", "Player")
            val(sub + "\\command", None, f'{exe} --to {t} "%1"')
        other = f"{base}\\shell\\99other"
        val(other, "MUIVerb", "{cm:MenuOther}")
        val(other, "CommandFlags", "32")
        val(other, "MultiSelectModel", "Player")
        val(other + "\\command", None, f'{exe} --open "%1"')
    path = os.path.join(ROOT, "installer", "formats.iss")
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("; Сгенерировано tools/build.py — не править руками\n" + "\n".join(lines) + "\n")
    print(f"formats.iss: {len(engine.ALL_INPUT)} расширений, {len(lines)} строк")


def version_file(ver):
    nums = (ver.split(".") + ["0"] * 4)[:4]
    tup = ", ".join(nums)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', "Frenk's"),
      StringStruct('FileDescription', "Frenk's Converter"),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'FrenksConverter'),
      StringStruct('LegalCopyright', "(c) Frenk's. MIT License"),
      StringStruct('OriginalFilename', 'FrenksConverter.exe'),
      StringStruct('ProductName', "Frenk's Converter"),
      StringStruct('ProductVersion', '{ver}')])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"""
    os.makedirs(BUILD, exist_ok=True)
    path = os.path.join(BUILD, "version.txt")
    open(path, "w", encoding="utf-8").write(text)
    return path


def pyinstaller(ver):
    sep = os.pathsep
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "FrenksConverter",
        "--icon", os.path.join(ROOT, "assets", "icon.ico"),
        "--version-file", version_file(ver),
        "--add-data", f"{os.path.join(SRC, 'ui')}{sep}ui",
        "--add-data", f"{os.path.join(ROOT, 'assets', 'icon.ico')}{sep}.",
        "--exclude-module", "tkinter",
        "--distpath", DIST, "--workpath", os.path.join(BUILD, "pyi"), "--specpath", BUILD,
        os.path.join(SRC, "frenks_converter.py"),
    ]
    subprocess.run(cmd, check=True)


def copy_ffmpeg():
    src_dir = os.environ.get("FFMPEG_DIR")
    exe = os.path.join(src_dir, "ffmpeg.exe") if src_dir else shutil.which("ffmpeg")
    if not exe or not os.path.exists(exe):
        sys.exit("Не найден ffmpeg.exe — задай FFMPEG_DIR или поставь: winget install Gyan.FFmpeg")
    out = os.path.join(APP_DIR, "ffmpeg")
    os.makedirs(out, exist_ok=True)
    shutil.copy2(exe, os.path.join(out, "ffmpeg.exe"))
    # лицензия FFmpeg (GPL) и откуда взята сборка — обязательно кладём рядом
    pkg = os.path.dirname(os.path.dirname(exe))
    for name in ("LICENSE", "LICENSE.txt", "README.txt"):
        p = os.path.join(pkg, name)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(out, "FFmpeg-" + name))
    print("ffmpeg:", exe)


def copy_docs():
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        p = os.path.join(ROOT, name)
        if os.path.exists(p):
            shutil.copy2(p, APP_DIR)


def make_zip(ver):
    path = os.path.join(DIST, f"FrenksConverter-{ver}-portable.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _d, files in os.walk(APP_DIR):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.join("FrenksConverter", os.path.relpath(full, APP_DIR)))
    print("zip:", path, f"{os.path.getsize(path) / 1e6:.0f} МБ")


def find_iscc():
    for p in (shutil.which("iscc"),
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
              os.path.expandvars(r"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe")):
        if p and os.path.exists(p):
            return p
    sys.exit("Не найден Inno Setup 6 — поставь: winget install JRSoftware.InnoSetup")


def make_installer(ver):
    subprocess.run([find_iscc(), f"/DAppVersion={ver}", "/Q",
                    os.path.join(ROOT, "installer", "FrenksConverter.iss")], check=True)
    path = os.path.join(DIST, f"FrenksConverter-{ver}-setup.exe")
    print("setup:", path, f"{os.path.getsize(path) / 1e6:.0f} МБ")


def main():
    ver = version()
    print("Frenk's Converter", ver)
    if os.path.isdir(APP_DIR):
        shutil.rmtree(APP_DIR)
    step("Меню правой кнопки для установщика")
    gen_registry()
    step("PyInstaller")
    pyinstaller(ver)
    step("ffmpeg и лицензии")
    copy_ffmpeg()
    copy_docs()
    step("Портативный zip")
    make_zip(ver)
    step("Установщик")
    make_installer(ver)
    print("\nГотово.")


if __name__ == "__main__":
    main()
