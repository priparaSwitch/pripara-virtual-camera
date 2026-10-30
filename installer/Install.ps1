param([Parameter(Mandatory=$true)][string]$PayloadRoot,[Parameter(Mandatory=$true)][string]$AppRoot,[Parameter(Mandatory=$true)][string]$DriverRoot,[string]$DesktopDir,[string]$StartMenuDir,[string]$CallerSid,[Parameter(Mandatory=$true)][string]$ResultPath,[string]$RegistrySandbox)
. (Join-Path $PSScriptRoot 'Common.ps1')
$report=@{success=$false;version='1.1.2';upper='CAFE:0001';lower='CAFE:0002';time=(Get-Date -Format o)}
$changedRegistration=$false;$before=$null
try {
 Initialize-RegistryStore $RegistrySandbox
 if(!$RegistrySandbox){
  if(![Environment]::Is64BitOperatingSystem){throw '64비트 Windows 10/11용 패키지입니다.'}
  $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
  if(!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw '드라이버 등록에는 관리자 권한이 필요합니다.'}
 }
 $AppRoot=Assert-TargetPath $AppRoot 'PriParaImageCamera'
 $DriverRoot=Assert-TargetPath $DriverRoot 'PriParaImageCameraDriver'
 Assert-ProgramsClosed
 $manifest=Read-JsonFile (Join-Path $PayloadRoot 'manifest.json')
 foreach($entry in $manifest.files){
  $source=Get-InstalledFile $PayloadRoot $entry.path
  if(!(Test-Path -LiteralPath $source) -or (Get-FileHash -LiteralPath $source).Hash -ne $entry.sha256){throw ('설치 파일 무결성 검사 실패: '+$entry.path)}
 }
 Assert-RegistrationAvailable $DriverRoot
 $statePath=Join-Path $DriverRoot 'install-state.json'
 $previous=$null
 if(Test-Path -LiteralPath $statePath){$previous=Read-JsonFile $statePath;if($previous.product -ne $ProductId -or $previous.appRoot -ne $AppRoot -or [string]$previous.registrySandbox -ne $RegistrySandbox){throw '다른 위치 또는 다른 사용자 설치가 있습니다. 먼저 기존 설치를 제거하세요.'}}
 if(Test-Path -LiteralPath $AppRoot){
  $marker=Join-Path $AppRoot 'installation.json';if(!(Test-Path -LiteralPath $marker)){$marker=Join-Path $AppRoot 'retained-data.json'}
  if(!(Test-Path -LiteralPath $marker) -or (Read-JsonFile $marker).product -ne $ProductId){throw '설치 대상에 기존 파일이 있습니다. 전용 설치 폴더를 사용하세요.'}
 }
 if((Test-Path -LiteralPath $DriverRoot) -and !$previous){
  $marker=Join-Path $DriverRoot 'uninstalled.json'
  if(!(Test-Path -LiteralPath $marker) -or (Read-JsonFile $marker).product -ne $ProductId){throw '드라이버 대상 폴더에 기존 파일이 있습니다.'}
 }
 $before=@(Get-RegistrationSnapshot)
 $original=if($previous){@($previous.registryBefore)}else{$before}
 New-Item -ItemType Directory -Path $AppRoot,$DriverRoot -Force | Out-Null
 # A failed first installation remains repairable without deleting user data.
 Write-JsonFile (Join-Path $AppRoot 'installation.json') @{product=$ProductId;version='1.1.2';driverRoot=$DriverRoot;pending=$true}
 $plannedApp=@($manifest.files | Where-Object {$_.path.StartsWith('App/')} | ForEach-Object {$_.path.Substring(4)})
 $plannedDriver=@($manifest.files | Where-Object {$_.path.StartsWith('Driver/')} | ForEach-Object {$_.path.Substring(7)})+@('Common.ps1','Uninstall.ps1','Uninstall.cmd')
 Write-JsonFile $statePath @{product=$ProductId;version='1.1.2';appRoot=$AppRoot;driverRoot=$DriverRoot;registrySandbox=$RegistrySandbox;registryBefore=$original;appFiles=$plannedApp;driverFiles=$plannedDriver;shortcuts=@();pending=$true}
 if($CallerSid -and !$RegistrySandbox){
  $acl=Get-Acl -LiteralPath $AppRoot
  $sid=[Security.Principal.SecurityIdentifier]::new($CallerSid)
  $rule=[Security.AccessControl.FileSystemAccessRule]::new($sid,[Security.AccessControl.FileSystemRights]::Modify,[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit',[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow)
  $acl.SetAccessRule($rule);Set-Acl -LiteralPath $AppRoot -AclObject $acl
 }
 $appFiles=@();$driverFiles=@()
 foreach($entry in $manifest.files){
  $parts=$entry.path -split '/',2
  if($parts[0] -eq 'App'){$destination=Get-InstalledFile $AppRoot $parts[1];$appFiles+=$parts[1]}
  elseif($parts[0] -eq 'Driver'){$destination=Get-InstalledFile $DriverRoot $parts[1];$driverFiles+=$parts[1]}
  else{continue}
  New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($destination)) -Force | Out-Null
  Copy-Item -LiteralPath (Get-InstalledFile $PayloadRoot $entry.path) -Destination $destination -Force
  if((Get-FileHash -LiteralPath $destination).Hash -ne $entry.sha256){throw 'Installed file hash mismatch.'}
 }
 foreach($name in @('Common.ps1','Uninstall.ps1')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $DriverRoot $name) -Force;$driverFiles+=$name}
 [IO.File]::WriteAllText((Join-Path $DriverRoot 'Uninstall.cmd'),'@echo off'+"`r`n"+'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall.ps1"'+"`r`n",[Text.Encoding]::ASCII)
 $driverFiles+='Uninstall.cmd'
 $changedRegistration=$true;Register-Cameras $DriverRoot;Assert-Cameras $DriverRoot
 $shortcuts=@()
 if(!$RegistrySandbox){
  $shell=New-Object -ComObject WScript.Shell
  foreach($directory in @($DesktopDir,$StartMenuDir)){
   if(!$directory){continue};New-Item -ItemType Directory -Path $directory -Force | Out-Null
   $shortcutPath=Join-Path $directory '프리파라 이미지 카메라.lnk';$shortcut=$shell.CreateShortcut($shortcutPath)
   $shortcut.TargetPath=Join-Path $AppRoot 'PriParaImageCamera.exe';$shortcut.WorkingDirectory=$AppRoot;$shortcut.IconLocation=$shortcut.TargetPath;$shortcut.Save();$shortcuts+=$shortcutPath
  }
  $base=Open-Store 64;$key=$base.CreateSubKey('SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PriParaImageCamera')
  try{
   $key.SetValue('DisplayName','프리파라 이미지 카메라');$key.SetValue('DisplayVersion','1.1.2');$key.SetValue('InstallLocation',$AppRoot)
   $key.SetValue('DisplayIcon',(Join-Path $AppRoot 'PriParaImageCamera.exe'))
   $command='powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $DriverRoot 'Uninstall.ps1')+'"'
   $key.SetValue('UninstallString',$command);$key.SetValue('NoModify',1,[Microsoft.Win32.RegistryValueKind]::DWord);$key.SetValue('NoRepair',1,[Microsoft.Win32.RegistryValueKind]::DWord)
  }finally{$key.Close();$base.Close()}
 }
 $state=@{product=$ProductId;version='1.1.2';appRoot=$AppRoot;driverRoot=$DriverRoot;registrySandbox=$RegistrySandbox;registryBefore=$original;appFiles=$appFiles;driverFiles=$driverFiles;shortcuts=$shortcuts;callerSid=$CallerSid;upper='CAFE:0001';lower='CAFE:0002'}
 Write-JsonFile $statePath $state
 Write-JsonFile (Join-Path $AppRoot 'installation.json') @{product=$ProductId;version='1.1.2';driverRoot=$DriverRoot;upper='CAFE:0001';lower='CAFE:0002'}
 $report.success=$true;$report.appRoot=$AppRoot;$report.driverRoot=$DriverRoot;$report.reinstall=($null -ne $previous)
}catch{
 $report.error=$_.Exception.ToString()
 if($changedRegistration -and $before){try{Restore-Registration $before;$report.registryRolledBack=$true}catch{$report.rollbackError=$_.Exception.Message}}
}finally{Write-JsonFile $ResultPath $report}
if(!$report.success){exit 1}
