<#
  定时采集任务管理（项目第 3 步）

  定时：每天 10:00 / 15:00 / 19:00
  内容：CrawlerStudio.exe --task run_daily --silent
        （run_daily 采完 5 个站点后，自己接着跑 analysis.report 生成报告）

  一般不用手敲命令，直接双击 tools 下这几个 bat：
    install_task.bat   安装任务（只在你登录时运行，不需要管理员）
    remove_task.bat    删除任务
    run_task_now.bat   立刻跑一次（验证用）
    task_status.bat    看状态和上次运行结果

  也可以自己调：
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\scheduler.ps1 -Action dryrun
#>
param(
    [ValidateSet('install', 'remove', 'run', 'status', 'dryrun')]
    [string]$Action = 'status',

    [string]$Exe = '',

    [string[]]$Times = @('10:00', '15:00', '19:00'),

    [string]$TaskName = 'crawler_daily'
)

$ErrorActionPreference = 'Stop'

if (-not $Exe) {
    $root = Split-Path -Parent $PSScriptRoot              # tools 的上一级就是项目根
    $Exe = Join-Path $root 'dist\CrawlerStudio\CrawlerStudio.exe'
}
$ExeArgs = '--task run_daily --silent'
$WorkDir = Split-Path -Parent $Exe

function Show-Plan {
    Write-Host '---------------- 将要注册的任务 ----------------'
    Write-Host "任务名    : $TaskName"
    Write-Host "程序      : $Exe"
    Write-Host "参数      : $ExeArgs   （--silent = 把黑窗藏掉）"
    Write-Host "工作目录  : $WorkDir"
    Write-Host "每天几点  : $($Times -join '  /  ')"
    Write-Host '设置      : 错过就尽快补跑 / 不重复启动 / 超过 1 小时自动结束'
    if (Test-Path $Exe) {
        Write-Host '程序检查  : 找到 exe（OK）' -ForegroundColor Green
    }
    else {
        Write-Host '程序检查  : 还没打包出来 -> 先做第 5 步打包，再回来装任务' -ForegroundColor Yellow
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
        Write-Host '先做第 5 步（PyInstaller 打包），或者用 -Exe 指定 exe 的路径。' -ForegroundColor Yellow
        exit 1
    }
    Show-Plan
    $taskAction = New-ScheduledTaskAction -Execute $Exe -Argument $ExeArgs -WorkingDirectory $WorkDir
    $triggers = foreach ($t in $Times) { New-ScheduledTaskTrigger -Daily -At $t }
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    try {
        Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $triggers `
            -Settings $settings -Force -Description '爬虫定时采集：run_daily 采完接着生成报告' | Out-Null
    }
    catch {
        Write-Host "注册失败：$($_.Exception.Message)" -ForegroundColor Red
        Write-Host '如果提示"拒绝访问"，就右键 install_task.bat -> 以管理员身份运行，再试一次。' -ForegroundColor Yellow
        exit 1
    }
    Write-Host "已注册任务：$TaskName" -ForegroundColor Green
    Write-Host '立刻验证：双击 run_task_now.bat，跑几分钟后再双击 task_status.bat 看结果码。'
    return
}

if ($Action -eq 'remove') {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "已删除任务：$TaskName" -ForegroundColor Green
    }
    else {
        Write-Host "本来就没有这个任务：$TaskName" -ForegroundColor Yellow
    }
    return
}

if ($Action -eq 'run') {
    if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
        Write-Host "任务还没装：$TaskName，先双击 install_task.bat" -ForegroundColor Yellow
        exit 1
    }
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "已触发 $TaskName —— 采集要跑几分钟，跑完双击 task_status.bat 看结果码（0 就是成功）" -ForegroundColor Green
    return
}

# ---------------- 剩下就是 status ----------------
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "没有这个任务：$TaskName（还没安装）" -ForegroundColor Yellow
    Write-Host '双击 install_task.bat 可以安装（记得先打包出 exe）。'
    return
}
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "任务名    : $($task.TaskName)"
Write-Host "状态      : $($task.State)"
Write-Host "上次运行  : $($info.LastRunTime)   结果码：$($info.LastTaskResult)"
Write-Host "下次运行  : $($info.NextRunTime)"
foreach ($t in $task.Triggers) { Write-Host "触发时间  : $($t.StartBoundary)" }
Write-Host '结果码：0 = 成功，2 = 找不到程序，其它值可以搜"任务计划程序 结果码"' -ForegroundColor DarkGray
