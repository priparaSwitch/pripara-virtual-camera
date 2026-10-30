param([string]$GameRoot,[switch]$NoUi)
$ErrorActionPreference='Stop'
try {
 $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
 if(!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -and !$NoUi){
  $args=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'))
  if($GameRoot){$args+=@('-GameRoot',('"'+$GameRoot+'"'))}
  $child=Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -WindowStyle Hidden -ArgumentList $args -PassThru -Wait;exit $child.ExitCode
 }
 if(!$GameRoot){
  Add-Type -AssemblyName System.Windows.Forms
  $dialog=[Windows.Forms.FolderBrowserDialog]::new();$dialog.Description='Prineo.exe와 system_options.txt가 있는 game 폴더를 선택하세요.'
  if(Test-Path -LiteralPath 'C:\prineohk\game'){$dialog.SelectedPath='C:\prineohk\game'}
  if($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK){exit 0};$GameRoot=$dialog.SelectedPath
 }
 $GameRoot=[IO.Path]::GetFullPath($GameRoot).TrimEnd('\')
 $options=Join-Path $GameRoot 'system_options.txt';$ini=Join-Path $GameRoot 'camera\QRReader.ini'
 foreach($path in @((Join-Path $GameRoot 'Prineo.exe'),$options,$ini)){if(!(Test-Path -LiteralPath $path -PathType Leaf)){throw ('게임 폴더에서 파일을 찾을 수 없습니다: '+$path)}}
 foreach($p in @(Get-Process -Name Prineo,QRReader0,QRReader1 -ErrorAction SilentlyContinue)){if($p.Path -and $p.Path.StartsWith($GameRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw '해당 폴더의 게임과 QR 리더를 종료한 뒤 적용하세요.'}}
 $encoding=[Text.Encoding]::GetEncoding(28591)
 $beforeOptions=[IO.File]::ReadAllBytes($options);$beforeIni=[IO.File]::ReadAllBytes($ini)
 $a=$encoding.GetString($beforeOptions);$b=$encoding.GetString($beforeIni)
 foreach($i in @(1,2)){
  foreach($kind in @('vid','pid')){
   $name='camera_'+$kind+$i;$pattern='(?m)^'+$name+',[^\r\n]*'
   if([regex]::Matches($a,$pattern).Count -ne 1){throw ('카메라 설정 행이 없거나 중복됩니다: '+$name)}
   $value=if($kind -eq 'vid'){'0xCAFE'}else{'0x0002'};$a=[regex]::Replace($a,$pattern,($name+','+$value))
  }
 }
 $sections=[regex]::Split($b,'(?m)(?=^\[Camera[01]\])');$found=0
 for($n=0;$n -lt $sections.Length;$n++){
  if($sections[$n] -match '^\[Camera[01]\]'){
   $found++
   foreach($i in @(0,1,2,3)){
    foreach($kind in @('VID','PID')){
     $pattern='(?m)^'+$kind+$i+'=[^\r\n]*'
     if([regex]::Matches($sections[$n],$pattern).Count -ne 1){throw 'QRReader.ini의 카메라 후보가 없거나 중복됩니다.'}
     $value=if($kind -eq 'VID'){'CAFE'}else{'0002'};$sections[$n]=[regex]::Replace($sections[$n],$pattern,($kind+$i+'='+$value))
    }
   }
  }
 }
 if($found -ne 2){throw 'QRReader.ini의 Camera0/Camera1 두 섹션을 확인하세요.'}
 $b=$sections -join ''
 $backup=Join-Path $GameRoot ('camera_settings_before_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
 New-Item -ItemType Directory -Path $backup | Out-Null
 [IO.File]::WriteAllBytes((Join-Path $backup 'system_options.txt'),$beforeOptions);[IO.File]::WriteAllBytes((Join-Path $backup 'QRReader.ini'),$beforeIni)
 try{[IO.File]::WriteAllBytes($options,$encoding.GetBytes($a));[IO.File]::WriteAllBytes($ini,$encoding.GetBytes($b))}
 catch{[IO.File]::WriteAllBytes($options,$beforeOptions);[IO.File]::WriteAllBytes($ini,$beforeIni);throw}
 if(!$NoUi){Add-Type -AssemblyName System.Windows.Forms;[Windows.Forms.MessageBox]::Show('게임과 QRReader0/1을 하부 QR 카메라 CAFE:0002로 설정했습니다. QRReader1을 먼저 실행한 뒤 게임을 시작하세요.','게임 연결 설정')|Out-Null}
 Write-Output ('PASS: '+$GameRoot+' -> CAFE:0002')
}catch{
 if(!$NoUi){Add-Type -AssemblyName System.Windows.Forms;[Windows.Forms.MessageBox]::Show($_.Exception.Message,'게임 연결 설정 실패')|Out-Null}
 Write-Error $_;exit 1
}
