"""Build download/Chodbak.exe:  pip install pyinstaller  then  python build_exe.py

Bundles web/sfx/ and web/taunts/ inside the exe and uses the pixel guard as its icon.
The API key is never bundled: the exe asks each user for their own on first run.
"""
import shutil
import struct
import subprocess
import sys
import tkinter as tk
from pathlib import Path

from chodbak import GUARD, PALETTE

HERE = Path(__file__).parent
BUILD = HERE / "build"
BUILD.mkdir(exist_ok=True)

# 64x64 icon from the 16x16 sprite; an .ico may simply wrap a PNG
root = tk.Tk()
root.withdraw()
img = tk.PhotoImage(width=64, height=64)
for y, row in enumerate(GUARD):
    for x, ch in enumerate(row):
        if ch in PALETTE:
            img.put(PALETTE[ch], to=(x * 4, y * 4, x * 4 + 4, y * 4 + 4))
img.write(str(BUILD / "chodbak.png"), format="png")
root.destroy()
png = (BUILD / "chodbak.png").read_bytes()
icon = BUILD / "chodbak.ico"
icon.write_bytes(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 64, 64, 0, 0, 1, 32, len(png), 22) + png)

subprocess.run([
    sys.executable, "-m", "PyInstaller", "--onefile", "--noconfirm", "--name", "Chodbak", "--icon", str(icon),
    "--add-data", f"{HERE / 'web' / 'sfx'};sfx", "--add-data", f"{HERE / 'web' / 'taunts'};taunts",
    "--workpath", str(BUILD), "--specpath", str(BUILD), "--distpath", str(BUILD / "dist"),
    str(HERE / "chodbak.py"),
], check=True)
(HERE / "download").mkdir(exist_ok=True)
shutil.copy2(BUILD / "dist" / "Chodbak.exe", HERE / "download" / "Chodbak.exe")
print("built", HERE / "download" / "Chodbak.exe")
