# -*- mode: python ; coding: utf-8 -*-

import glob
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Explicitly expand files for PyInstaller datas to guarantee Windows path resolution
datas = [
    ('icon.ico', '.'),
    ('settings.json', '.'),
]

for f in glob.glob('ffmpeg_engine/bin/*', recursive=True):
    if os.path.isfile(f):
        datas.append((f, 'ffmpeg_engine/bin'))

for f in glob.glob('ffmpeg_engine/presets/*', recursive=True):
    if os.path.isfile(f):
        datas.append((f, 'ffmpeg_engine/presets'))

binaries = []
hiddenimports = [
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'PIL.ImageFilter',
    'PIL.ImageEnhance',
    'PIL.ImageOps',
    'pygame',
    'pygame.mixer',
    'yt_dlp',
    'curl_cffi',
    'gui',
    'gui.theme',
    'gui.icons',
    'gui.queue_cards',
    'gui.watermark_widget',
    'gui.cutter_widget',
    'gui.subtitle_widget',
    'gui.bg_remover_widget',
    'gui.vocal_isolation_widget',
    'core',
    'core.watermark_renderer',
    'core.video_preview',
    'core.watermark_worker',
    'core.worker',
    'core.universal_engine',
    'core.downloader',
    'core.download_worker',
    'core.ai_worker',
    'ffmpeg_engine',
    'ffmpeg_engine.engine',
    'utils',
    'utils.config',
    'utils.logger',
    'utils.validators',
]

# Collect customtkinter assets/themes/windows
ctk_datas, ctk_binaries, ctk_hidden = collect_all('customtkinter')
datas += ctk_datas
binaries += ctk_binaries
hiddenimports += ctk_hidden

# Collect tkinterdnd2 tkdnd native binaries and support files
dnd_datas, dnd_binaries, dnd_hidden = collect_all('tkinterdnd2')
datas += dnd_datas
binaries += dnd_binaries
hiddenimports += dnd_hidden

# Collect yt_dlp submodules
hiddenimports += collect_submodules('yt_dlp')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'torchaudio',
        'onnxruntime',
        'scipy',
        'matplotlib',
        'gradio',
        'fastapi',
        'uvicorn',
        'tensorboard',
        'IPython',
        'notebook',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AudioMorph',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AudioMorph',
)
