$ErrorActionPreference='Stop'
# A Python/PowerShell 7 parent may pass its module paths to Windows PowerShell
# 5.1. Use this engine's utility module for the SHA-256 integrity gate.
if($PSEdition -eq 'Desktop'){
 Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -Force -ErrorAction Stop
}
$ProductId='PriParaImageCamera-1'
$Category='{860BB310-5D01-11D0-BD3B-00A0C911CE86}'
$FilterData=[Convert]::FromBase64String('AgAAAAAAIAABAAAAAAAAADBwaTMIAAAAAAAAAAEAAAAAAAAAAAAAADB0eTMAAAAAOAAAAEgAAAB2aWRzAAAQAIAAAKoAOJtxAAAAAAAAAAAAAAAAAAAAAA==')
function Write-JsonFile($Path,$Data) {
 [IO.File]::WriteAllText($Path,($Data | ConvertTo-Json -Depth 35),[Text.UTF8Encoding]::new($false))
}
function Read-JsonFile($Path) {Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json}
function Initialize-RegistryStore([string]$Sandbox) {
 $script:Sandbox=$Sandbox
 if($Sandbox -and $Sandbox -notmatch '^Software\\PriParaImageCameraInstallerTests\\[A-Za-z0-9_-]+$') {throw 'Invalid isolated test registry root.'}
}
function Open-Store([int]$Bits) {
 $hive=if($script:Sandbox){[Microsoft.Win32.RegistryHive]::CurrentUser}else{[Microsoft.Win32.RegistryHive]::LocalMachine}
 $view=if($Bits -eq 32){[Microsoft.Win32.RegistryView]::Registry32}else{[Microsoft.Win32.RegistryView]::Registry64}
 return [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive,$view)
}
function Store-Path([string]$Relative) {if($script:Sandbox){return ($script:Sandbox+'\'+$Relative)};return $Relative}
function Filter-Specs([int]$Bits) {
 $last=if($Bits -eq 32){@('20','22','21')}else{@('10','12','11')}
 @(
  @{guid=('{5C2CD55C-92AD-4999-8666-912BD3E700'+$last[0]+'}');name='PriPara Upper Camera';dll=('UnityCaptureFilter'+$Bits+'.dll');device='\\?\usb#vid_cafe&pid_0001#pripara_0';camera=$true},
  @{guid=('{5C2CD55C-92AD-4999-8666-912BD3E700'+$last[1]+'}');name='PriPara QR Camera';dll=('PriParaQRFilter'+$Bits+'.dll');device='\\?\usb#vid_cafe&pid_0002#pripara_1';camera=$true},
  @{guid=('{5C2CD55C-92AD-4999-8666-912BD3E700'+$last[2]+'}');name='PriPara Camera Configuration';dll=('UnityCaptureFilter'+$Bits+'.dll');camera=$false}
 )
}
function Owned-RegistryPaths([int]$Bits) {
 foreach($s in (Filter-Specs $Bits)) {
  'SOFTWARE\Classes\CLSID\'+$s.guid
  if($s.camera){'SOFTWARE\Classes\CLSID\'+$Category+'\Instance\'+$s.guid}
 }
 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PriParaImageCamera'
}
function Snapshot-Node($Base,[string]$Relative) {
 $key=$Base.OpenSubKey((Store-Path $Relative))
 $node=@{path=$Relative;exists=($null -ne $key);values=@();children=@()}
 if(!$key){return $node}
 try {
  foreach($name in $key.GetValueNames()) {
   $kind=$key.GetValueKind($name).ToString();$value=$key.GetValue($name,$null,[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
   if($kind -eq 'Binary'){$value=[Convert]::ToBase64String($value)}
   $node.values+=@{name=$name;kind=$kind;value=$value}
  }
  foreach($child in $key.GetSubKeyNames()){$node.children+=Snapshot-Node $Base ($Relative+'\'+$child)}
 } finally {$key.Close()}
 return $node
}
function Restore-Node($Base,$Node) {
 $path=Store-Path $Node.path
 $Base.DeleteSubKeyTree($path,$false)
 if(!$Node.exists){return}
 $key=$Base.CreateSubKey($path)
 try {
  foreach($entry in $Node.values) {
   $value=$entry.value
   if($entry.kind -eq 'Binary'){$value=[Convert]::FromBase64String($value)}
   elseif($entry.kind -eq 'DWord'){$value=[int]$value}
   elseif($entry.kind -eq 'QWord'){$value=[long]$value}
   elseif($entry.kind -eq 'MultiString'){$value=[string[]]$value}
   $key.SetValue([string]$entry.name,$value,[Microsoft.Win32.RegistryValueKind]::$($entry.kind))
  }
 } finally {$key.Close()}
 foreach($child in $Node.children){Restore-Node $Base $child}
}
function Get-RegistrationSnapshot {
 $snap=@()
 foreach($bits in @(32,64)){
  $base=Open-Store $bits
  try{foreach($path in (Owned-RegistryPaths $bits)){$snap+=@{bits=$bits;node=(Snapshot-Node $base $path)}}}finally{$base.Close()}
 }
 return $snap
}
function Restore-Registration($Snapshot) {
 foreach($item in $Snapshot){$base=Open-Store $item.bits;try{Restore-Node $base $item.node}finally{$base.Close()}}
}
function Assert-RegistrationAvailable([string]$DriverRoot) {
 foreach($bits in @(32,64)){
  $base=Open-Store $bits
  try {
   foreach($s in (Filter-Specs $bits | Where-Object {$_.camera})) {
    $key=$base.OpenSubKey((Store-Path ('SOFTWARE\Classes\CLSID\'+$s.guid+'\InprocServer32')))
    if($key){
     try{$existing=[string]$key.GetValue('')}finally{$key.Close()}
     if($existing -and $existing -ne (Join-Path $DriverRoot $s.dll)){
      $categoryKey=$base.OpenSubKey((Store-Path ('SOFTWARE\Classes\CLSID\'+$Category+'\Instance\'+$s.guid)))
      $ours=$false
      if($categoryKey){try{$ours=($categoryKey.GetValue('FriendlyName') -eq $s.name -and $categoryKey.GetValue('DevicePath') -eq $s.device)}finally{$categoryKey.Close()}}
      if(!$ours){throw ('다른 UnityCapture 장치가 같은 등록값을 사용하고 있습니다. 기존 설치를 확인하세요: '+$existing)}
     }
    }
   }
  } finally {$base.Close()}
 }
}
function Register-Cameras([string]$DriverRoot) {
 foreach($bits in @(32,64)) {
  $base=Open-Store $bits
  try {
   foreach($s in (Filter-Specs $bits)) {
    $classPath='SOFTWARE\Classes\CLSID\'+$s.guid
    $key=$base.CreateSubKey((Store-Path $classPath));try{$key.SetValue('',$s.name)}finally{$key.Close()}
    $key=$base.CreateSubKey((Store-Path ($classPath+'\InprocServer32')))
    try{$key.SetValue('',(Join-Path $DriverRoot $s.dll));$key.SetValue('ThreadingModel','Both')}finally{$key.Close()}
    if($s.camera){
     $key=$base.CreateSubKey((Store-Path ('SOFTWARE\Classes\CLSID\'+$Category+'\Instance\'+$s.guid)))
     try{$key.SetValue('CLSID',$s.guid);$key.SetValue('FriendlyName',$s.name);$key.SetValue('DevicePath',$s.device);$key.SetValue('FilterData',$FilterData,[Microsoft.Win32.RegistryValueKind]::Binary)}finally{$key.Close()}
    }
   }
  } finally {$base.Close()}
 }
}
function Assert-Cameras([string]$DriverRoot) {
 foreach($bits in @(32,64)){
  $base=Open-Store $bits
  try{
   foreach($s in (Filter-Specs $bits)) {
    $key=$base.OpenSubKey((Store-Path ('SOFTWARE\Classes\CLSID\'+$s.guid+'\InprocServer32')))
    if(!$key){throw 'Camera class registration missing.'}
    try{if($key.GetValue('') -ne (Join-Path $DriverRoot $s.dll)){throw 'Camera driver path mismatch.'}}finally{$key.Close()}
    if($s.camera){
     $key=$base.OpenSubKey((Store-Path ('SOFTWARE\Classes\CLSID\'+$Category+'\Instance\'+$s.guid)))
     if(!$key){throw 'Camera enumeration entry missing.'}
     try{if($key.GetValue('DevicePath') -ne $s.device -or $key.GetValue('FriendlyName') -ne $s.name -or [Convert]::ToBase64String($key.GetValue('FilterData')) -ne [Convert]::ToBase64String($FilterData)){throw 'Camera identity mismatch.'}}finally{$key.Close()}
    }
   }
  }finally{$base.Close()}
 }
}
function Assert-TargetPath([string]$Path,[string]$Leaf) {
 $full=[IO.Path]::GetFullPath($Path).TrimEnd('\')
 if([IO.Path]::GetFileName($full) -ne $Leaf){throw ('Unexpected installation folder: '+$full)}
 $scan=$full
 while($scan){
  if((Test-Path -LiteralPath $scan) -and ((Get-Item -LiteralPath $scan -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Installation through a junction or symbolic link is not supported.'}
  $next=[IO.Path]::GetDirectoryName($scan);if($next -eq $scan){break};$scan=$next
 }
 return $full
}
function Get-InstalledFile([string]$Root,[string]$Relative) {
 $prefix=[IO.Path]::GetFullPath($Root).TrimEnd('\')+'\'
 $target=[IO.Path]::GetFullPath((Join-Path $Root $Relative))
 if(!$target.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Package path escapes installation folder.'}
 return $target
}
function Assert-ProgramsClosed {
 if(!$script:Sandbox -and (Get-Process -Name PriParaImageCamera,QRReader0,QRReader1,Prineo -ErrorAction SilentlyContinue)) {throw '이미지 카메라와 QR 리더, 게임을 종료한 뒤 다시 실행하세요.'}
}
