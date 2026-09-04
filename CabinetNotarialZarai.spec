# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=['.', 'core'],
    datas=[('assets', 'assets'), ('core/models', 'core/models')],
    hiddenimports=[
        'secrets_local',
        'ui.pages.settings_page',
        'ui.pages.register_page',
        'ui.pages.clients_page',
        'ui.pages.accounting_page',
        'ui.pages.fiche_client_page',
        'ui.pages.home_page',
        'ui.pages.scanner_page',
        'ui.pages.presence_page',
        'ui.pages.settings.workers',
    ],


    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Rien de tout cela n'est importe par l'application : verifie par recherche
    # sur core/, ui/ et main.py. Sans ces exclusions PyInstaller embarque torch
    # (320 Mo), pyarrow (80 Mo), scipy (73 Mo) et matplotlib, tires par des
    # dependances transitives — le dossier passait a 995 Mo, a copier sur
    # chaque poste du cabinet.
    excludes=[
        "torch", "torchaudio", "torchvision",
        "tensorflow", "tensorboard", "keras",
        "pyarrow",
        "scipy",
        "matplotlib",
        "sqlalchemy",
        "IPython", "notebook", "jupyter", "jupyter_core", "nbconvert",
        "tkinter",
        "PyQt5", "PyQt6", "PySide2",
        "pytest", "sphinx",
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
    name='CabinetNotarialZarai',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CabinetNotarialZarai',
)
