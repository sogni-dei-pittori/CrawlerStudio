<#
  开机自启管理（项目第 4 步）

  做法：在"启动"文件夹里放一个快捷方式（不改注册表、不装服务、不需要管理员）：
        %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\CrawlerStudio.lnk
  好处：任务管理器 -> 启动 里能看到、能一键禁用；删掉快捷方式就干净了。

  快捷方式指向：CrawlerStudio.exe --minimized
  （--minimized = 开机后直接躲进托盘，不弹窗口；要看界面就点/双击托盘图标）

  一般不用手敲，双击 tools 下这两个：
    install_autostart.bat
    remove_autostart.bat
#>
param(
    [ValidateSet('install', 'remove', 'status', 'dryrun')]
    [string]$Action = 'status',

    [string]$Exe = '',

    [string]$LinkPath = ''      # 一般不用管；给测试用（不指定就放"启动"文件夹）
)

$ErrorActionPreference = 'Stop'

if (-not $Exe) {
    $root = Split-Path -Parent $PSScriptRoot              # tools 的上一级就是项目根
    $Exe = Join-Path $root 'dist\CrawlerStudio\CrawlerStudio.exe'
}
if (-not $LinkPath) {
    $LinkPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'CrawlerStudio.lnk'
}
$ExeArgs = '--minimized'
$WorkDir = Split-Path -Parent $Exe

function Show-Plan {
    Write-Host '------------ 开机自启（快捷方式方案）------------'
    Write-Host "快捷方式  : $LinkPath"
    Write-Host "指向程序  : $Exe"
    Write-Host "参数      : $ExeArgs   （--minimized = 开机后直接躲进托盘）"
    Write-Host "工作目录  : $WorkDir"
    Write-Host '当前状态  : ' -NoNewline
    if (Test-Path $LinkPath) { Write-Host '已经装过了（再装一次就是覆盖）' -ForegroundColor Yellow }
    else { Write-Host '还没装' }
    if (Test-Path $Exe) {
        Write-Host '程序检查  : 找到 exe（OK）' -ForegroundColor Green
    }
    else {
        Write-Host '程序检查  : 还没打包出来 -> 先做打包，再回来装' -ForegroundColor Yellow
    }
    Write-Host '------------------------------------------------'
}

if ($Action -eq 'dryrun') {
    Show-Plan
    return
}

if ($Action -eq 'install') {
    if (-not (Test-Path $Exe)) {
        Write-Host "找不到程序：$Exe" -ForegroundColor Red
        Write-Host '先打包出 exe，或者用 -Exe 指定 exe 的路径。' -ForegroundColor Yellow
        exit 1
    }
    Show-Plan
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($LinkPath)
    $lnk.TargetPath = $Exe
    $lnk.Arguments = $ExeArgs
    $lnk.WorkingDirectory = $WorkDir
    $lnk.IconLocation = "$Exe,0"
    $lnk.Description = '爬虫采集与分析工具（开机自启，静默到托盘）'
    $lnk.Save()
    Write-Host "已装好：$LinkPath" -ForegroundColor Green
    Write-Host '不想开机自启了：双击 remove_autostart.bat，或在 任务管理器 -> 启动 里禁用。'
    return
}

if ($Action -eq 'remove') {
    if (Test-Path $LinkPath) {
        Remove-Item $LinkPath -Force
        Write-Host "已删除：$LinkPath" -ForegroundColor Green
    }
    else {
        Write-Host "本来就没装：$LinkPath" -ForegroundColor Yellow
    }
    return
}

# ---------------- 剩下就是 status ----------------
if (Test-Path $LinkPath) {
    $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut($LinkPath)
    Write-Host "已装开机自启：$LinkPath"
    Write-Host "  指向程序  : $($lnk.TargetPath)"
    Write-Host "  参数      : $($lnk.Arguments)"
    Write-Host "  工作目录  : $($lnk.WorkingDirectory)"
}
else {
    Write-Host "还没装开机自启：$LinkPath" -ForegroundColor Yellow
    Write-Host '双击 install_autostart.bat 可以安装（记得先打包出 exe）。'
}
