param([string]$StatePath=(Join-Path $PSScriptRoot 'install-state.json'),[string]$ResultPath)
. (Join-Path $PSScriptRoot 'Common.ps1')
try {
 $state=Read-JsonFile $StatePath
 if($state.product -ne $ProductId){throw 'Unknown installation marker.'}
 Initialize-RegistryStore ([string]$state.registrySandbox)
 if(!$script:Sandbox){
  $principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
  if(!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
   $args=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-StatePath',('"'+$StatePath+'"'))
   if($ResultPath){$args+=@('-ResultPath',('"'+$ResultPath+'"'))}
   $child=Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -WindowStyle Hidden -ArgumentList $args -PassThru -Wait
   exit $child.ExitCode
  }
 }
 $appRoot=Assert-TargetPath $state.appRoot 'PriParaImageCamera'
 $driverRoot=Assert-TargetPath $state.driverRoot 'PriParaImageCameraDriver'
 if([IO.Path]::GetFullPath($StatePath) -ne (Join-Path $driverRoot 'install-state.json')){throw 'Invalid uninstall state location.'}
 Assert-ProgramsClosed
 Assert-Cameras $driverRoot
 Restore-Registration $state.registryBefore
 Write-JsonFile (Join-Path $appRoot 'retained-data.json') @{product=$ProductId;imagesPreserved=$true}
 Write-JsonFile (Join-Path $driverRoot 'uninstalled.json') @{product=$ProductId;uninstalled=$true}
 foreach($shortcut in $state.shortcuts){
  if([IO.Path]::GetFileName($shortcut) -ne '프리파라 이미지 카메라.lnk'){throw 'Unexpected shortcut path.'}
  if(Test-Path -LiteralPath $shortcut){Remove-Item -LiteralPath $shortcut -Force}
 }
 foreach($relative in $state.appFiles){$path=Get-InstalledFile $appRoot $relative;if(Test-Path -LiteralPath $path -PathType Leaf){Remove-Item -LiteralPath $path -Force}}
 foreach($relative in $state.driverFiles){$path=Get-InstalledFile $driverRoot $relative;if(Test-Path -LiteralPath $path -PathType Leaf){Remove-Item -LiteralPath $path -Force}}
 Remove-Item -LiteralPath (Join-Path $appRoot 'installation.json') -Force
 Remove-Item -LiteralPath $StatePath -Force
 # User images, slots and recent-image libraries remain in the app directory.
 if($ResultPath){Write-JsonFile $ResultPath @{success=$true;imagesPreserved=$true;registrationRestored=$true;appRoot=$appRoot}}
 if(!$script:Sandbox){Add-Type -AssemblyName System.Windows.Forms;[Windows.Forms.MessageBox]::Show('카메라 등록과 프로그램을 제거했습니다. 보관 이미지는 설치 폴더에 남겨두었습니다.','프리파라 이미지 카메라')|Out-Null}
}catch{
 if($ResultPath){Write-JsonFile $ResultPath @{success=$false;error=$_.Exception.ToString()}}
 if(!$script:Sandbox){Add-Type -AssemblyName System.Windows.Forms;[Windows.Forms.MessageBox]::Show($_.Exception.Message,'제거 실패')|Out-Null}
 exit 1
}
