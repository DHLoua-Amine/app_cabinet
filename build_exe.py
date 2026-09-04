"""
Builds the distributable application.

This used to assemble a PyInstaller command line by hand, with no --add-data and
no excludes. The result was an 821 MB folder whose executable did not start,
missing the stylesheet and both face-recognition models. The build is now driven
by CabinetNotarialZarai.spec, which is version-controlled and reviewable, and it
verifies afterwards that the files the app opens at runtime are really inside the
build rather than assuming they are.
"""

import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SPEC = BASE_DIR / "CabinetNotarialZarai.spec"

REQUIRED = [
    BASE_DIR / "assets" / "styles.qss",
    BASE_DIR / "core" / "models" / "face_detection_yunet_2023mar.onnx",
    BASE_DIR / "core" / "models" / "face_recognition_sface_2021dec.onnx",
]


def verify_bundle(dist_dir: Path) -> bool:
    """Confirms the built folder really contains the files the app will look for."""
    expected = [
        dist_dir / "_internal" / "assets" / "styles.qss",
        dist_dir / "_internal" / "core" / "models" / "face_detection_yunet_2023mar.onnx",
        dist_dir / "_internal" / "core" / "models" / "face_recognition_sface_2021dec.onnx",
    ]
    ok = True
    print("\nVérification du contenu du build :")
    for p in expected:
        present = p.exists()
        ok &= present
        size = f"{p.stat().st_size / 1024:.0f} Ko" if present else "ABSENT"
        print(f"  [{'OK' if present else '!!'}] {p.relative_to(dist_dir)}  {size}")
    return ok


def build_executable():
    print("Début de la compilation de l'application...")

    missing = [p for p in REQUIRED if not p.exists()]
    if missing:
        print("\nCompilation annulée : fichiers requis introuvables :")
        for p in missing:
            print(f"  - {p}")
        return False

    for d in (BASE_DIR / "build", BASE_DIR / "dist"):
        if d.exists():
            print(f"  nettoyage de {d.name}/ ...")
            shutil.rmtree(d, ignore_errors=True)

    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(BASE_DIR / "dist"), str(SPEC)],
            check=True, cwd=str(BASE_DIR))
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de la compilation : {e}")
        return False

    dist_dir = BASE_DIR / "dist" / "CabinetNotarialZarai"
    if not (dist_dir / "CabinetNotarialZarai.exe").exists():
        print("Erreur : l'exécutable n'a pas été produit.")
        return False

    ok = verify_bundle(dist_dir)
    total = sum(f.stat().st_size for f in dist_dir.rglob("*") if f.is_file())
    print(f"\nTaille totale du build : {total / 1e6:.0f} Mo")
    if ok:
        print("Compilation terminée avec succès ! "
              "L'exécutable se trouve dans 'dist/CabinetNotarialZarai/'.")
    else:
        print("ATTENTION : des fichiers requis manquent dans le build.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if build_executable() else 1)
