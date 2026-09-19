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
AccioLauncher.exe {TAG} is a free, open-source (MIT) launcher that downloads, installs and starts classic PC games on Windows 10/11. Publisher: ASTeam. It is flagged by SmartScreen only because it is new and not code-signed; it contains no malware.

- Source code: https://github.com/ludvdber/AccioLauncher
- Official download: https://github.com/ludvdber/AccioLauncher/releases/tag/{TAG}
- Website: https://acciolauncher.be/
- SHA-256: {SHA256}
- Built by GitHub Actions from the public source (workflow release.yml), never on a personal machine. The release carries a signed build provenance attestation (Sigstore): gh attestation verify AccioLauncher.exe --repo ludvdber/AccioLauncher
- PyInstaller onefile (Python 3.14, PyQt6), UPX disabled. Bundles 7-Zip (7z.exe) to extract the downloaded archives.

Expected behaviour an analyst may observe:
- HTTPS only, to github.com, api.github.com and raw.githubusercontent.com (catalogue, updates, downloads); every downloaded file is checked against its SHA-256.
- Self-update: downloads the new release exe; a small .bat waits for the process to exit, swaps the exe and restarts it.
- Removes the Zone.Identifier stream from extracted game files, so that old games can load their own DLLs.
- For two games only, and after asking the user, writes their language and install path under HKLM\SOFTWARE\WOW6432Node\Electronic Arts\... through an elevated regedit import (UAC prompt).
- Optional Discord Rich Presence through the local Discord named pipe.
```
