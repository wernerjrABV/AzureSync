from pathlib import Path


ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(ROOT / "apps" / "launcher" / "entrypoint.py")],
    pathex=[str(ROOT / "apps" / "launcher")],
    binaries=[],
    datas=[],
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AzureSync",
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AzureSync-launcher",
)
