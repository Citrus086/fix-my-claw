# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('src/fix_my_claw/prompts', 'fix_my_claw/prompts')]
binaries = []
hiddenimports = ['fix_my_claw', 'fix_my_claw.cli', 'fix_my_claw.config', 'fix_my_claw.health', 'fix_my_claw.monitor', 'fix_my_claw.repair', 'fix_my_claw.state', 'fix_my_claw.notify', 'fix_my_claw.shared', 'fix_my_claw.anomaly_guard', 'fix_my_claw.runtime']
tmp_ret = collect_all('fix_my_claw')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['scripts/cli_entry.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='fix-my-claw',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
