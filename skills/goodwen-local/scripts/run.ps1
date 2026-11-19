$ErrorActionPreference = "Stop"
if ($env:PROCESSOR_ARCHITECTURE -ne "AMD64" -and $env:PROCESSOR_ARCHITEW6432 -ne "AMD64") { throw "需要 Windows x64" }
$lock = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "runtime-lock.json") | ConvertFrom-Json
$asset = $lock.platforms.'windows-x64'.python
$cacheRoot = if ($env:GOODWEN_LOCAL_CACHE) { $env:GOODWEN_LOCAL_CACHE } else { Join-Path $env:LOCALAPPDATA "Goodwen\LocalCache" }
$cache = Join-Path $cacheRoot ("windows-x64\" + $asset.sha256)
[IO.Directory]::CreateDirectory($cache) | Out-Null
$python = Join-Path $cache "python\python.exe"
if (!(Test-Path $python)) {
    $stage = Join-Path $cache ([guid]::NewGuid().ToString())
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    try {
        $archive = Join-Path (Split-Path $PSScriptRoot) ("offline\" + $asset.name)
        if (!(Test-Path $archive)) {
            $archive = Join-Path $stage "runtime.tar.gz"
            curl.exe --fail --location --silent --show-error --retry 2 --output $archive $asset.url
            if ($LASTEXITCODE -ne 0) { throw "无法下载运行器" }
        }
        if ((Get-FileHash $archive -Algorithm SHA256).Hash -ne $asset.sha256) { throw "运行器摘要不符" }
        tar.exe -xzf $archive -C $stage
        if ($LASTEXITCODE -ne 0) { throw "无法解包运行器" }
        try { [IO.Directory]::Move((Join-Path $stage "python"), (Join-Path $cache "python")) }
        catch { if (!(Test-Path $python)) { throw } }
    } finally { Remove-Item -LiteralPath $stage -Recurse -Force }
}
& $python -I (Join-Path $PSScriptRoot "bootstrap.py") windows-x64 $cache @args
exit $LASTEXITCODE
