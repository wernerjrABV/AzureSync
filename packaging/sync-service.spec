from pathlib import Path


ROOT = Path(SPECPATH).parent.parent

a = Analysis(
    [str(ROOT / "apps" / "sync-service" / "portable_run.py")],
    pathex=[str(ROOT / "apps" / "sync-service")],
    binaries=[],
    datas=[
        (str(ROOT / "apps" / "sync-service" / "app" / "templates"), "app/templates"),
        (str(ROOT / "apps" / "sync-service" / "app" / "static"), "app/static"),
    ],
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sync-service",
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="sync-service",
)
