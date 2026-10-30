using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Windows.Forms;
[assembly: AssemblyTitle("PriPara Image Camera Setup")]
[assembly: AssemblyVersion("1.1.2.0")]
[assembly: AssemblyFileVersion("1.1.2.0")]
class CameraSetup : Form {
 static bool previewMode;
 protected override bool ShowWithoutActivation {get{return previewMode||base.ShowWithoutActivation;}}
 protected override CreateParams CreateParams {get{var value=base.CreateParams;if(previewMode)value.ExStyle|=0x08000080;return value;}}
 Label status; Button install, cancel; CheckBox launch; bool busy;
 readonly string appRoot=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"PriParaImageCamera");
 readonly string driverRoot=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),"PriParaImageCameraDriver");
 CameraSetup() {
  Text="프리파라 이미지 카메라 설치";Font=new System.Drawing.Font("Malgun Gothic",9);Width=610;Height=350;FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;StartPosition=FormStartPosition.CenterScreen;
  FormClosing+=(s,e)=>{if(busy)e.Cancel=true;};
  var title=new Label{Left=25,Top=22,Width=550,Height=35,Text="프리파라 이미지 카메라 1.1.2",Font=new System.Drawing.Font("Malgun Gothic",16)};Controls.Add(title);
  status=new Label{Left=25,Top=75,Width=550,Height=145,Text="앱과 32·64비트 가상 카메라 드라이버를 설치합니다.\r\n상부 CAFE:0001 / 하부 QR CAFE:0002\r\n\r\n앱: "+appRoot+"\r\n드라이버 등록 시 관리자 권한을 요청합니다."};Controls.Add(status);
  launch=new CheckBox{Left=25,Top=225,Width=350,Text="설치 후 이미지 카메라 실행",Checked=true};Controls.Add(launch);
  install=new Button{Left=350,Top=265,Width=105,Height=34,Text="설치"};cancel=new Button{Left=465,Top=265,Width=105,Height=34,Text="닫기"};Controls.Add(install);Controls.Add(cancel);
  cancel.Click+=(s,e)=>Close();install.Click+=(s,e)=>BeginInstall();AcceptButton=install;
 }
 static string Quote(string value) {return "\""+value+"\"";}
 static void Extract(string destination) {
  string root=Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
  Directory.CreateDirectory(root);
  using(var resource=Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
  using(var zip=new ZipArchive(resource,ZipArchiveMode.Read)) {
   foreach(var entry in zip.Entries) {
    string target=Path.GetFullPath(Path.Combine(root,entry.FullName.Replace('/',Path.DirectorySeparatorChar)));
    if(!target.StartsWith(root,StringComparison.OrdinalIgnoreCase))throw new Exception("Invalid package path.");
    if(entry.FullName.EndsWith("/")){Directory.CreateDirectory(target);continue;}
    Directory.CreateDirectory(Path.GetDirectoryName(target));
    using(var input=entry.Open())using(var output=new FileStream(target,FileMode.CreateNew,FileAccess.Write))input.CopyTo(output);
   }
  }
 }
 void BeginInstall() {
  if(!Environment.Is64BitOperatingSystem){MessageBox.Show("64비트 Windows 10/11에서 실행하세요.");return;}
  busy=true;install.Enabled=false;cancel.Enabled=false;launch.Enabled=false;bool runApp=launch.Checked;
  string sid=WindowsIdentity.GetCurrent().User.Value;
  string desktop=Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
  string menu=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"프리파라 이미지 카메라");
  status.Text="설치 파일을 준비하고 있습니다…";
  new Thread(()=>{
   string tempRoot=Path.GetFullPath(Path.Combine(Path.GetTempPath(),"PriParaImageCameraSetup"));
   string stage=Path.Combine(tempRoot,Guid.NewGuid().ToString("N"));
   try {
    Extract(stage);
    string result=Path.Combine(stage,"result.json");
    string args="-NoProfile -ExecutionPolicy Bypass -File "+Quote(Path.Combine(stage,"Setup","Install.ps1"))+" -PayloadRoot "+Quote(stage)+" -AppRoot "+Quote(appRoot)+" -DriverRoot "+Quote(driverRoot)+" -DesktopDir "+Quote(desktop)+" -StartMenuDir "+Quote(menu)+" -CallerSid "+Quote(sid)+" -ResultPath "+Quote(result);
    Invoke((Action)(()=>status.Text="앱과 드라이버를 설치하고 있습니다…\r\n관리자 권한 요청을 승인해 주세요."));
    var info=new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"System32","WindowsPowerShell","v1.0","powershell.exe"),args){UseShellExecute=true,Verb="runas",WindowStyle=ProcessWindowStyle.Hidden};
    using(var process=Process.Start(info)){process.WaitForExit();if(process.ExitCode!=0)throw new Exception(File.Exists(result)?File.ReadAllText(result,Encoding.UTF8):"설치가 취소되었거나 완료되지 않았습니다.");}
    string stageFull=Path.GetFullPath(stage);
    if(stageFull.StartsWith(tempRoot+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)&&Path.GetFileName(stageFull).Length==32)Directory.Delete(stageFull,true);
    Invoke((Action)(()=>{busy=false;status.Text="설치 완료\r\n\r\n상부 VID CAFE / PID 0001\r\n하부 VID CAFE / PID 0002\r\n\r\n바탕화면의 ‘프리파라 이미지 카메라’를 실행하세요.";cancel.Enabled=true;install.Text="완료";install.Enabled=false;}));
    if(runApp)Process.Start(new ProcessStartInfo(Path.Combine(appRoot,"PriParaImageCamera.exe")){UseShellExecute=true,WorkingDirectory=appRoot});
   } catch(Exception error) {
    Invoke((Action)(()=>{busy=false;status.Text="설치가 완료되지 않았습니다.";MessageBox.Show(error.Message+"\r\n\r\n설치 기록: "+stage,"설치 확인",MessageBoxButtons.OK,MessageBoxIcon.Error);install.Enabled=true;cancel.Enabled=true;launch.Enabled=true;}));
   }
  }){IsBackground=false}.Start();
 }
 [STAThread] static int Main(string[] args) {
  try {
   if(args.Length==2&&args[0]=="/extract"){Extract(args[1]);return 0;}
   if(args.Length==2&&args[0]=="/preview"){
    previewMode=true;Application.EnableVisualStyles();using(var form=new CameraSetup())using(var bitmap=new System.Drawing.Bitmap(form.Width,form.Height)){form.StartPosition=FormStartPosition.Manual;form.Location=new System.Drawing.Point(-30000,-30000);form.ShowInTaskbar=false;form.Show();Application.DoEvents();form.DrawToBitmap(bitmap,new System.Drawing.Rectangle(0,0,bitmap.Width,bitmap.Height));bitmap.Save(args[1]);form.Hide();}return 0;
   }
   Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new CameraSetup());return 0;
  }catch(Exception error){MessageBox.Show(error.Message,"프리파라 이미지 카메라 설치");return 1;}
 }
}
