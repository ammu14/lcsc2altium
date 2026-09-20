; LCSC 元件导出器 —— Inno Setup 安装包脚本
; 编译: 在仓库根目录运行 installer\build_installer.ps1
;
; 特性:
;   - 安装前检测 Python（注册表 + py/python 命令双重检测），没有则提示并终止
;   - 免管理员（装到 %LOCALAPPDATA%\Programs）
;   - 桌面/开始菜单快捷方式（.pyw 关联 pythonw 直接开窗）
;   - 不打包: .git / out / __pycache__ / ai_config.json（用户本机密钥）/ 安装器自身

#define AppName      "LCSC 元件导出器"
; 版本号唯一来源是 lcsc_exporter/__init__.py 的 __version__；
; build_installer.ps1 用 /DAppVersion= 传入，这里只是手动编译时的兜底。
#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
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
Source: "..\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion; Excludes: ".git\*,out\*,__pycache__\*,*.pyc,ai_config.json,dist\*,build\*,wheels\*,installer\*,.tools\innosetup-installer.exe,.tools\innosetup\*,.tools\pybuild\*,dl_inno*.py,probe_*.py,test_*.py,*.spec,lcsc_preview_*\*,.dsh-vision-router\*"

[Icons]
; 目标直指 pythonw.exe + 脚本参数，不依赖 ".pyw 文件关联"
;（Store 版 Python 等环境下该关联常缺失，双击会弹"选择打开方式"）
Name: "{autodesktop}\{#AppName}"; Filename: "{code:GetPythonw}"; Parameters: "{code:GetScriptParam}"; WorkingDir: "{app}"
Name: "{group}\{#AppName}"; Filename: "{code:GetPythonw}"; Parameters: "{code:GetScriptParam}"; WorkingDir: "{app}"
Name: "{group}\使用手册"; Filename: "{app}\使用手册.md"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{code:GetPythonw}"; Parameters: "{code:GetScriptParam}"; Description: "安装完成后立即运行"; Flags: postinstall skipifsilent unchecked

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

// ---- 解析 pythonw.exe 绝对路径（安装时执行）----
// 依次尝试: 1) 注册表 PythonCore\*\InstallPath  2) Microsoft Store 别名
//           3) PATH 里 where pythonw  4) 兜底退回 .pyw（依赖文件关联）
var
  PythonwCache: String;

function FindPythonwInHive(RootKey: Integer; const SubKey: String): String;
var
  Versions: TArrayOfString;
  I: Integer;
  P: String;
begin
  Result := '';
  if RegGetSubkeyNames(RootKey, SubKey, Versions) then
    for I := 0 to GetArrayLength(Versions) - 1 do
      if RegQueryStringValue(RootKey,
           SubKey + '\' + Versions[I] + '\InstallPath', '', P) then
        if (P <> '') and FileExists(AddBackslash(P) + 'pythonw.exe') then
        begin
          Result := AddBackslash(P) + 'pythonw.exe';
          Exit;
        end;
end;

function FindPythonw: String;
var
  TmpFile, Line: String;
  Lines: TArrayOfString;
  Res: Integer;
begin
  // 1) 注册表（python.org 安装包）
  Result := FindPythonwInHive(HKCU, 'SOFTWARE\Python\PythonCore');
  if Result = '' then
    Result := FindPythonwInHive(HKLM, 'SOFTWARE\Python\PythonCore');
  if Result = '' then
    Result := FindPythonwInHive(HKLM, 'SOFTWARE\WOW6432Node\Python\PythonCore');
  // 2) Microsoft Store 版 Python 的别名路径
  if Result = '' then
  begin
    Result := ExpandConstant('{localappdata}\Microsoft\WindowsApps\pythonw.exe');
    if not FileExists(Result) then
      Result := '';
  end;
  // 3) PATH 里找（scoop/choco/手动加 PATH 的情况）
  if Result = '' then
  begin
    TmpFile := ExpandConstant('{tmp}\lcsc_pythonw.txt');
    if Exec('cmd.exe', '/c where pythonw.exe > "' + TmpFile + '" 2>nul', '',
            SW_HIDE, ewWaitUntilTerminated, Res) and (Res = 0)
       and LoadStringsFromFile(TmpFile, Lines)
       and (GetArrayLength(Lines) > 0) then
    begin
      Line := Trim(Lines[0]);
      if FileExists(Line) then
        Result := Line;
    end;
    DeleteFile(TmpFile);
  end;
  // 4) 兜底：退回 .pyw 脚本本身（老行为，依赖 .pyw 文件关联）
  if Result = '' then
    Result := ExpandConstant('{app}\lcsc2altium_gui.pyw');
end;

function GetPythonw(Param: String): String;
begin
  if PythonwCache = '' then
    PythonwCache := FindPythonw;
  Result := PythonwCache;
end;

function GetScriptParam(Param: String): String;
begin
  Result := '"' + ExpandConstant('{app}\lcsc2altium_gui.pyw') + '"';
end;
