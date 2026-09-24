# Argument-forwarding shim. It holds no behaviour of its own: any logic here
# would exist only on one platform, and the two shims would drift apart the
# first time one of them was edited.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$tools = Join-Path (Split-Path -Parent $here) 'tools'
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$tools$([IO.Path]::PathSeparator)$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $tools
}
$python = if ($env:ZEROOPS_PYTHON) { $env:ZEROOPS_PYTHON } else { 'python' }
& $python -m zeroops @args
exit $LASTEXITCODE
