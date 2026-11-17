# -*- coding: utf-8 -*-
"""
Frenk's Converter — конвертер видео, музыки и картинок для Windows.

Окно в стиле бренда Frenk's (liquid glass) на WebView2. Перетащи файлы в окно,
на ярлык или выбери «Конвертировать в…» в меню правой кнопки — новый файл
появится рядом с исходным, оригинал не трогается.
"""
import base64
import ctypes
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time

APP_VERSION = "1.0.0"
APP_TITLE = "Frenk's Converter"

HERE = os.path.dirname(os.path.abspath(__file__))
# ресурсы (ui, иконка): в собранном exe они лежат во временной папке PyInstaller
RES = getattr(sys, "_MEIPASS", HERE)
sys.path.insert(0, HERE)
import engine as E  # noqa: E402

PORT = 51837  # одно окно на всех: повторные запуски передают файлы уже открытому окну
ICON = next((p for p in (os.path.join(RES, "icon.ico"), os.path.join(HERE, "..", "assets", "icon.ico"))
             if os.path.exists(p)), "")
UI = os.path.join(RES, "ui", "index.html")
DROP_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Frenk's Converter")
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "FrenksConverter")


def log_error(text):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "error.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except OSError:
        pass


# ---------- очередь задач ----------
class Core:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs = []
        self.next_id = 1
        self.work = queue.Queue()
        self.cancel = threading.Event()
        self.dirty = threading.Event()
        self.last_folder = None
        self.window = None
        threading.Thread(target=self.worker, daemon=True).start()

    # --- состояние для интерфейса ---
    def pending(self):
        return [j for j in self.jobs if j["status"] in ("wait", "error")]

    def snapshot(self):
        with self.lock:
            pend = self.pending()
            counts = {}
            for j in pend:
                for t in E.targets_for(j["path"]):
                    counts[t] = counts.get(t, 0) + 1
            order = E.VIDEO_OUT + E.AUDIO_OUT + E.IMAGE_OUT
            formats = [t for t in order if t in counts]
            return {
                "counts": counts,
                "pending": len(pend),
                "jobs": [{k: j.get(k) for k in ("id", "name", "ext", "kind", "size", "status",
                                                 "progress", "target", "result", "error")} for j in self.jobs],
                "formats": formats,
                "groups": {f: E.group_of(f) for f in formats},
                "busy": any(j["status"] in ("queued", "work") for j in self.jobs),
                "ffmpeg": bool(E.FFMPEG),
            }

    def changed(self):
        self.dirty.set()

    # --- добавление ---
    def add(self, paths, target=None):
        added, skipped, auto = 0, 0, []
        with self.lock:
            for p in paths:
                if not p:
                    continue
                p = os.path.abspath(p)
                if os.path.isdir(p):
                    found = []
                    for root, _d, files in os.walk(p):
                        found += [os.path.join(root, f) for f in sorted(files)]
                    items = [f for f in found if E.targets_for(f)]
                else:
                    items = [p]
                for f in items:
                    if not os.path.isfile(f) or not E.targets_for(f):
                        skipped += 1
                        continue
                    if any(j["path"] == f and j["status"] in ("wait", "queued", "work") for j in self.jobs):
                        continue
                    try:
                        size = os.path.getsize(f)
                    except OSError:
                        size = None
                    job = {"id": self.next_id, "path": f, "name": os.path.basename(f), "ext": E.ext_of(f),
                           "kind": E.kind_of(f), "size": size, "status": "wait", "progress": None,
                           "target": None, "result": None, "error": None}
                    self.next_id += 1
                    self.jobs.append(job)
                    added += 1
                    if target:
                        auto.append(job)
            for job in auto:
                if target in E.targets_for(job["path"]):
                    self.enqueue(job, target)
                else:
                    job.update(status="error", error=f"Нельзя превратить .{job['ext']} в {target.upper()}")
        self.changed()
        if skipped:
            self.toast(f"Пропущено неподдерживаемых файлов: {skipped}")
        return added

    def enqueue(self, job, target):
        job.update(target=target, status="queued", progress=None, error=None)
        self.cancel.clear()
        self.work.put(job)

    def start(self, target):
        with self.lock:
            jobs = [j for j in self.pending() if target in E.targets_for(j["path"])]
            for j in jobs:
                self.enqueue(j, target)
        self.changed()

    def stop(self):
        self.cancel.set()
        with self.lock:
            while True:
                try:
                    j = self.work.get_nowait()
                except queue.Empty:
                    break
                j.update(status="wait", target=None)
        self.changed()

    def remove(self, job_id):
        with self.lock:
            self.jobs = [j for j in self.jobs if not (j["id"] == job_id and j["status"] not in ("queued", "work"))]
        self.changed()

    def clear(self):
        with self.lock:
            self.jobs = [j for j in self.jobs if j["status"] in ("queued", "work")]
        self.changed()

    def find(self, job_id):
        with self.lock:
            return next((j for j in self.jobs if j["id"] == job_id), None)

    # --- работа ---
    def worker(self):
        while True:
            job = self.work.get()
            if job["status"] != "queued":
                continue
            job.update(status="work", progress=None)
            self.changed()

            def prog(p, j=job):
                j["progress"] = p
                self.changed()
            try:
                dst = E.convert(job["path"], job["target"], prog, self.cancel)
                job.update(status="done", result=os.path.basename(dst), result_path=dst, progress=100)
                self.last_folder = os.path.dirname(dst)
            except E.ConvertError as ex:
                if str(ex) == "Отменено":
                    job.update(status="wait", target=None, progress=None)
                else:
                    job.update(status="error", error=str(ex), progress=None)
            except Exception as ex:  # noqa: BLE001
                log_error(f"convert {job['path']} -> {job['target']}: {ex!r}")
                job.update(status="error", error=str(ex) or "Ошибка", progress=None)
            self.changed()
            if self.work.empty():
                with self.lock:
                    done = sum(1 for j in self.jobs if j["status"] == "done")
                if done:
                    self.toast("Готово ✓")

    # --- связь с окном ---
    def toast(self, msg):
        w = self.window
        if w:
            try:
                w.evaluate_js(f"window.app && app.toast({json.dumps(msg)})")
            except Exception:
                pass

    def pusher(self):
        while True:
            self.dirty.wait()
            time.sleep(0.12)
            self.dirty.clear()
            w = self.window
            if not w:
                continue
            try:
                w.evaluate_js(f"window.app && app.render({json.dumps(self.snapshot(), ensure_ascii=False)})")
            except Exception:
                pass


CORE = Core()


# ---------- API для JavaScript ----------
class Api:
    def ready(self):
        snap = CORE.snapshot()
        snap["version"] = APP_VERSION
        return snap

    def pick_files(self):
        import webview
        exts = ";".join("*." + e for e in E.ALL_INPUT)
        try:
            paths = CORE.window.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=True,
                file_types=(f"Видео музыка и картинки ({exts})", "Все файлы (*.*)"))
        except Exception as ex:  # noqa: BLE001
            log_error(f"dialog: {ex!r}")
            paths = None
        if paths:
            CORE.add(list(paths))

    def start(self, target):
        CORE.start(target)

    def stop(self):
        CORE.stop()

    def clear(self):
        CORE.clear()

    def remove(self, job_id):
        CORE.remove(int(job_id))

    def reveal(self, job_id):
        j = CORE.find(int(job_id))
        path = j and (j.get("result_path") if j["status"] == "done" else j["path"])
        if path and os.path.exists(path):
            subprocess.Popen(["explorer", "/select,", path])

    def open_folder(self):
        folder = CORE.last_folder
        if not folder and CORE.jobs:
            folder = os.path.dirname(CORE.jobs[-1]["path"])
        if not folder:
            folder = os.path.join(os.path.expanduser("~"), "Desktop")
        if os.path.isdir(folder):
            os.startfile(folder)

    def minimize(self):
        CORE.window.minimize()

    def start_drag(self):
        """Перетаскивание окна за заголовок — системным способом Windows (как у обычных окон)."""
        hwnd = HWND["value"]
        form = CORE.window and CORE.window.native
        if not hwnd or form is None:
            return
        from System import Action

        def drag():
            u = ctypes.windll.user32
            u.ReleaseCapture()
            u.SendMessageW(ctypes.c_void_p(hwnd), 0x00A1, 2, 0)  # WM_NCLBUTTONDOWN, HTCAPTION
        try:
            form.BeginInvoke(Action(drag))
        except Exception as ex:  # noqa: BLE001
            log_error(f"drag: {ex!r}")

    def close(self):
        CORE.cancel.set()
        CORE.window.destroy()

    def save_dropped(self, name, b64):
        """Файл перетащили из браузера/мессенджера — пути нет, сохраняем байты в Загрузки\\Конвертер."""
        try:
            os.makedirs(DROP_DIR, exist_ok=True)
            safe = "".join(c for c in os.path.basename(name) if c not in '<>:"/\\|?*') or "файл"
            stem, ext = os.path.splitext(safe)
            path = os.path.join(DROP_DIR, safe)
            n = 1
            while os.path.exists(path):
                path = os.path.join(DROP_DIR, f"{stem} ({n}){ext}")
                n += 1
            with open(path, "wb") as f:
                f.write(base64.b64decode(b64))
            CORE.add([path])
        except Exception as ex:  # noqa: BLE001
            log_error(f"save_dropped: {ex!r}")
            CORE.toast("Не получилось принять файл")


# ---------- перетаскивание (настоящие пути от WebView2) ----------
def on_drop(event):
    try:
        files = event.get("dataTransfer", {}).get("files", []) or []
        paths, missing = [], []
        for f in files:
            p = f.get("pywebviewFullPath")
            if p:
                paths.append(p)
            elif f.get("name"):
                missing.append(f["name"])
        if paths:
            CORE.add(paths)
        if missing:
            CORE.window.evaluate_js(f"window.app && app.needBytes({json.dumps(missing, ensure_ascii=False)})")
    except Exception as ex:  # noqa: BLE001
        log_error(f"drop: {ex!r}")


def on_loaded(window):
    from webview.dom import DOMEventHandler
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
    CORE.changed()


def on_shown(window):
    """Иконка в панели задач и скруглённые углы Windows 11 для окна без рамки."""
    try:
        form = window.native
        from System import Action
        from System.Drawing import Icon

        def apply():
            if os.path.exists(ICON):
                form.Icon = Icon(ICON)
            hwnd = form.Handle.ToInt64()
            HWND["value"] = hwnd
            pref = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 33, ctypes.byref(pref), 4)
        form.Invoke(Action(apply))
    except Exception as ex:  # noqa: BLE001
        log_error(f"shown: {ex!r}")


HWND = {"value": None}


def bring_to_front():
    """Поднять окно наверх. Только через ctypes: свойства WinForms из чужого потока
    держат GIL и вешают окно (взаимная блокировка с потоком интерфейса)."""
    hwnd = HWND["value"]
    if not hwnd:
        return
    try:
        u = ctypes.windll.user32
        h = ctypes.c_void_p(hwnd)
        if u.IsIconic(h):
            u.ShowWindow(h, 9)  # SW_RESTORE
        flags = 0x0001 | 0x0002 | 0x0040  # NOSIZE | NOMOVE | SHOWWINDOW
        u.SetWindowPos(h, ctypes.c_void_p(-1), 0, 0, 0, 0, flags)  # HWND_TOPMOST
        u.SetWindowPos(h, ctypes.c_void_p(-2), 0, 0, 0, 0, flags)  # HWND_NOTOPMOST
        u.SetForegroundWindow(h)
    except Exception as ex:  # noqa: BLE001
        log_error(f"front: {ex!r}")


# ---------- одно окно на всех ----------
def try_become_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        s.bind(("127.0.0.1", PORT))
        s.listen(16)
        return s
    except OSError:
        s.close()
        return None


def send_to_running(payload):
    for _ in range(25):
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=2) as c:
                c.sendall(json.dumps(payload).encode("utf-8"))
            return True
        except OSError:
            time.sleep(0.15)
    return False


def listen(server):
    while True:
        try:
            conn, _ = server.accept()
            with conn:
                data = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
            payload = json.loads(data.decode("utf-8"))
            CORE.add(payload.get("files", []), payload.get("to"))
            bring_to_front()
        except Exception:
            continue


def parse_args(argv):
    target, files, i = None, [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--to" and i + 1 < len(argv):
            target = argv[i + 1].lower()
            i += 2
            continue
        if a != "--open":
            files.append(os.path.abspath(a))
        i += 1
    return {"to": target, "files": files}


def main():
    payload = parse_args(sys.argv[1:])
    server = try_become_server()
    if server is None and send_to_running(payload):
        return  # окно уже открыто — отдали ему файлы

    import webview
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Frenks.Converter")
        # по этой метке установщик видит, что программа запущена, и закрывает её перед обновлением
        ctypes.windll.kernel32.CreateMutexW(None, False, "FrenksConverterMutex")
    except Exception:
        pass

    window = webview.create_window(
        APP_TITLE, url=UI, js_api=Api(),
        width=940, height=640, resizable=False, frameless=True, easy_drag=False,
        background_color="#050505", text_select=False,
    )
    CORE.window = window
    window.events.loaded += on_loaded
    window.events.shown += on_shown
    if payload["files"]:
        CORE.add(payload["files"], payload["to"])
    threading.Thread(target=CORE.pusher, daemon=True).start()
    if server:
        threading.Thread(target=listen, args=(server,), daemon=True).start()
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:  # у .pyw нет консоли — пишем ошибку в файл и показываем окно
        log_error(f"startup: {ex!r}")
        try:
            ctypes.windll.user32.MessageBoxW(0, f"Ошибка запуска:\n{ex}", "Конвертер файлов", 0x10)
        except Exception:
            pass
        raise
