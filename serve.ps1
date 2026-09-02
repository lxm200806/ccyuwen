# 本机静态服务，方便手机同一 Wi-Fi 打开
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$listen = [System.Net.HttpListener]::new()
$listen.Prefixes.Add('http://localhost:8765/')
$listen.Start()
Write-Host "打开 http://localhost:8765/"
$types = @{
    '.html' = 'text/html; charset=utf-8'
    '.css'  = 'text/css; charset=utf-8'
    '.js'   = 'text/javascript; charset=utf-8'
    '.csv'  = 'text/csv; charset=utf-8'
    '.json' = 'application/json; charset=utf-8'
}
while ($listen.IsListening) {
    $ctx = $listen.GetContext()
    $path = $ctx.Request.Url.LocalPath
    if ($path -eq '/') { $path = '/index.html' }
    $file = Join-Path $root ($path.TrimStart('/').Replace('/', '\'))
    if (Test-Path $file -PathType Leaf) {
        $ext = [IO.Path]::GetExtension($file)
        $ctx.Response.ContentType = $types[$ext]
        if (-not $ctx.Response.ContentType) { $ctx.Response.ContentType = 'application/octet-stream' }
        $bytes = [IO.File]::ReadAllBytes($file)
        $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } else {
        $ctx.Response.StatusCode = 404
    }
    $ctx.Response.Close()
}
