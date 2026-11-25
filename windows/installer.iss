; Inno Setup script for Label Bridge (Windows). Built by build.ps1, which passes /DAppVer=...
#ifndef AppVer
  #define AppVer "0.0.0"
#endif

[Setup]
AppId={{6B0E3C1F-5A8D-4E2B-9C47-1D3F8A2B7E50}
AppName=Label Bridge
AppVersion={#AppVer}
AppVerName=Label Bridge {#AppVer}
AppPublisher=Label Bridge
AppPublisherURL=https://github.com/jbarger/label-bridge
DefaultDirName={autopf}\Label Bridge
DefaultGroupName=Label Bridge
DisableProgramGroupPage=yes
PrivilegesRequired=admin
UsedUserAreasWarning=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=LabelBridge-Setup-{#AppVer}
SetupIconFile=build\labelbridge.ico
UninstallDisplayIcon={app}\LabelBridge.exe
UninstallDisplayName=Label Bridge
LicenseFile=..\LICENSE
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force

[Tasks]
Name: "startup"; Description: "Start Label Bridge when I sign in to Windows (recommended)"
Name: "firewall"; Description: "Let phones on my home Wi-Fi send labels (adds a Windows Firewall rule for Private networks)"
Name: "desktopicon"; Description: "Put a ""Labels to Print"" folder shortcut on the desktop"

[Files]
Source: "build\dist\LabelBridge\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Dirs]
Name: "{userdocs}\Label Bridge\Inbox"

[Icons]
Name: "{group}\Label Bridge"; Filename: "{app}\LabelBridge.exe"; Parameters: "watch"
Name: "{group}\Label Bridge settings"; Filename: "{app}\LabelBridge.exe"; Parameters: "settings"
Name: "{group}\Labels to Print"; Filename: "{userdocs}\Label Bridge\Inbox"
Name: "{userdesktop}\Labels to Print"; Filename: "{userdocs}\Label Bridge\Inbox"; Tasks: desktopicon
Name: "{userstartup}\Label Bridge"; Filename: "{app}\LabelBridge.exe"; Parameters: "watch"; Tasks: startup

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Label Bridge"""; Flags: runhidden; Tasks: firewall
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Label Bridge"" dir=in action=allow program=""{app}\LabelBridge.exe"" profile=private enable=yes"; Flags: runhidden; Tasks: firewall
Filename: "{app}\LabelBridge.exe"; Parameters: "watch"; Description: "Start Label Bridge now"; Flags: postinstall nowait runasoriginaluser

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM LabelBridge.exe"; Flags: runhidden; RunOnceId: "StopApp"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Label Bridge"""; Flags: runhidden; RunOnceId: "DelFirewall"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { Stop a running copy so its files can be replaced. Settings and labels are kept. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM LabelBridge.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;
