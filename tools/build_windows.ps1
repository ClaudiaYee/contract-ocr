# 本地打包 ContractOCR.exe（与 .github/workflows/windows-desktop.yml 的步骤一致）
# 用法：在项目根目录双击「打包.bat」，或在 PowerShell 中运行：
#   powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1
# 可选参数：
#   -Mirror          国内网络：pip 使用清华镜像
#   -RefreshModels   重新下载模型（默认已下载过就跳过）
#   -SkipSmokeTest   跳过打包后的 EXE 自检（更快）
#   -NoZip           只生成 dist\ContractOCR 文件夹，不压缩 zip
param(
    [switch]$Mirror,
    [switch]$RefreshModels,
    [switch]$SkipSmokeTest,
    [switch]$NoZip
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($text) { Write-Host "`n==== $text ====" -ForegroundColor Cyan }
function Run($exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "命令失败（退出码 $LASTEXITCODE）：$exe $($arguments -join ' ')" }
}

$pipMirror = @()
if ($Mirror) {
    $pipMirror = @('-i', 'https://pypi.tuna.tsinghua.edu.cn/simple')
    $env:HF_ENDPOINT = 'https://hf-mirror.com'
}

Step '1/8 检查 Python 3.11（64 位）'
$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
        $ErrorActionPreference = 'Continue'
        & py -3.11 -c "import sys" 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { $python = @('py', '-3.11') }
    } catch { } finally { $ErrorActionPreference = 'Stop' }
}
if (-not $python) {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $ver = & python -c "import sys,struct;print('%d.%d-%d' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P')*8))"
        if ($ver -eq '3.11-64') { $python = @('python') }
    }
}
if (-not $python) {
    throw '没有找到 64 位 Python 3.11。请从 https://www.python.org/downloads/release/python-3119/ 安装 "Windows installer (64-bit)"，安装时勾选 "Add python.exe to PATH"，然后重新运行。'
}
$pyExe = $python[0]; $pyArgs = @($python | Select-Object -Skip 1)
Write-Host "使用：$($python -join ' ')"

Step '2/8 创建打包环境 .venv-build 并安装依赖'
if (-not (Test-Path '.venv-build\Scripts\python.exe')) { Run $pyExe ($pyArgs + @('-m', 'venv', '.venv-build')) }
$bp = (Resolve-Path '.venv-build\Scripts\python.exe').Path
Run $bp (@('-m', 'pip', 'install', '--upgrade', 'pip') + $pipMirror)
Run $bp (@('-m', 'pip', 'install', '-r', 'requirements-native.txt', 'pyinstaller==6.22.3') + $pipMirror)

Step '3/8 （语义模型已移除，无需准备）'

Step '4-6/8 （小秘书无 OCR 版：不下载、不量化、不检查 OCR 模型）'

Step '7/8 用 PyInstaller 打包'
Run $bp @('native\make_version_info.py', 'version_info.txt')
$hidden = 'documents word_text engine stamp_removal analysis_scope page_quality layout_quality recovery ocr_cache text_normalize date_review ocr_dictionary excel_table fulltext_index'.Split(' ')
$piArgs = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--name', 'ContractOCR',
    '--version-file', 'version_info.txt', '--noupx', '--paths', 'native')
foreach ($m in $hidden) { $piArgs += @('--hidden-import', $m) }
foreach ($p in 'pymupdf'.Split(' ')) { $piArgs += @('--collect-all', $p) }
# 打包环境里可能还装着旧版本用过的 OCR 运行库；明确排除，确保安装包里没有 OCR 模型和运行库。
foreach ($x in 'rapidocr_onnxruntime rapidocr onnxruntime'.Split(' ')) { $piArgs += @('--exclude-module', $x) }
$piArgs += @('--add-data', 'index.html;web', '--add-data', 'js;web/js', '--add-data', 'css;web/css',
    '--add-data', 'assets;web/assets', '--add-data', 'lib/pdfjs;web/lib/pdfjs', 'native/desktop.py')
Run $bp $piArgs
$exe = Join-Path $Root 'dist\ContractOCR\ContractOCR.exe'
if (-not (Test-Path $exe)) { throw '打包结束但没有找到 dist\ContractOCR\ContractOCR.exe' }

Step '7b/8 替换程序里过旧的 VC++ 运行库'
# PyInstaller 有时会从 PATH 上的其他软件里收集到旧版 msvcp140.dll（例如 2017 年的 14.12）。
# 新版 onnxruntime 碰到旧版运行库会直接崩溃（0xc0000005），这里统一换成系统中更新的版本。
$runtimeNames = 'msvcp140.dll msvcp140_1.dll msvcp140_2.dll msvcp140_atomic_wait.dll msvcp140_codecvt_ids.dll vcruntime140.dll vcruntime140_1.dll concrt140.dll vcomp140.dll'.Split(' ')
$systemMsvcp = Join-Path $env:WINDIR 'System32\msvcp140.dll'
if (-not (Test-Path $systemMsvcp) -or (Get-Item $systemMsvcp).VersionInfo.FileVersionRaw -lt [version]'14.40') {
    throw '系统中的 VC++ 运行库过旧或未安装。请先安装 https://aka.ms/vs/17/release/vc_redist.x64.exe ，再重新运行打包。'
}
foreach ($bundled in Get-ChildItem 'dist\ContractOCR' -Recurse -File | Where-Object { $runtimeNames -contains $_.Name.ToLower() }) {
    $system = Join-Path $env:WINDIR ('System32\' + $bundled.Name)
    if (-not (Test-Path $system)) { continue }
    $old = $bundled.VersionInfo.FileVersionRaw; $new = (Get-Item $system).VersionInfo.FileVersionRaw
    if ($old -lt $new) {
        Copy-Item $system $bundled.FullName -Force
        Write-Host "已更新 $($bundled.FullName.Substring($Root.Length + 1))：$old -> $new"
    }
}

Step '8/8 自检并压缩'
if (-not $SkipSmokeTest) {
    Run $bp @('native\smoke_nocr.py', $exe)
    if (Test-Path 'packaged-validation.json') { Copy-Item 'packaged-validation.json' 'dist\ContractOCR\validation_report.json' -Force }
} else { Write-Host '已跳过 EXE 自检。' }
Copy-Item 'README.md' 'dist\ContractOCR\README.md' -Force
if (-not $NoZip) {
    $zip = Join-Path $Root 'ContractOCR-Assistant-NoOCR-Windows-x64.zip'
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path 'dist\ContractOCR' -DestinationPath $zip
    $hash = (Get-FileHash $zip -Algorithm SHA256).Hash
    Write-Host "`n压缩包：$zip`nSHA256：$hash" -ForegroundColor Green
}
Write-Host "`n完成！程序位置：$exe" -ForegroundColor Green
