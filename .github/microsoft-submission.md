## Soumettre {TAG} à Microsoft (SmartScreen)

<!-- Rempli par le workflow « release » ({TAG} et {SHA256}) et affiché dans le
     résumé du run : à recopier sur https://www.microsoft.com/en-us/wdsi/filesubmission?persona=SoftwareDeveloper
     après avoir publié la release. Le texte anglais doit rester sous 1 900 caractères. -->

| Champ du formulaire | Réponse |
|---|---|
| Select the Microsoft security product | **Microsoft Defender Smartscreen** (ou *Microsoft Defender Antivirus* si Defender a mis l'exe en quarantaine) |
| Company Name | **ASTeam** |
| Microsoft support case number | **No** |
| Select the file | `AccioLauncher.exe` de la release {TAG} |
| Should this file be removed… | **No** |
| What do you believe this file is? | **Incorrectly detected as malware/malicious** |
| Detection name | **SmartScreen: Windows protected your PC (unrecognized app)** (avec Defender : le nom exact affiché, par exemple `Trojan:Win32/Wacatac.B!ml`) |
| Definition version | vide pour SmartScreen ; avec Defender, celle de *Sécurité Windows → Mises à jour de la protection* |

**Additional information** :

```text
AccioLauncher.exe {TAG} is a free, open-source (GNU GPL v3) launcher that downloads, installs and starts classic PC games on Windows 10/11. Publisher: ASTeam. SmartScreen flags it only because it is new and unsigned; it contains no malware.

- Source: https://github.com/ludvdber/AccioLauncher
- Warning URL: https://github.com/ludvdber/AccioLauncher/releases/download/{TAG}/AccioLauncher.exe
- Website: https://acciolauncher.be/
- SHA-256: {SHA256}
- Built by GitHub Actions from the public source (release.yml), with a Sigstore build provenance attestation: gh attestation verify AccioLauncher.exe --repo ludvdber/AccioLauncher
- PyInstaller onefile (Python 3.15, PyQt6), no UPX. Bundles 7-Zip.

Expected behaviour:
- HTTPS only (github.com, raw.githubusercontent.com, download.microsoft.com); Windows certificate store; downloads SHA-256 checked.
- Before launching a 32-bit game, sets LARGE_ADDRESS_AWARE in its exe header (checksum fixed).
- On first use, downloads vgmstream-cli (ISC, SHA-256 checked); runs it (no window) to convert game music to WAV.
- On request: missing VC++/DirectX redistributables from Microsoft, Authenticode-checked (PowerShell), run elevated (UAC).
- Self-update: a .bat waits for exit, swaps the exe, restarts it.
- Removes Zone.Identifier from extracted game files.
- Two games, after asking: language/install path under HKLM\SOFTWARE\WOW6432Node\Electronic Arts\... via elevated regedit (UAC).
- Optional Discord Rich Presence (local named pipe).
- After a game crash only: wevtutil.exe qe (read-only).
- Reads the controller via winmm joyGetPosEx.
- Gzips save copies before each session; exports/imports saves as .zip on request.
- Reads saves for progress; lists WinSxS for VC++ 2005/2008.
- Moves screenshots to Pictures\Accio Launcher; saves music to Music\Accio on request.
```
