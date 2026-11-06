param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$JavaHome = $env:JAVA_HOME
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not $JavaHome) { throw 'JavaHome 또는 JAVA_HOME에 JDK 25 경로를 지정하세요.' }
$cache = Join-Path $env:USERPROFILE '.gradle/caches/modules-2/files-2.1'
$jars = foreach ($group in @('org.apache.pdfbox', 'commons-logging', 'tools.jackson.core', 'com.fasterxml.jackson.core')) {
    $groupPath = Join-Path $cache $group
    if (Test-Path -LiteralPath $groupPath) {
        foreach ($artifact in Get-ChildItem -LiteralPath $groupPath -Directory) {
            $version = Get-ChildItem -LiteralPath $artifact.FullName -Directory | Sort-Object Name -Descending | Select-Object -First 1
            Get-ChildItem -LiteralPath $version.FullName -Filter '*.jar' -Recurse | Where-Object { $_.Name -notmatch '-(sources|javadoc)\.jar$' } | Select-Object -ExpandProperty FullName
        }
    }
}
if (-not $jars) { throw 'backend Gradle 의존성이 필요합니다. backend에서 .\gradlew.bat classes를 먼저 실행하세요.' }
$output = [IO.Path]::GetFullPath($OutputPath)
$classes = Join-Path $output '.classes'
New-Item -ItemType Directory -Path $classes -Force | Out-Null
$classpath = $jars -join [IO.Path]::PathSeparator
& (Join-Path $JavaHome 'bin/javac.exe') -encoding UTF-8 -cp $classpath -d $classes `
    (Join-Path $repo 'backend/src/main/java/com/hiremate/file/PdfText.java') (Join-Path $PSScriptRoot 'ParsePdfs.java')
if ($LASTEXITCODE -ne 0) { throw 'PDF 파서 컴파일 실패' }
& (Join-Path $JavaHome 'bin/java.exe') '-Dfile.encoding=UTF-8' -cp "$classes$([IO.Path]::PathSeparator)$classpath" `
    ParsePdfs ([IO.Path]::GetFullPath($ZipPath)) $output
if ($LASTEXITCODE -ne 0) { throw 'PDF 추출 실패' }
