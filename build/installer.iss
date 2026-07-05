; Inno Setup script for OwnTest Studio.
; Produces the single file end users receive: OwnTest-Setup.exe
; Build (after PyInstaller): iscc build\installer.iss
; Download Inno Setup: https://jrsoftware.org/isdl.php

#define AppName "OwnTest Studio"
#define AppVersion "0.1.0"
#define AppExe "OwnTest.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Your Company
DefaultDirName={autopf}\OwnTest
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename=OwnTest-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
; WebView2 Evergreen Bootstrapper (~2 MB) — download once from Microsoft and
; place next to this script:
; https://developer.microsoft.com/microsoft-edge/webview2/#download
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: WebView2Missing

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Run]
; Silently install WebView2 runtime only if the machine doesn't have it
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; \
  StatusMsg: "Installing Microsoft WebView2 runtime..."; Check: WebView2Missing
; Offer to launch when the wizard finishes
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; \
  Flags: nowait postinstall skipifsilent

[Code]
function WebView2Missing: Boolean;
var
  Version: String;
begin
  // WebView2 per-machine registry key; present on Win11 and updated Win10
  Result := not RegQueryStringValue(HKLM,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Version);
end;
