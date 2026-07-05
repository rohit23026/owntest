# PyInstaller spec for OwnTest Studio.
# Build on a Windows machine (or GitHub Actions windows runner):
#   pyinstaller build/owntest.spec
# Output: dist/OwnTest.exe  — fully self-contained, no Python needed by users.
import os

block_cipher = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(SPECPATH) if 'SPECPATH' in dir() else '.', '..'))

a = Analysis(
    ['../app/desktop.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../app/static', 'app/static'),     # the UI
        ('../examples', 'examples'),          # seed intent files (copied to user data on first run)
        ('../owntest', 'owntest'),            # the engine as source (imported at runtime)
    ],
    hiddenimports=[
        'owntest', 'owntest.runner',
        'owntest.cdp.client', 'owntest.cdp.browser',
        'owntest.ui.page', 'owntest.api.engine', 'owntest.llm.provider',
        'websockets', 'websockets.legacy',
        'webview.platforms.winforms', 'webview.platforms.edgechromium',
        'clr_loader', 'pythonnet',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='OwnTest',
    debug=False,
    strip=False,
    upx=False,
    console=False,          # windowed app — no black console for the user
    icon=None,              # drop an .ico here later: icon='owntest.ico'
)
