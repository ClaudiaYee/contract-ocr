# 本地打包 ContractOCR.exe（与 .github/workflows/windows-desktop.yml 的步骤一致）
# 用法：在项目根目录双击「打包.bat」，或在 PowerShell 中运行：
#   powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1
# 可选参数：
#   -Mirror          国内网络：语义模型从 hf-mirror.com 下载，pip 使用清华镜像
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
    & py -3.11 -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = @('py', '-3.11') }
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

Step '3/8 准备语义模型（models\semantic_model）'
if ($RefreshModels -or -not (Test-Path 'models\semantic_model\model_quantized.onnx')) {
    Run $bp @('native\fetch_semantic_model.py')
} else { Write-Host '已存在，跳过下载。' }

Step '4/8 准备 PP-OCRv5 OCR 模型（单独环境 .venv-models）'
if (-not (Test-Path '.venv-models\Scripts\python.exe')) { Run $pyExe ($pyArgs + @('-m', 'venv', '.venv-models')) }
$mp = (Resolve-Path '.venv-models\Scripts\python.exe').Path
if ($RefreshModels -or -not (Test-Path 'models\ocr_models\ppocrv5_rec_server.onnx')) {
    Run $mp (@('-m', 'pip', 'install', 'rapidocr==3.8.4', 'onnxruntime') + $pipMirror)
    Run $mp @('native\fetch_ocr_models.py')
} else { Write-Host '已存在，跳过下载。' }

Step '5/8 生成 int8 检测模型（失败也不影响，程序会用原始检测模型）'
try {
    Run $mp (@('-m', 'pip', 'install', 'onnx', 'sympy', 'rapidocr_onnxruntime==1.4.4') + $pipMirror)
    Run $mp @('tools\quantize_ocr.py', 'models\ocr_models', '--det-only')
} catch { Write-Warning "int8 检测模型未生成：$($_.Exception.Message)" }

Step '6/8 检查 OCR 模型能正常加载'
Run $bp @('native\check_ocr_models.py')

Step '7/8 用 PyInstaller 打包'
Run $bp @('native\make_version_info.py', 'version_info.txt')
$hidden = 'documents engine semantic page_quality layout_quality recovery ocr_cache text_normalize date_review ocr_dictionary excel_table'.Split(' ')
$piArgs = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--name', 'ContractOCR',
    '--version-file', 'version_info.txt', '--noupx', '--paths', 'native')
foreach ($m in $hidden) { $piArgs += @('--hidden-import', $m) }
foreach ($p in 'rapidocr_onnxruntime onnxruntime pyclipper shapely pymupdf tokenizers'.Split(' ')) { $piArgs += @('--collect-all', $p) }
$piArgs += @('--add-data', 'models/semantic_model;semantic_model', '--add-data', 'models/ocr_models;ocr_models',
    '--add-data', 'index.html;web', '--add-data', 'js;web/js', '--add-data', 'css;web/css',
    '--add-data', 'assets;web/assets', '--add-data', 'lib;web/lib', 'native/desktop.py')
Run $bp $piArgs
$exe = Join-Path $Root 'dist\ContractOCR\ContractOCR.exe'
if (-not (Test-Path $exe)) { throw '打包结束但没有找到 dist\ContractOCR\ContractOCR.exe' }

Step '8/8 自检并压缩'
if (-not $SkipSmokeTest) {
    Run $bp @('native\smoke_windows.py', $exe)
    if (Test-Path 'packaged-validation.json') { Copy-Item 'packaged-validation.json' 'dist\ContractOCR\validation_report.json' -Force }
} else { Write-Host '已跳过 EXE 自检。' }
Copy-Item 'README.md' 'dist\ContractOCR\README.md' -Force
if (-not $NoZip) {
    $zip = Join-Path $Root 'ContractOCR-Windows-x64.zip'
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path 'dist\ContractOCR' -DestinationPath $zip
    $hash = (Get-FileHash $zip -Algorithm SHA256).Hash
    Write-Host "`n压缩包：$zip`nSHA256：$hash" -ForegroundColor Green
}
Write-Host "`n完成！程序位置：$exe" -ForegroundColor Green
