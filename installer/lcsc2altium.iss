; LCSC 元件导出器 —— Inno Setup 安装包脚本
; 编译: 在仓库根目录运行 installer\build_installer.ps1
;
; 特性:
;   - 安装前实际运行候选 Python，要求 64 位、3.10-3.14；不兼容则提示并终止
;   - 免管理员（装到 %LOCALAPPDATA%\Programs），仅支持 64 位 Windows 10+
;   - 桌面/开始菜单快捷方式直指 pythonw.exe（不依赖 .pyw 文件关联）
;   - 不打包: .git / out / __pycache__ / ai_config.json（用户密钥）/ 调试与测试目录

#define AppName      "LCSC 元件导出器"
; 版本号唯一来源是 lcsc_exporter/__init__.py 的 __version__；
; build_installer.ps1 用 /DAppVersion= 传入，这里只是手动编译时的兜底。
#ifndef AppVersion
  #define AppVersion "1.2.3"
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
; 内置 npnp / Qt 均为 x64；Qt 6 支持 Windows 10 及以上。
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
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
Source: "..\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion; Excludes: ".git\*,.gitignore,out\*,out_*\*,__pycache__\*,*.pyc,ai_config.json,dist\*,build\*,wheels\*,installer\*,skills\*,tests\*,dbg_*,dbg_*\*,.tools\innosetup-installer.exe,.tools\innosetup\*,.tools\pybuild\*,dl_inno*.py,probe_*.py,test_*.py,*.spec,lcsc_preview_*\*,.dsh-vision-router\*"

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
// 内置 PySide6 6.11.2 的 wheel 要求：64 位 CPython >=3.10,<3.15。
// 用候选解释器实际执行检查，避免多版本共存时选到不兼容的那个。
const
  PY_CHECK = 'import sys,struct;sys.exit(0 if (3,10)<=sys.version_info[:2]<(3,15) and struct.calcsize(''P'')==8 else 42)';

var
  PythonwCache: String;

function PythonCommandSupported(const PythonExe: String): Boolean;
var
  Code: Integer;
begin
  // 直接 Exec 解释器，不经过 cmd.exe：避免引号/重定向被 Python 当参数。
  // 返回码 0 = 64 位且版本在 3.10-3.14；42 = 版本/位数不符；其他 = 无法运行。
  Result := Exec(PythonExe, '-c "' + PY_CHECK + '"', '', SW_HIDE,
                 ewWaitUntilTerminated, Code) and (Code = 0);
end;

function PythonwSupported(const Pythonw: String): Boolean;
var
  PythonExe: String;
begin
  PythonExe := AddBackslash(ExtractFileDir(Pythonw)) + 'python.exe';
  if not FileExists(PythonExe) then
    PythonExe := Pythonw;
  Result := PythonCommandSupported(PythonExe);
end;

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
        if P <> '' then
        begin
          P := AddBackslash(P) + 'pythonw.exe';
          if FileExists(P) and PythonwSupported(P) then
          begin
            Result := P;
            Exit;
          end;
        end;
end;

function FindPythonw: String;
var
  TmpFile, Line, P: String;
  Lines: TArrayOfString;
  Res, I: Integer;
begin
  Result := '';
  // 1) 注册表（python.org 安装包），仅接受通过版本/位数检查的候选。
  Result := FindPythonwInHive(HKCU, 'SOFTWARE\Python\PythonCore');
  if Result <> '' then Exit;
  Result := FindPythonwInHive(HKLM, 'SOFTWARE\Python\PythonCore');
  if Result <> '' then Exit;
  Result := FindPythonwInHive(HKLM, 'SOFTWARE\WOW6432Node\Python\PythonCore');
  if Result <> '' then Exit;
  // 2) Microsoft Store 版 Python 的别名路径。
  P := ExpandConstant('{localappdata}\Microsoft\WindowsApps\pythonw.exe');
  if FileExists(P) and PythonwSupported(P) then
  begin
    Result := P;
    Exit;
  end;
  // 3) PATH 里逐个查找（scoop/choco/手动加 PATH 的情况）。
  TmpFile := ExpandConstant('{tmp}\lcsc_pythonw.txt');
  if Exec('cmd.exe', '/c where pythonw.exe > "' + TmpFile + '" 2>nul', '',
          SW_HIDE, ewWaitUntilTerminated, Res) and (Res = 0)
     and LoadStringsFromFile(TmpFile, Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
    begin
      Line := Trim(Lines[I]);
      if FileExists(Line) and PythonwSupported(Line) then
      begin
        Result := Line;
        break;
      end;
    end;
  DeleteFile(TmpFile);
end;

function InitializeSetup: Boolean;
var
  ErrorCode: Integer;
  Reason, W: String;
begin
  W := FindPythonw;
  if W <> '' then
  begin
    PythonwCache := W;
    Result := True;
    Exit;
  end;
  if PythonRegistered or PythonRunnable then
    Reason := '检测到 Python，但它不是受支持的 64 位 Python 3.10 - 3.14，或当前无法运行。'
  else
    Reason := '未检测到可用的 Python 环境。';
  if SuppressibleMsgBox(Reason + #13#10#13#10
            + '本工具需要 64 位 Python 3.10 - 3.14（建议 3.14.x），无需 pip 安装其他依赖。'#13#10
            + '是否现在打开 Python Windows 下载页？安装时请勾选 Add Python to PATH。'#13#10#13#10
            + '装完兼容版本后请重新运行本安装包。',
            mbCriticalError, IDNO, IDNO) = IDYES then
    ShellExec('open', 'https://www.python.org/downloads/windows/', '', '',
              SW_SHOW, ewNoWait, ErrorCode);
  Result := False;
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
