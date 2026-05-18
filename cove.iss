; Cove — Inno Setup installer
; Compila con: ISCC.exe /DAppVersion=0.1.0 cove.iss
; (o tramite: python tools\build.py --installer)

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Cove"
#define AppPublisher "Antonio Castellucci"
#define AppURL "https://github.com/caste9612/Cove"
#define AppExeName "Cove.exe"

[Setup]
; GUID statico — non cambiarlo, identifica installazioni precedenti per upgrade
AppId={{A2C2E1F8-6F0B-4B5E-9B7F-C9D3A0E1F2B4}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
; Per-user install (no admin)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
LicenseFile=
OutputDir=dist
OutputBaseFilename=Cove-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
WizardImageStretch=no
ShowLanguageDialog=no

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Avvia Cove all'accesso a Windows"; GroupDescription: "Avvio:"; Flags: unchecked

[Files]
Source: "dist\Cove\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Disinstalla {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Avvia {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Lascia in piedi config.json e audio/ scaricati dall'utente.
; Eliminiamo solo i file generati dall'app stessa (cache __pycache__).
Type: filesandordirs; Name: "{app}\__pycache__"
