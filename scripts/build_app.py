"""Freeze current application sources, without running camera/UI entrypoints."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def build():
    if sys.platform!='win32':raise RuntimeError('The application bundle is built on Windows')
    if not (ROOT/'app/native/PriParaFrameSender64.dll').is_file():raise RuntimeError('Build native DLLs first')
    out=ROOT/'build/app-dist';work=ROOT/'build/pyinstaller';out.mkdir(parents=True,exist_ok=True);work.mkdir(exist_ok=True)
    env=dict(os.environ,PYTHONHASHSEED='0',PYTHONDONTWRITEBYTECODE='1')
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(out),'--workpath',str(work),str(ROOT/'PriParaImageCamera.spec')]
    with (ROOT/'build/app-build.log').open('wb')as log:subprocess.run(args,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    folder=out/'PriParaImageCamera';exe=folder/'PriParaImageCamera.exe'
    if not exe.is_file()or not (folder/'_internal/native/PriParaFrameSender64.dll').is_file():raise RuntimeError('Incomplete app bundle')
    allowed_qt={'qt6core.dll','qt6gui.dll','qt6network.dll','qt6opengl.dll','qt6svg.dll','qt6widgets.dll'}
    forbidden=[p for p in folder.rglob('*')if 'pyvirtualcam'in str(p).lower()or'virtualkeyboard'in str(p).lower()
               or (p.name.lower().startswith('qt6')and p.suffix.lower()=='.dll'and p.name.lower()not in allowed_qt)]
    if forbidden:raise RuntimeError('Unused/GPL dependency unexpectedly bundled: '+str(forbidden[:3]))
    modules=sorted(p.name for p in (folder/'_internal/PySide6').glob('Qt6*.dll'))
    result=dict(passed=True,version='1.1.1',application_exe_bytes=exe.stat().st_size,
                application_exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),Qt_DLLs=modules,
                onedir_internal_required=True,pyvirtualcam_bundled=False,application_run=False)
    (ROOT/'build/app-build-report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result));return result
if __name__=='__main__':build()
