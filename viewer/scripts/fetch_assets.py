"""Downloads the CC0 Poly Haven assets the viewer uses into viewer/public/.

Run from viewer/:  python scripts/fetch_assets.py
  - models   -> public/models/<id>.glb   (1k JPEG textures, packed by gltf-transform)
  - textures -> public/textures/<id>/{diff,nor_gl,rough}.jpg
  - hdri     -> public/hdri/<id>.hdr

Models are re-encoded without Draco on purpose: Draco makes drei's useGLTF fetch a
decoder from Google's CDN at runtime. Re-running skips anything already downloaded.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent.parent / "public"
API = "https://api.polyhaven.com/files/"
HEADERS = {"User-Agent": "lastmilehome-viewer-asset-fetch"}

# Keep in sync with src/scene/catalog.ts
MODELS = [
    "Sofa_01", "modern_arm_chair_01", "modern_coffee_table_01", "round_wooden_table_01",
    "dining_chair_02", "metal_office_desk", "modern_wooden_cabinet", "wooden_display_shelves_01",
    "drawer_cabinet", "vintage_cabinet_01", "side_table_01", "potted_plant_02",
    "modern_ceiling_lamp_01", "electric_stove", "fancy_picture_frame_01", "painted_wooden_cabinet",
    "wooden_table_02", "coffee_table_round_01", "metal_stool_02", "Ottoman_01",
]
TEXTURES = ["laminate_floor_02", "floor_tiles_06", "plastered_wall_04", "fabric_pattern_07", "oak_veneer_01"]
HDRIS = ["lythwood_room"]


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as res:
        return res.read()


def _recompress_jpeg(path: Path) -> None:
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((1024, 1024))
        im.save(path, format="JPEG", quality=80, optimize=True)


def _files(asset_id: str) -> dict:
    return json.loads(_get(API + asset_id))


def fetch_model(asset_id: str) -> None:
    out = PUBLIC / "models" / f"{asset_id}.glb"
    if out.exists():
        return
    gltf = _files(asset_id)["gltf"]["1k"]["gltf"]
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / Path(gltf["url"]).name
        src.write_bytes(_get(gltf["url"]))
        for rel, info in gltf.get("include", {}).items():  # paths the .gltf references
            dest = Path(tmp) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_get(info["url"]))
            if dest.suffix.lower() in (".jpg", ".jpeg"):
                _recompress_jpeg(dest)
        out.parent.mkdir(parents=True, exist_ok=True)
        # Plain repack into one .glb: `optimize` simplifies meshes and scrambled some models'
        # UVs, and its WebP step (sharp) fails on some Windows setups, so textures stay JPEG.
        subprocess.run(
            ["npx", "--yes", "@gltf-transform/cli@4.1.1", "copy", str(src), str(out)],
            check=True,
            shell=sys.platform == "win32",  # npx is a .cmd shim on Windows
        )
    print(f"model    {asset_id}: {out.stat().st_size / 1e6:.1f} MB")


def fetch_texture(asset_id: str) -> None:
    files = _files(asset_id)
    # Some fabrics ship colour variants (col_1, col_2, ...) instead of a single Diffuse map.
    diffuse = "Diffuse" if "Diffuse" in files else sorted(k for k in files if k.startswith("col_"))[0]
    for key, name in ((diffuse, "diff"), ("nor_gl", "nor_gl"), ("Rough", "rough")):
        out = PUBLIC / "textures" / asset_id / f"{name}.jpg"
        if out.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(_get(files[key]["1k"]["jpg"]["url"]))
    print(f"texture  {asset_id}")


def fetch_hdri(asset_id: str) -> None:
    out = PUBLIC / "hdri" / f"{asset_id}.hdr"
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_get(_files(asset_id)["hdri"]["1k"]["hdr"]["url"]))
    print(f"hdri     {asset_id}")


if __name__ == "__main__":
    if not shutil.which("npx"):
        sys.exit("npx not found; install Node.js")
    for t in TEXTURES:
        fetch_texture(t)
    for h in HDRIS:
        fetch_hdri(h)
    for m in MODELS:
        fetch_model(m)
