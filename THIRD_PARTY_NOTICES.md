# Сторонние компоненты

Код Frenk's Converter распространяется по лицензии [MIT](LICENSE). Готовые сборки
(установщик и портативный zip) содержат сторонние компоненты со своими лицензиями.

## FFmpeg — GPL v3

Сборки включают `ffmpeg.exe` — отдельную программу, которую конвертер запускает
как внешний процесс. Конвертер не линкуется с FFmpeg и не меняет его код.

- Сборка: FFmpeg 9.0.2, `full_build` от [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)
- Лицензия: GNU GPL v3 — текст лежит рядом с программой: `ffmpeg/FFmpeg-LICENSE`
- Исходный код этой версии: <https://github.com/FFmpeg/FFmpeg/commit/946fcce07b>
- Конфигурация сборки и список библиотек: `ffmpeg/FFmpeg-README.txt`

FFmpeg — товарный знак Fabrice Bellard, создателя проекта FFmpeg.

## Библиотеки Python внутри exe

| Компонент | Лицензия |
|---|---|
| [pywebview](https://github.com/r0x0r/pywebview) | BSD 3-Clause |
| [pythonnet](https://github.com/pythonnet/pythonnet), [clr-loader](https://github.com/pythonnet/clr-loader) | MIT |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU |
| [bottle](https://github.com/bottlepy/bottle), [proxy_tools](https://github.com/jtushman/proxy_tools) | MIT |
| [typing_extensions](https://github.com/python/typing_extensions) | PSF |
| [Python](https://www.python.org/) | PSF License |
| [PyInstaller](https://pyinstaller.org/) (загрузчик) | GPL v2 с исключением для собранных программ |

## Шрифты

| Шрифт | Лицензия |
|---|---|
| [Manrope](https://github.com/sharanda/manrope) | SIL Open Font License 1.1 |
| [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) | SIL Open Font License 1.1 |

## Системные компоненты

Окно программы работает на Microsoft Edge WebView2 Runtime — он уже есть в Windows 10/11
и не входит в сборку.
