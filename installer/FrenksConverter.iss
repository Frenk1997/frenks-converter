; Установщик Frenk's Converter (Inno Setup 6).
; Собирается скриптом tools\build.py — он передаёт версию и генерирует formats.iss.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Frenk's Converter"
#define AppExe "FrenksConverter.exe"
#define AppUrl "https://github.com/Frenk1997/frenks-converter"

[Setup]
AppId={{7C3F2A9E-5B14-4D8E-9A61-F0B2C4E8D713}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Frenk's
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
DefaultDirName={localappdata}\Programs\Frenk's Converter
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=FrenksConverter-{#AppVersion}-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
AppMutex=FrenksConverterMutex
CloseApplications=yes
ChangesAssociations=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.ContextMenu=Добавить «Конвертировать в…» в меню правой кнопки мыши
english.ContextMenu=Add "Convert to…" to the right-click menu
russian.SendTo=Добавить в меню «Отправить»
english.SendTo=Add to the "Send to" menu
russian.Integration=Интеграция с Windows:
english.Integration=Windows integration:
russian.MenuTitle=Конвертировать в…
english.MenuTitle=Convert to…
russian.MenuOther=Другой формат…
english.MenuOther=Other format…

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "contextmenu"; Description: "{cm:ContextMenu}"; GroupDescription: "{cm:Integration}"
Name: "sendto"; Description: "{cm:SendTo}"; GroupDescription: "{cm:Integration}"; Flags: unchecked

[Files]
Source: "..\dist\FrenksConverter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{usersendto}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: sendto

[Registry]
#include "formats.iss"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\FrenksConverter"
