; =====================================================================
; ZeroLink Hub - Official Inno Setup Script (Monochrome Minimalist Edition)
; Generates ZeroLink-Setup-v1.2.5.exe for seamless installation & auto-update
; =====================================================================

#define MyAppName "ZeroLink"
#define MyAppVersion "1.2.5"
#define MyAppPublisher "WhyAlwaysEng"
#define MyAppURL "https://github.com/WhyAlwaysEng/ZeroLink"
#define MyAppExeName "ZeroLink.exe"

[Setup]
; Unique AppId across versions
AppId={{C286F454-9988-4FA1-9C3E-94576D21820B}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; Per-user install: no admin UAC needed!
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist_setup
OutputBaseFilename=ZeroLink-Setup-v{#MyAppVersion}
SetupIconFile=..\pc_receiver\icon.ico
UninstallDisplayIcon={app}\_internal\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Automatically close running instances during upgrade
CloseApplications=yes
CloseApplicationsFilter=ZeroLink.exe
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\pc_receiver\dist\ZeroLink\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\Kill-ZeroLink.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
