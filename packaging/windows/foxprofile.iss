; Inno Setup script. Build: iscc /DAppVersion=2.3.1 packaging\windows\foxprofile.iss
; Input: dist\FoxProfile\ (PyInstaller one-folder build). Output: dist\FoxProfile-Setup-<version>.exe
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8E3B7A52-4C1D-4F6A-9B2E-5D7C1A0F3E64}
AppName=FoxProfile
AppVersion={#AppVersion}
AppPublisher=FoxProfile
DefaultDirName={autopf}\FoxProfile
DefaultGroupName=FoxProfile
; Per-user install: no admin prompt. Profiles and logs live in %APPDATA%\FoxProfile, not here.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\..\src\assets\icon.ico
UninstallDisplayIcon={app}\FoxProfile.exe
OutputDir=..\..\dist
OutputBaseFilename=FoxProfile-Setup-{#AppVersion}
LicenseFile=..\..\LICENSE
WizardStyle=modern

[Files]
Source: "..\..\dist\FoxProfile\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\FoxProfile"; Filename: "{app}\FoxProfile.exe"
Name: "{autodesktop}\FoxProfile"; Filename: "{app}\FoxProfile.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\FoxProfile.exe"; Description: "Launch FoxProfile"; Flags: nowait postinstall skipifsilent
