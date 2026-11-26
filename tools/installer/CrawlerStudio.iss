; ============================================================
;  CrawlerStudio 安装脚本（向导生成 + 手工整理）
;  用法：用 Inno Setup Compiler 打开本文件 → 按 F9 编译
;  产物：项目根的 installer\CrawlerStudio_Setup_v0.4.0.exe
;
;  相对路径说明：Inno 里 Source/OutputDir 等相对路径是相对"本 .iss 所在目录"的，
;  所以这里用 ..\..\ 回到项目根。
; ============================================================

#define MyAppName "CrawlerStudio"
#define MyAppVersion "0.4.0"
#define MyAppPublisher "个人学习项目"
#define MyAppURL "https://github.com/sogni-dei-pittori/CrawlerStudio"
#define MyAppExeName "CrawlerStudio.exe"

[Setup]
; ★ AppId 是这个软件的身份，生成一次就永远别改（升级、卸载都靠它认出"同一个软件"）
AppId={{772F36B7-1EBB-4FC1-9D2B-8A28761BC044}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; ---- 安装位置：免管理员模式（{autopf} 会变成 %LOCALAPPDATA%\Programs，不弹 UAC）----
DefaultDirName={autopf}\{#MyAppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
; ---- 64 位 ----
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; ---- 界面与图标 ----
WizardStyle=modern
SetupIconFile=..\..\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; ---- 压缩：体积最小（代价是编译多花几分钟）----
Compression=lzma2/max
SolidCompression=yes
; ---- 输出到项目根的 installer\ ----
OutputDir=..\..\installer
OutputBaseFilename=CrawlerStudio_Setup_v{#MyAppVersion}
; ---- 安装过程写日志，出问题好排查（也可以用 安装包 /LOG=路径）----
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; ★ recursesubdirs / createallsubdirs 必须有：Nuitka 的 dist 是"一个文件夹"，
;   少了它安装包只会装一个 exe，程序根本跑不起来。
; ★ Excludes：把运行期数据排除掉 —— 那是"我机器上"的东西，不该装给别人。
Source: "..\..\build_nuitka\main.dist\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "data\*,reports\*,logs\*,views\*,*.bak-*,debug.log"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
