param(
 [Parameter(Mandatory=$true)][string]$PayloadRoot,
 [Parameter(Mandatory=$true)][string]$OutDir
)
# Exercise the installer's explicit HKCU test store, never the live HKLM store.
# No COM activation, device enumeration, process termination, UI, or elevation.
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$expectedVersion=(Get-Content -LiteralPath (Join-Path $repo 'VERSION') -Raw).Trim()
$PayloadRoot=[IO.Path]::GetFullPath($PayloadRoot).TrimEnd('\')
$OutDir=[IO.Path]::GetFullPath($OutDir).TrimEnd('\')
$allowed=@((Join-Path $repo 'build'),(Join-Path $repo '.local-tests'))
if(!($allowed | Where-Object {$OutDir.StartsWith($_+'\',[StringComparison]::OrdinalIgnoreCase)})){
 throw 'OutDir must be a child of this repository build or .local-tests folder.'
}
$scan=$OutDir
while($scan){
 if((Test-Path -LiteralPath $scan) -and ((Get-Item -LiteralPath $scan -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Test output through a reparse point is not allowed.'}
 $next=[IO.Path]::GetDirectoryName($scan);if($next -eq $scan){break};$scan=$next
}
$setup=Join-Path $PayloadRoot 'Setup'
foreach($name in @('Common.ps1','Install.ps1','Uninstall.ps1')){
 if(!(Test-Path -LiteralPath (Join-Path $setup $name) -PathType Leaf)){throw ('Missing payload setup script: '+$name)}
}
if(!(Test-Path -LiteralPath (Join-Path $PayloadRoot 'manifest.json') -PathType Leaf)){throw 'Missing payload manifest.'}
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$runId=[guid]::NewGuid().ToString('N')
$runRoot=Join-Path $OutDir ('run_'+$runId)
New-Item -ItemType Directory -Path $runRoot | Out-Null
$testRegistryRoot='Software\PriParaImageCameraInstallerTests\'+$runId
$appRoot=Join-Path $runRoot 'PriParaImageCamera'
$driverRoot=Join-Path $runRoot 'PriParaImageCameraDriver'
$ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
. (Join-Path $setup 'Common.ps1')
$report=[ordered]@{
 passed=$false;success=$false;test_mode='explicit RegistrySandbox HKCU32/HKCU64';
 live_registration_modified=$false;live_camera_opened=$false;UI_started=$false;
 real_game_files_used=$false;processes_terminated=$false;registration_override_used=$false;
 checks=@();registry_sandbox_removed=$false
}
function Check([bool]$Condition,[string]$Name){
 if(!$Condition){throw ('FAILED: '+$Name)}
 $script:report.checks+=@{name=$Name;passed=$true}
}
function Hash-Text([string]$Text){
 $sha=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function Node-Lines($Node){
 'PATH='+$Node.path+';EXISTS='+[string]$Node.exists
 foreach($entry in @($Node.values | Sort-Object name)){
  'VALUE='+$entry.name+';KIND='+$entry.kind+';DATA='+($entry.value | ConvertTo-Json -Compress -Depth 8)
 }
 foreach($child in @($Node.children | Sort-Object path)){Node-Lines $child}
}
function Registration-Fingerprint{
 $lines=@(foreach($item in @(Get-RegistrationSnapshot | Sort-Object bits,{ $_.node.path })){
  'BITS='+$item.bits;Node-Lines $item.node
 })
 return Hash-Text ($lines -join "`n")
}
function Invoke-TestScript([string]$Script,[string[]]$Arguments,[string]$LogName,[int]$ExpectedExit=0){
 $log=Join-Path $runRoot ($LogName+'.log')
 $previousPreference=$ErrorActionPreference
 try{
  # An intentional child failure may write stderr; its exit code is authoritative.
  $ErrorActionPreference='Continue'
  & $ps -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Script @Arguments *> $log
  $code=$LASTEXITCODE
 }finally{$ErrorActionPreference=$previousPreference}
 if($code -ne $ExpectedExit){throw ('Unexpected script exit '+$code+' for '+$LogName+'; see test log.')}
}
function Install-Test([string]$Name){
 $result=Join-Path $runRoot ($Name+'.json')
 Invoke-TestScript (Join-Path $setup 'Install.ps1') @('-PayloadRoot',$PayloadRoot,'-AppRoot',$appRoot,'-DriverRoot',$driverRoot,'-ResultPath',$result,'-RegistrySandbox',$testRegistryRoot) $Name
 $value=Read-JsonFile $result
 Check ([bool]$value.success) ($Name+'_reported_success')
 Initialize-RegistryStore $testRegistryRoot
 Assert-Cameras $driverRoot
 Check $true ($Name+'_both_registry_views_camera_identity')
 return $value
}
function Uninstall-Test([string]$Name){
 $result=Join-Path $runRoot ($Name+'.json')
 Invoke-TestScript (Join-Path $driverRoot 'Uninstall.ps1') @('-ResultPath',$result) $Name
 Check ([bool](Read-JsonFile $result).success) ($Name+'_reported_success')
 Initialize-RegistryStore $testRegistryRoot
 Check ((Registration-Fingerprint) -eq $script:initialSandbox) ($Name+'_registration_snapshot_restored')
}
$liveBefore=$null
try{
 # This is the only use of the live store: a read-only fingerprint of owned keys.
 Initialize-RegistryStore ''
 $liveBefore=Registration-Fingerprint
 $report.live_registration_before_sha256=$liveBefore
 Initialize-RegistryStore $testRegistryRoot
 Check (@(Get-RegistrationSnapshot | Where-Object {$_.node.exists}).Count -eq 0) 'unique_test_store_starts_empty'
 # Seed a non-camera class so removal must restore values, not just delete keys.
 foreach($bits in @(32,64)){
  $base=Open-Store $bits
  try{
   $spec=@(Filter-Specs $bits | Where-Object {!$_.camera})[0]
   $key=$base.CreateSubKey((Store-Path ('SOFTWARE\Classes\CLSID\'+$spec.guid)))
   try{$key.SetValue('','ISOLATED BEFORE');$key.SetValue('Sentinel',77,[Microsoft.Win32.RegistryValueKind]::DWord)}finally{$key.Close()}
  }finally{$base.Close()}
 }
 $script:initialSandbox=Registration-Fingerprint
 foreach($file in @(Get-ChildItem -LiteralPath $setup -Filter '*.ps1')){
  $tokens=$null;$errors=$null
  [Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors) | Out-Null
  Check ($errors.Count -eq 0) ('payload_powershell_parses_'+$file.Name)
 }
 $manifest=Read-JsonFile (Join-Path $PayloadRoot 'manifest.json')
 Check ($manifest.product -eq 'PriParaImageCamera-1' -and $manifest.version -eq $expectedVersion) 'payload_product_and_version'
 $fresh=Install-Test 'fresh_install'
 Check (!$fresh.reinstall) 'fresh_install_not_marked_reinstall'
 $state=Read-JsonFile (Join-Path $driverRoot 'install-state.json')
 Check ($state.registrySandbox -eq $testRegistryRoot -and $state.appRoot -eq $appRoot -and $state.driverRoot -eq $driverRoot) 'state_retains_only_explicit_test_roots'
 Check (@($state.shortcuts).Count -eq 0) 'sandbox_creates_no_shortcuts'
 # Synthetic private state must survive both repair and removal byte-for-byte.
 $userFiles=@('channels\lower\data\library.json','channels\upper\data\selected.dat','TicketData\MyTicket\private-sentinel.dat')
 $userHashes=@{}
 foreach($relative in $userFiles){
  $path=Join-Path $appRoot $relative
  New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($path)) -Force | Out-Null
  [IO.File]::WriteAllBytes($path,[Text.Encoding]::UTF8.GetBytes('synthetic-preserved-data:'+ $relative))
  $userHashes[$relative]=(Get-FileHash -LiteralPath $path).Hash
 }
 $reinstall=Install-Test 'reinstall'
 Check ([bool]$reinstall.reinstall) 'second_install_marked_reinstall'
 foreach($relative in $userFiles){Check ((Get-FileHash -LiteralPath (Join-Path $appRoot $relative)).Hash -eq $userHashes[$relative]) ('reinstall_preserves_'+$relative)}
 Uninstall-Test 'uninstall'
 Check (!(Test-Path -LiteralPath (Join-Path $appRoot 'PriParaImageCamera.exe'))) 'uninstall_removes_application_executable'
 foreach($relative in $userFiles){Check ((Get-FileHash -LiteralPath (Join-Path $appRoot $relative)).Hash -eq $userHashes[$relative]) ('uninstall_preserves_'+$relative)}
 Check ((Read-JsonFile (Join-Path $appRoot 'retained-data.json')).imagesPreserved) 'uninstall_writes_retained_data_marker'
 $again=Install-Test 'install_after_uninstall'
 foreach($relative in $userFiles){Check ((Get-FileHash -LiteralPath (Join-Path $appRoot $relative)).Hash -eq $userHashes[$relative]) ('install_after_uninstall_preserves_'+$relative)}
 # Integrity rejection is tested with a tiny synthetic payload, not modified input.
 $bad=Join-Path $runRoot 'bad-payload';New-Item -ItemType Directory -Path (Join-Path $bad 'App') -Force | Out-Null
 [IO.File]::WriteAllText((Join-Path $bad 'App\sentinel.txt'),'deliberately bad test hash')
 Write-JsonFile (Join-Path $bad 'manifest.json') @{product='PriParaImageCamera-1';version=$expectedVersion;files=@(@{path='App/sentinel.txt';sha256=('0'*64);size=26})}
 $badParent=Join-Path $runRoot 'rejected';$badApp=Join-Path $badParent 'PriParaImageCamera';$badDriver=Join-Path $badParent 'PriParaImageCameraDriver'
 $registeredBefore=Registration-Fingerprint
 $badResult=Join-Path $runRoot 'rejected.json'
 Invoke-TestScript (Join-Path $setup 'Install.ps1') @('-PayloadRoot',$bad,'-AppRoot',$badApp,'-DriverRoot',$badDriver,'-ResultPath',$badResult,'-RegistrySandbox',$testRegistryRoot) 'reject_bad_hash' 1
 Check (!(Read-JsonFile $badResult).success -and !(Test-Path -LiteralPath $badApp) -and !(Test-Path -LiteralPath $badDriver)) 'bad_hash_rejected_before_destination_creation'
 Check ((Registration-Fingerprint) -eq $registeredBefore) 'bad_hash_leaves_test_registration_unchanged'
 # Only a synthetic game tree is passed to the shipped settings helper.
 $game=Join-Path $runRoot 'synthetic game\game';New-Item -ItemType Directory -Path (Join-Path $game 'camera') -Force | Out-Null
 $exe=Join-Path $game 'Prineo.exe';$options=Join-Path $game 'system_options.txt';$ini=Join-Path $game 'camera\QRReader.ini'
 [IO.File]::WriteAllText($exe,'synthetic non-executable test fixture',[Text.Encoding]::ASCII)
 $beforeOptions="test_setting,KEEP`r`ncamera_vid1,0x1234`r`ncamera_pid1,0x5678`r`ncamera_vid2,0x1234`r`ncamera_pid2,0x5678`r`nwindow_info,1,720,1280`r`n"
 $beforeIni="; KEEP NON CAMERA CONTENT`r`n"
 foreach($cam in @(0,1)){
  $beforeIni+='[Camera'+$cam+"]`r`n"
  foreach($index in @(0,1,2,3)){$beforeIni+='VID'+$index+"=1234`r`nPID"+$index+"=5678`r`n"}
  $beforeIni+="DecodeTimeout=3000`r`n"
 }
 [IO.File]::WriteAllText($options,$beforeOptions,[Text.Encoding]::ASCII);[IO.File]::WriteAllText($ini,$beforeIni,[Text.Encoding]::ASCII)
 $beforeOptionHash=(Get-FileHash -LiteralPath $options).Hash;$beforeIniHash=(Get-FileHash -LiteralPath $ini).Hash;$exeHash=(Get-FileHash -LiteralPath $exe).Hash
 Invoke-TestScript (Join-Path $appRoot 'game_camera_setup.ps1') @('-GameRoot',$game,'-NoUi') 'synthetic_game_settings'
 Check ([IO.File]::ReadAllText($options) -ceq $beforeOptions.Replace('0x1234','0xCAFE').Replace('0x5678','0x0002')) 'four_system_camera_fields_only_changed'
 Check ([IO.File]::ReadAllText($ini) -ceq $beforeIni.Replace('=1234','=CAFE').Replace('=5678','=0002')) 'sixteen_ini_camera_fields_only_changed'
 Check ((Get-FileHash -LiteralPath $exe).Hash -eq $exeHash) 'synthetic_executable_unchanged'
 $backup=@(Get-ChildItem -LiteralPath $game -Directory -Filter 'camera_settings_before_*')
 Check ($backup.Count -eq 1) 'settings_created_one_original_backup'
 Check ((Get-FileHash -LiteralPath (Join-Path $backup[0].FullName 'system_options.txt')).Hash -eq $beforeOptionHash -and (Get-FileHash -LiteralPath (Join-Path $backup[0].FullName 'QRReader.ini')).Hash -eq $beforeIniHash) 'settings_backup_is_byte_exact_original'
 Copy-Item -LiteralPath (Join-Path $backup[0].FullName 'system_options.txt') -Destination $options -Force
 Copy-Item -LiteralPath (Join-Path $backup[0].FullName 'QRReader.ini') -Destination $ini -Force
 Check ((Get-FileHash -LiteralPath $options).Hash -eq $beforeOptionHash -and (Get-FileHash -LiteralPath $ini).Hash -eq $beforeIniHash) 'synthetic_settings_restore_is_byte_exact'
 # Duplicate required keys must reject without writing either config or a backup.
 [IO.File]::AppendAllText($options,"camera_vid1,0x9999`r`n",[Text.Encoding]::ASCII)
 $duplicateHash=(Get-FileHash -LiteralPath $options).Hash
 Invoke-TestScript (Join-Path $appRoot 'game_camera_setup.ps1') @('-GameRoot',$game,'-NoUi') 'reject_duplicate_camera_key' 1
 Check ((Get-FileHash -LiteralPath $options).Hash -eq $duplicateHash -and (Get-FileHash -LiteralPath $ini).Hash -eq $beforeIniHash -and @(Get-ChildItem -LiteralPath $game -Directory -Filter 'camera_settings_before_*').Count -eq 1) 'invalid_settings_rejected_without_partial_write'
 Uninstall-Test 'final_uninstall'
 $report.passed=$true;$report.success=$true
}catch{
 $report.error=$_.Exception.Message
}finally{
 # Guarded deletion is limited to the single random HKCU test subtree.
 try{
  if($testRegistryRoot -notmatch '^Software\\PriParaImageCameraInstallerTests\\[a-f0-9]{32}$'){throw 'Unsafe test-store cleanup path.'}
  foreach($view in @([Microsoft.Win32.RegistryView]::Registry32,[Microsoft.Win32.RegistryView]::Registry64)){
   $base=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,$view)
   try{$base.DeleteSubKeyTree($testRegistryRoot,$false)}finally{$base.Close()}
  }
  $report.registry_sandbox_removed=$true
 }catch{$report.cleanup_error=$_.Exception.Message;$report.passed=$false;$report.success=$false}
 try{
  Initialize-RegistryStore ''
  $after=Registration-Fingerprint;$report.live_registration_after_sha256=$after
  if(!$liveBefore -or $after -ne $liveBefore){throw 'Live registration read-only fingerprints differ.'}
  $report.live_registration_unchanged=$true
 }catch{$report.registration_check_error=$_.Exception.Message;$report.passed=$false;$report.success=$false}
 Write-JsonFile (Join-Path $OutDir 'installer-sandbox.json') $report
}
if(!$report.passed){Write-Error ('Installer sandbox validation failed: '+$report.error);exit 1}
Write-Output ('PASS: explicit installer sandbox ('+$report.checks.Count+' checks); no live registration/device/game writes.')
