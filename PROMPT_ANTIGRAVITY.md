# Prompt à copier dans Antigravity

---

I need you to produce a Windows installer for a PySide6 desktop app so I can send it
to a client today. The code fixes are already written and tested — your job is the
build, the installer, and the verification.

## Project

- Root: `C:\Users\amin\Desktop\zarai1_pyside`
- Python: `C:\Users\amin\AppData\Local\Programs\Python\Python313\python.exe`
- App: "Cabinet Notarial Zarai" — notarial office software (Arabic/French, RTL)
- Current version: 1.0.4 (in `core/version.py` and `installer_setup.iss`)

## What was just changed (already tested, do NOT rewrite)

Four files were modified. 22 automated tests pass. Do not redo this work — only
build it.

1. `core/ocr_engine.py`
   - Added `_log_ocr_failure()` — OCR failures now write to `system_errors.log`.
     Before, a failed CIN scan left no trace at all.
   - Added a `reseau_mort` flag: on a network failure (`offline`/`timeout`) the whole
     API-key pool is abandoned instead of retrying every key. Was up to 18 HTTP calls
     (9 keys x 2 models x 40s); now 1. A quota failure (HTTP 429) still tries the next
     key — that behaviour is intentional and must be preserved.

2. `ui/pages/scanner_page.py`
   - Added `OCR_JOIN_TIMEOUT_S = 95`. The two `p1["ocr_thread"].join()` /
     `p2["ocr_thread"].join()` calls had NO timeout, so a stuck pre-scan froze the
     whole generation forever with a spinning progress bar and no message.
   - On timeout, an Arabic warning is added to `results["warnings"]` and the incident
     is logged.

3. `ui/components/audio_recorder.py`
   - `self.session.setAudioInput(None)` after building the session: the microphone is
     no longer held from app start to app exit. It is attached in `start()` and
     released in `_relacher_peripherique()`. This was the real bug — a second running
     instance could not capture anything (0 ms duration, 257-byte empty container).
   - `_on_recorder_error()` now translates Qt's raw English errors into an actionable
     Arabic message and logs them.
   - The finalise-failure message now names the cause based on captured duration
     instead of the useless "the audio file could not be finalised".
   - IMPORTANT: `_diagnostiquer_peripherique()` deliberately refuses ONLY when there
     is no microphone at all. Do not make it refuse on `QAudioSource` `OpenError` —
     that was tried and rejected: it produced false positives that blocked valid
     dictations.

4. `PROMPT_ANTIGRAVITY.md` — this file.

## Your task

### 1. Build

A build may already be running (`python build_exe.py`). Check first:

```
Get-Process python -EA SilentlyContinue | Select Id,StartTime,CPU
```

If `dist\CabinetNotarialZarai\CabinetNotarialZarai.exe` already exists and is newer
than the four source files above, skip to step 2. Otherwise:

```
cd C:\Users\amin\Desktop\zarai1_pyside
& "C:\Users\amin\AppData\Local\Programs\Python\Python313\python.exe" build_exe.py
```

Takes 10–20 minutes. Do not use `build_release.py` — it does not exist here.

### 2. Verify the build before packaging

- `dist\CabinetNotarialZarai\CabinetNotarialZarai.exe` exists.
- Total size of `dist\CabinetNotarialZarai\` is roughly 350–450 MB. Much smaller means
  the `excludes` list broke something.
- `core/secrets_local.py` MUST be inside the build — it holds the GitHub token used
  for auto-updates. It is gitignored but bundled via `hiddenimports` in
  `CabinetNotarialZarai.spec`. Verify it this way:

  ```
  Select-String -Path build\CabinetNotarialZarai\PYZ-00.toc -Pattern secrets_local
  ```

  A raw byte search on the `.exe` gives a FALSE NEGATIVE — the PYZ archive is
  compressed. Use the `.toc` file.

### 3. Build the installer

```
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer_setup.iss
```

Output: `dist_installer\CabinetNotarial_Setup_v1.0.4.exe` (expect ~135–140 MB).

The `.iss` uses `{#SourcePath}`-relative paths and contains no hardcoded machine or
office values — keep it that way. It installs a firewall rule for TCP port 8765
(needed by the PC that hosts the office database) and removes it on uninstall.

### 4. Report back to me

Give me:
- the full path of the installer,
- its size and timestamp,
- confirmation that `secrets_local` was found in `PYZ-00.toc`.

## Things that have burned me before — read these

- First launch of the built `.exe` takes about 45 seconds (antivirus scan). It is not
  frozen. Do not conclude the build is broken before waiting a full minute.
- `console=False` in the spec, so `print()` output is invisible in the built app.
  Anything worth knowing must go through `system_guardian.log_system_error`, which
  writes to `%LOCALAPPDATA%\CabinetNotarialZarai\data\logs\system_errors.log`.
- This machine runs AVG Antivirus, whose Web/Mail Shield intercepts HTTPS and re-signs
  it with its own root CA. `config._build_ca_bundle()` already merges the Windows
  trust store with certifi to handle this — do not disable TLS verification anywhere,
  and do not "fix" this, it works (verified: HTTP 200 from Gemini in 3.4s).
- Never write a secret into `core/version.py` — it is tracked by git and a previous
  token was published in three commits because of exactly that.

## Optional, only if I ask

GitHub release `v1.0.4` (tag `34a2647`) currently has NO assets attached, which is why
auto-update has never worked for any client. Attaching
`dist_installer\CabinetNotarial_Setup_v1.0.4.exe` to that release would let installed
copies update themselves instead of needing a manual visit. The repository is private.

---

## Ce que je dois faire, moi, après avoir reçu le fichier

1. **Envoyer** `CabinetNotarial_Setup_v1.0.4.exe` au client (WeTransfer, clé USB, Drive).
2. **Sur son PC** : désinstaller l'ancienne version n'est pas nécessaire — l'installateur
   écrase. Les données du cabinet (clients, dossiers, licence) vivent dans
   `%LOCALAPPDATA%\CabinetNotarialZarai` et ne sont jamais touchées.
3. **Cocher la case pare-feu** pendant l'installation sur le PC qui détient la base.
4. **Une seule instance à la fois.** Si deux copies de l'application tournent, la
   dictée ne captera rien sur l'ancienne version. C'était le bug du 3 septembre.
5. **En cas de problème**, lire :
   `%LOCALAPPDATA%\CabinetNotarialZarai\data\logs\system_errors.log`
   Il nomme désormais la cause — c'était tout l'objet des corrections.
