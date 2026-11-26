; ==============================================================================
; AudioMorph Studio — Production Windows Installer Script (Inno Setup 6)
; Features: Multi-Language (English, French, Darija), Localized EULA,
;           Modern Wizard, Safe Upgrades, Language Persistence & UX Guards.
; ==============================================================================

#define MyAppName "AudioMorph Studio"
#define MyAppVersion "2.2.1"
#define MyAppPublisher "Evoless"
#define MyAppURL "https://github.com/CallMeHoussam/AudioMorph"
#define MyAppExeName "AudioMorph.exe"

[Setup]
AppId={{D37F8E94-91B2-4A73-A785-3E77B13A28F1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=.
OutputBaseFilename=AudioMorph_Setup_v2.2
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
DisableProgramGroupPage=yes

; --- Multi-Language Selection on Launch ---
ShowLanguageDialog=yes
UsePreviousLanguage=no

; --- Safe Upgrades & Running Application Handling ---
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"; LicenseFile: "installer_assets\EULA_en.txt"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"; LicenseFile: "installer_assets\EULA_fr.txt"
Name: "darija"; MessagesFile: "installer_assets\Darija.isl"; LicenseFile: "installer_assets\EULA_darija.txt"

[CustomMessages]
en.CreateDesktopIcon=Create a desktop shortcut
en.LaunchProgram=Launch AudioMorph Studio
en.KeepSettings=Preserve custom user settings and presets
fr.CreateDesktopIcon=Créer un raccourci sur le Bureau
fr.LaunchProgram=Lancer AudioMorph Studio
fr.KeepSettings=Conserver les paramètres et profils personnalisés
darija.CreateDesktopIcon=إنشاء اختصار على سطح المكتب (Desktop)
darija.LaunchProgram=تشغيل AudioMorph Studio
darija.KeepSettings=الاحتفاظ بالإعدادات والملفات الشخصية

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Primary application executable
Source: "dist\AudioMorph\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Application dependencies, libraries, and runtime files
Source: "dist\AudioMorph\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "settings.json"

; Default settings template (do not overwrite existing user settings on upgrade)
Source: "settings.example.json"; DestDir: "{app}"; DestName: "settings.json"; Flags: onlyifdoesntexist uninsneveruninstall

; Application icon
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; EULA documents for user offline reference
Source: "installer_assets\EULA_en.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "installer_assets\EULA_fr.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "installer_assets\EULA_darija.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\icon.ico"

[Registry]
; Persist user's selected installer language for the application runtime
Root: HKCU; Subkey: "Software\AudioMorphStudio"; ValueType: string; ValueName: "Language"; ValueData: "{language}"; Flags: uninsdeletekeyifempty

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up runtime cache and log files on uninstall, leaving no residue
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.log.*"
Type: files; Name: "{app}\download_history.json"
Type: filesandordirs; Name: "{app}\temp"
Type: filesandordirs; Name: "{app}\tmp"
Type: filesandordirs; Name: "{app}\.cache"
