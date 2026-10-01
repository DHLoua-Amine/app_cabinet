"""
version.py — Fichier officiel de versionnage de l'application Cabinet Notarial Zarai.
"""

__version__ = "1.0.9"
APP_NAME    = "Cabinet Notarial"

# ── GitHub ────────────────────────────────────────────────────────────────────
GITHUB_REPO_RELEASES = "DHLoua-Amine/app_cabinet"  # Dépôt officiel des mises à jour
UPDATE_MODE          = "confirm"   # "confirm" | "silent" | "forced"
ENCODED_GITHUB_TOKEN = ""   # ← VIDE, ET DOIT LE RESTER.
# Le jeton vit dans core/secrets_local.py, ignore par git. Un jeton ecrit
# ici part sur GitHub au prochain push : c'est exactement ce qui est
# arrive au precedent, publie dans trois commits.


# ── Licence ───────────────────────────────────────────────────────────────────
# Clé unique de cette installation. Chaque client reçoit une clé différente.
# Contrôle centralisé via licenses.json sur GitHub (activer / révoquer à distance).
LICENSE_KEY = "DE1AACB8-4967-41FC-88E7-3B23CDF70861"   # ← MASTER / Cabinet Zarai (Siège)
