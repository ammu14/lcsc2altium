; *** Inno Setup 简体中文消息（针对本安装向导精简翻译） ***
; 未覆盖的消息自动回退英文内置默认。

[LangOptions]
LanguageName=简体中文
LanguageID=$0804
LanguageCodePage=936

[Messages]

; *** 标题
SetupAppTitle=安装
SetupWindowTitle=安装 - %1
UninstallAppTitle=卸载
UninstallAppFullTitle=%1 卸载

; *** 常用
InformationTitle=信息
ConfirmTitle=确认
ErrorTitle=错误

; *** 启动
SetupLdrStartupMessage=即将安装 %1。是否继续？
SetupAlreadyRunning=安装程序已在运行。
LastErrorMessage=%1.%n%n错误 %2: %3

; *** 退出
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。如果现在退出，程序将不会被安装。%n%n您可以稍后再次运行安装程序完成安装。%n%n退出安装？

; *** 按钮
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonYesToAll=全部选是(&A)
ButtonNo=否(&N)
ButtonNoToAll=全部选否(&O)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&B)...
ButtonWizardBrowse=浏览(&R)...
ButtonNewFolder=新建文件夹(&M)

; *** 向导通用
ClickNext=点击"下一步"继续，或点击"取消"退出安装。

; *** 欢迎页
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=即将在您的电脑上安装 [name/ver]。%n%n建议您在继续之前关闭其他所有应用程序。

; *** 许可协议页
WizardLicense=许可协议
LicenseLabel=继续之前请阅读以下重要信息。
LicenseLabel3=请阅读以下许可协议。您必须接受本协议的条款才能继续安装。
LicenseAccepted=我接受协议(&A)
LicenseNotAccepted=我不接受协议(&D)

; *** 选择安装位置页
WizardSelectDir=选择安装位置
SelectDirDesc=要将 [name] 安装到哪里？
SelectDirLabel3=安装程序将把 [name] 安装到以下文件夹。
SelectDirBrowseLabel=点击"下一步"继续。如需选择其他文件夹，请点击"浏览"。
DiskSpaceGBLabel=至少需要 [gb] GB 的可用磁盘空间。
DiskSpaceMBLabel=至少需要 [mb] MB 的可用磁盘空间。
CannotInstallToNetworkDrive=无法安装到网络驱动器。
InvalidPath=必须输入带盘符的完整路径，例如：%n%nC:\APP
InvalidDrive=您选择的驱动器不存在或不可访问，请选择其他位置。
DiskSpaceWarningTitle=磁盘空间不足
DiskSpaceWarning=安装至少需要 %1 KB 可用空间，但所选驱动器仅有 %2 KB。%n%n仍要继续吗？
DirExistsTitle=文件夹已存在
DirExists=文件夹：%n%n%1%n%n已存在。仍要安装到该文件夹吗？

; *** 选择附加任务页
WizardSelectTasks=选择附加任务
SelectTasksDesc=要执行哪些附加任务？
SelectTasksLabel2=选择安装 [name] 时要执行的附加任务，然后点击"下一步"。

; *** 开始菜单文件夹页
WizardSelectProgramGroup=选择开始菜单文件夹
SelectStartMenuFolderDesc=要把程序的快捷方式放在哪里？
SelectStartMenuFolderLabel3=安装程序将在以下开始菜单文件夹中创建程序快捷方式。
SelectStartMenuFolderBrowseLabel=点击"下一步"继续。如需选择其他文件夹，请点击"浏览"。
NoProgramGroupCheck2=不创建开始菜单文件夹(&D)

; *** 准备安装页
WizardReady=准备安装
ReadyLabel1=安装程序已准备就绪，可以开始在您的电脑上安装 [name]。
ReadyLabel2a=点击"安装"继续，如需查看或更改设置请点击"上一步"。
ReadyLabel2b=点击"安装"继续安装。
ReadyMemoDir=安装位置：
ReadyMemoGroup=开始菜单文件夹：
ReadyMemoTasks=附加任务：

; *** 正在安装页
WizardPreparing=正在准备安装
PreparingDesc=安装程序正准备在您的电脑上安装 [name]。
WizardInstalling=正在安装
InstallingLabel=请稍候，正在将 [name] 安装到您的电脑。
CannotContinue=安装无法继续。请点击"取消"退出。

; *** 完成页
FinishedHeadingLabel=[name] 安装向导完成
FinishedLabelNoIcons=安装程序已完成 [name] 的安装。
FinishedLabel=安装程序已完成 [name] 的安装。可以通过已安装的快捷方式启动本程序。
ClickFinish=点击"完成"退出安装向导。
YesRadio=是，立即重启电脑(&Y)
NoRadio=否，稍后自行重启(&N)
RunEntryExec=运行 %1
RunEntryShellExec=查看 %1

; *** 安装阶段状态
StatusCreateDirs=正在创建目录...
StatusExtractFiles=正在释放文件...
StatusCreateIcons=正在创建快捷方式...
StatusCreateRegistryEntries=正在写注册表...
StatusSavingUninstall=正在保存卸载信息...
StatusRunProgram=正在完成安装...
StatusRollback=正在回滚更改...

; *** 杂项错误
ErrorCreatingDir=无法创建目录 "%1"
ErrorCopying=复制文件时出错：
ErrorReplacingExistingFile=替换现有文件时出错：
ErrorExecutingProgram=无法执行文件：%n%1
SetupAborted=安装未完成。%n%n请解决问题后重新运行安装程序。
SourceIsCorrupted=源文件已损坏
SourceDoesntExist=源文件 "%1" 不存在
ExistingFileReadOnly2=现有文件为只读，无法替换。

; *** 卸载
ConfirmUninstall=确定要完全卸载 %1 及其所有组件吗？
UninstallStatusLabel=请稍候，正在从您的电脑移除 %1。
UninstalledAll=%1 已成功卸载。
UninstalledMost=%1 卸载完成。%n%n部分内容未能移除，可手动删除。
WizardUninstalling=卸载状态
StatusUninstalling=正在卸载 %1...

[CustomMessages]
NameAndVersion=%1 版本 %2
AdditionalIcons=附加快捷方式：
CreateDesktopIcon=创建桌面快捷方式(&D)
ProgramOnTheWeb=%1 官方网站
UninstallProgram=卸载 %1
LaunchProgram=启动 %1
