[Setup]
AppName=AudioMorph Studio
AppVersion=2.1
AppPublisher=Evoless
DefaultDirName={autopf}\AudioMorph Studio
DefaultGroupName=AudioMorph Studio
AllowNoIcons=yes
OutputDir=.
OutputBaseFilename=AudioMorph_Setup_v2.1
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\AudioMorph\AudioMorph.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\AudioMorph\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\AudioMorph Studio"; Filename: "{app}\AudioMorph.exe"; IconFilename: "{app}\icon.ico"
Name: "{group}\Uninstall AudioMorph Studio"; Filename: "{uninstallexe}"
Name: "{autodesktop}\AudioMorph Studio"; Filename: "{app}\AudioMorph.exe"; Tasks: desktopicon; IconFilename: "{app}\icon.ico"

[Run]
Filename: "{app}\AudioMorph.exe"; Description: "{cm:LaunchProgram,AudioMorph Studio}"; Flags: nowait postinstall skipifsilent
