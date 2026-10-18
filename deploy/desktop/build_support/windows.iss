#ifndef AppVersion
  #error Supply AppVersion
#endif
#ifndef WindowsVersion
  #error Supply WindowsVersion
#endif
#ifndef SourceDir
  #error Supply SourceDir
#endif
#ifndef OutputDir
  #error Supply OutputDir
#endif

[Setup]
AppId={{8B79A062-067C-46D5-94D7-A27CBAA00C33}
AppName=Thimbleby
AppVersion={#AppVersion}
VersionInfoVersion={#WindowsVersion}.0
DefaultDirName={localappdata}\Programs\Thimbleby
DefaultGroupName=Thimbleby
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=Thimbleby-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Thimbleby.exe
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Thimbleby"; Filename: "{app}\Thimbleby.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Thimbleby"; Filename: "{app}\Thimbleby.exe"; Tasks: desktopicon; WorkingDir: "{app}"

[Run]
Filename: "{app}\Thimbleby.exe"; Description: "Open Thimbleby"; Flags: nowait postinstall skipifsilent
