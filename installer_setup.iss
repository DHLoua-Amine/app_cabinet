; ============================================================================
; Cabinet Notarial Zarai — script d'installation Inno Setup
;
; Compilation :
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer_setup.iss
;
; Prerequis : le dossier dist\CabinetNotarialZarai\ doit exister.
;             Le construire avec :  python build_exe.py
;
; Les chemins sont relatifs a l'emplacement de CE fichier ({#SourcePath}) et
; non ecrits en dur : le projet peut etre deplace, ou construit sur une autre
; machine, sans rien modifier ici.
; ============================================================================

#define MonNom        "Cabinet Notarial Zarai"
#define MaVersion     "1.0.4"
#define MonExe        "CabinetNotarialZarai.exe"
#define ReglePareFeu  "Cabinet Notarial Zarai (partage reseau)"
#define PortReseau    "8765"

[Setup]
AppId={{DE1AACB8-4967-41FC-88E7-3B23CDF70861}
AppName={#MonNom}
AppVersion={#MaVersion}
AppVerName={#MonNom} {#MaVersion}
AppPublisher={#MonNom}
VersionInfoVersion={#MaVersion}
DefaultDirName={autopf}\CabinetNotarialZarai
DefaultGroupName={#MonNom}
OutputDir={#SourcePath}dist_installer
OutputBaseFilename=CabinetNotarial_Setup_v{#MaVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; La regle de pare-feu et l'ecriture dans Program Files demandent l'elevation.
PrivilegesRequired=admin
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"
; Cochee par defaut : sans cette regle, le poste de la secretaire ne peut pas
; joindre le PC qui detient la base. Inutile mais inoffensive sur un poste de
; travail, donc laissee active pour eviter un oubli qui coute une heure de
; diagnostic.
Name: "parefeu"; Description: \
    "Autoriser le partage reseau du cabinet (port {#PortReseau}) — necessaire sur le PC qui detient la base"; \
    GroupDescription: "Reseau du cabinet :"

[Files]
Source: "{#SourcePath}dist\CabinetNotarialZarai\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MonNom}"; Filename: "{app}\{#MonExe}"
Name: "{autodesktop}\{#MonNom}"; Filename: "{app}\{#MonExe}"; Tasks: desktopicon

[Run]
; 1. La regle de pare-feu, avant le premier lancement, pour que le serveur soit
;    joignable des le demarrage.
Filename: "{sys}\netsh.exe"; \
    Parameters: "advfirewall firewall add rule name=""{#ReglePareFeu}"" dir=in action=allow protocol=TCP localport={#PortReseau}"; \
    StatusMsg: "Configuration du pare-feu pour le reseau du cabinet..."; \
    Flags: runhidden; Tasks: parefeu
; 2. Le lancement propose en fin d'installation.
Filename: "{app}\{#MonExe}"; Description: "{cm:LaunchProgram,{#MonNom}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
; La regle est retiree a la desinstallation : ne pas laisser un port ouvert sur
; la machine d'un client apres avoir enleve le logiciel.
Filename: "{sys}\netsh.exe"; \
    Parameters: "advfirewall firewall delete rule name=""{#ReglePareFeu}"""; \
    Flags: runhidden; RunOnceId: "SupprimerReglePareFeu"

[UninstallDelete]
; Les donnees du cabinet vivent dans %LOCALAPPDATA%\CabinetNotarialZarai et ne
; sont JAMAIS supprimees ici : desinstaller le logiciel ne doit pas effacer les
; actes, les clients ni la licence du notaire.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Messages]
french.WelcomeLabel2=Cet assistant va installer [name/ver] sur votre ordinateur.%n%nLes donnees du cabinet (clients, dossiers, licence) sont conservees separement et ne seront pas effacees par une reinstallation.
