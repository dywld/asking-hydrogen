# Windows PowerShell 5.1 / 사용자의 로그인 세션에서 브라우저를 실행합니다.
param([switch]$Run, [switch]$Publish)
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:LOCALAPPDATA 'asking-hydrogen\kgs-daily'
$runtime = $PSScriptRoot
$python = Join-Path $base 'venv\Scripts\python.exe'
$entry = Join-Path $runtime 'kgs_browser.py'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$taskName = "AskingHydrogen-KGS-FP216-$($identity.User.Value)"
$codeFiles = @('kgs_browser.py', 'fetch_kgs_code.py', 'kgs_cloud.py', 'kgs_watch.py', 'ingest_kgs_code.py', 'extract_annex.py')

try {
    if ($Run) {
        if (-not [IO.File]::Exists($python)) { throw '예약용 Python 환경을 찾지 못했습니다. 설정을 다시 실행하세요.' }
        $log = Join-Path $base '최근실행.txt'
        $env:PYTHONIOENCODING = 'utf-8'
        $env:PYTHONUTF8 = '1'
        $env:PYTHONUNBUFFERED = '1'
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        $runArgs = @('-X', 'utf8', $entry, '--root', $base, '--code', 'FP216')
        if ($Publish) {
            $userKey = [Environment]::GetEnvironmentVariable('KGS_PUSH_KEY', 'User')
            if ($userKey) { $env:KGS_PUSH_KEY = $userKey }
            $userUrl = [Environment]::GetEnvironmentVariable('KGS_PUSH_URL', 'User')
            if ($userUrl) { $env:KGS_PUSH_URL = $userUrl }
            $runArgs += '--publish'
        }
        "시작 $(Get-Date -Format s)" | Out-File -LiteralPath $log -Encoding utf8
        # PowerShell 5.1은 네이티브 stderr도 오류 객체로 보낸다. 종료 코드는 Python에서 받는다.
        $ErrorActionPreference = 'Continue'
        & $python @runArgs 2>&1 | Out-File -LiteralPath $log -Append -Encoding utf8
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        "완료 $(Get-Date -Format s) / 종료 코드 $exitCode" | Out-File -LiteralPath $log -Append -Encoding utf8
        exit $exitCode
    }

    $choice = Read-Host '매일 실행할 시각을 24시간제로 입력하세요 (예 09:00). 기존 예약 해제는 X'
    if ($choice -eq 'X') {
        $existing = Get-ScheduledTask -TaskPath '\' | Where-Object TaskName -eq $taskName
        if ($existing) { Unregister-ScheduledTask -TaskName $taskName -TaskPath '\' -Confirm:$false }
        Write-Host '예약을 해제했습니다.'
        exit 0
    }
    if ($choice -notmatch '^(?:[01][0-9]|2[0-3]):[0-5][0-9]$') { throw '09:00 또는 18:30처럼 시각을 입력하세요.' }
    $publishChoice = Read-Host '웹 챗봇 게시도 켤까요? 기본은 수집만 합니다 (웹 게시 Y / 수집만 Enter)'
    if ($publishChoice -notin @('','Y','N')) { throw 'Enter, Y 또는 N을 입력하세요.' }
    $enablePublish = $publishChoice -eq 'Y'
    if ($enablePublish -and -not [Environment]::GetEnvironmentVariable('KGS_PUSH_KEY', 'User') -and
        -not [Environment]::GetEnvironmentVariable('KGS_PUSH_KEY', 'Machine')) {
        throw '웹 게시에는 Windows 사용자 환경 변수 KGS_PUSH_KEY가 필요합니다. 담당자가 설정한 뒤 재실행하거나, Enter를 골라 PDF부터 수집하세요.'
    }
    foreach ($name in $codeFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $name) -PathType Leaf)) {
            throw "팀 저장소 전체를 받은 폴더 안에서 실행하세요. 누락된 파일 $name"
        }
    }
    $seed = Join-Path $PSScriptRoot 'data\kgs_code.jsonl'
    if (-not (Test-Path -LiteralPath $seed -PathType Leaf)) { throw '팀 저장소의 data\kgs_code.jsonl이 필요합니다.' }
    $null = [IO.Directory]::CreateDirectory((Join-Path $base 'data'))
    if (-not (Test-Path -LiteralPath $python)) {
        $created = $false
        foreach ($command in @('py','python')) {
            if (-not (Get-Command $command -CommandType Application -ErrorAction SilentlyContinue)) { continue }
            $prefix = @()
            if ($command -eq 'py') { $prefix = @('-3') }
            & $command @prefix -c 'import sys; sys.exit(sys.version_info < (3,10))'
            if ($LASTEXITCODE -ne 0) { continue }
            & $command @prefix -m venv (Join-Path $base 'venv')
            if ($LASTEXITCODE -ne 0) { throw '전용 Python 환경을 만들지 못했습니다.' }
            $created = $true
            break
        }
        if (-not $created) { throw 'Python 3.10 이상을 설치한 뒤 다시 실행하세요.' }
    }
    & $python -m pip install --disable-pip-version-check 'playwright>=1.51,<2' 'pymupdf>=1.25,<2'
    if ($LASTEXITCODE -ne 0) { throw '필요한 Python 도구 설치에 실패했습니다.' }

    # 새 버전은 별도의 폴더에 완성한 뒤 예약을 전환한다. 실행 중인 이전 작업과 파일을 공유하지 않는다.
    $allFiles = $codeFiles + @('register_kgs_task.ps1')
    $hashes = foreach ($name in $allFiles) {
        (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot $name)).Hash
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::ASCII.GetBytes(($hashes -join '')))).Replace('-','') }
    finally { $sha.Dispose() }
    $runtime = Join-Path $base ('runtime-' + $hash.Substring(0,16))
    if (-not [IO.Directory]::Exists($runtime)) {
        $staging = Join-Path $base ('install-' + [guid]::NewGuid().ToString('N'))
        $null = [IO.Directory]::CreateDirectory($staging)
        try {
            foreach ($name in $allFiles) {
                [IO.File]::Copy((Join-Path $PSScriptRoot $name), (Join-Path $staging $name))
            }
            [IO.Directory]::Move($staging, $runtime)
        } finally {
            if ([IO.Directory]::Exists($staging)) { [IO.Directory]::Delete($staging, $true) }
        }
    }
    $runner = Join-Path $runtime 'register_kgs_task.ps1'
    $entry = Join-Path $runtime 'kgs_browser.py'
    $dataset = Join-Path $base 'data\kgs_code.jsonl'
    if (-not [IO.File]::Exists($dataset)) {
        $seedTmp = "$dataset.$([guid]::NewGuid()).tmp"
        try {
            [IO.File]::Copy($seed, $seedTmp)
            [IO.File]::Move($seedTmp, $dataset)
        } finally { if ([IO.File]::Exists($seedTmp)) { [IO.File]::Delete($seedTmp) } }
    }
    & $python -X utf8 $entry --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '실행 파일과 Python 설치를 확인하지 못했습니다.' }
    $at = [datetime]::ParseExact($choice, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture)
    if ($at -le (Get-Date)) { $at = $at.AddDays(1) }
    $trigger = New-ScheduledTaskTrigger -Daily -At $at
    $account = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
    $shell = Join-Path $PSHOME 'powershell.exe'
    $runCommand = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -Run' -f $runner
    if ($enablePublish) { $runCommand += ' -Publish' }
    $action = New-ScheduledTaskAction -Execute $shell -WorkingDirectory $runtime -Argument $runCommand
    Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Action $action -Trigger $trigger -Principal $account -Settings $settings -Force | Out-Null
    $info = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
    Write-Host "예약 완료. 다음 실행 $($info.NextRunTime) (PC 현지 시각)"
    Write-Host "결과 폴더 $base"
    Write-Host 'PC를 켜고 Windows에 로그인해 두세요. 예약 시각 변경 또는 해제는 이 파일을 다시 실행하세요.'
    exit 0
} catch {
    if ($Run -and (Test-Path -LiteralPath $base)) {
        $_.Exception.Message | Out-File -LiteralPath (Join-Path $base '최근실행.txt') -Append -Encoding utf8
    }
    Write-Host "실패 — $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
