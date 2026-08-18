from pathlib import Path


ROOT = Path(SPECPATH).parent.parent

a = Analysis(
    [str(ROOT / "apps" / "api-read" / "portable_run.py")],
    pathex=[str(ROOT / "apps" / "api-read")],
    binaries=[],
    datas=[(str(ROOT / "apps" / "web-read" / "dist"), "web")],
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="api-read",
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="api-read",
)
