# Run idf.py with the ESP-IDF v5.5.4 environment installed under C:\Espressif.
# Usage: powershell -File firmware\idf.ps1 -C firmware\csi_probe build
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$IdfArgs)

# Launched from Git Bash these leak in and make ESP-IDF refuse to run.
Remove-Item Env:MSYSTEM -ErrorAction SilentlyContinue
Remove-Item Env:MSYSTEM_PREFIX -ErrorAction SilentlyContinue

$env:IDF_PATH = 'C:\Espressif\frameworks\esp-idf-v5.5.4'
$env:IDF_TOOLS_PATH = 'C:\Espressif'
$py = 'C:\Espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe'

$exports = & $py "$env:IDF_PATH\tools\idf_tools.py" export --format key-value
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
foreach ($line in $exports) {
    $key, $value = $line -split '=', 2
    if (-not $key) { continue }
    $value = $value -replace '%PATH%', $env:PATH -replace '\$PATH', $env:PATH
    Set-Item -Path "Env:$key" -Value $value
}

& $py "$env:IDF_PATH\tools\idf.py" @IdfArgs
exit $LASTEXITCODE
