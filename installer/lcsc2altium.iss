; LCSC 元件导出器 —— Inno Setup 安装包脚本
; 编译: 在仓库根目录运行 installer\build_installer.ps1
;
; 特性:
;   - 安装前检测 Python（注册表 + py/python 命令双重检测），没有则提示并终止
;   - 免管理员（装到 %LOCALAPPDATA%\Programs）
;   - 桌面/开始菜单快捷方式（.pyw 关联 pythonw 直接开窗）
;   - 不打包: .git / out / __pycache__ / ai_config.json（用户本机密钥）/ 安装器自身

#define AppName      "LCSC 元件导出器"
#define AppVersion   "1.1.0"
#define AppPublisher "lcsc2altium"
#define AppId        "{{7F3A2B1C-9D4E-4A5F-B8C6-2E1D0F9A8B7C}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\lcsc2altium
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=lcsc2altium-setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no
UninstallDisplayName={#AppName}

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion; Excludes: ".git\*,out\*,__pycache__\*,*.pyc,ai_config.json,dist\*,installer\*,.tools\innosetup-installer.exe,.tools\innosetup\*,dl_inno*.py,probe_*.py,test_*.py"

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\lcsc2altium_gui.pyw"; WorkingDir: "{app}"
Name: "{group}\{#AppName}"; Filename: "{app}\lcsc2altium_gui.pyw"; WorkingDir: "{app}"
Name: "{group}\使用手册"; Filename: "{app}\使用手册.md"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\lcsc2altium_gui.pyw"; Description: "安装完成后立即运行"; Flags: shellexec postinstall skipifsilent unchecked

[Code]
// Python 检测: 先看注册表（python.org 安装包会写），再实际跑 python/py --version
function PythonRegistered: Boolean;
begin
  Result := RegKeyExists(HKLM, 'SOFTWARE\Python\PythonCore') or
            RegKeyExists(HKCU, 'SOFTWARE\Python\PythonCore') or
            RegKeyExists(HKLM, 'SOFTWARE\WOW6432Node\Python\PythonCore');
end;

function PythonRunnable: Boolean;
var
  Code: Integer;
begin
  Result := Exec('cmd.exe', '/c python --version >nul 2>&1', '', SW_HIDE,
                 ewWaitUntilTerminated, Code) and (Code = 0);
  if not Result then
    Result := Exec('cmd.exe', '/c py --version >nul 2>&1', '', SW_HIDE,
                   ewWaitUntilTerminated, Code) and (Code = 0);
end;

function InitializeSetup: Boolean;
var
  ErrorCode: Integer;
begin
  if PythonRegistered or PythonRunnable then
  begin
    Result := True;
    Exit;
  end;
  if MsgBox('未检测到 Python 环境。'#13#10#13#10
            + '本工具需要 Python 3.10 及以上版本才能运行。'#13#10
            + '是否现在打开 Python 官网下载页（下载后安装时请务必勾选 Add Python to PATH）？'#13#10#13#10
            + '装完 Python 后请重新运行本安装包。',
            mbCriticalError, MB_YESNO) = IDYES then
    ShellExec('open', 'https://www.python.org/downloads/', '', '', SW_SHOW,
              ewNoWait, ErrorCode);
  Result := False;
end;
