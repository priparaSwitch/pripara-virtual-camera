"""Build every shipped camera DLL from this repository; never use installed DLLs."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def build(toolchain):
    toolchain=Path(toolchain).resolve();out=ROOT/'build/native';out.mkdir(parents=True,exist_ok=True)
    products=[]
    for kind,prefix in [('upper','UnityCaptureFilter'),('qr','PriParaQRFilter')]:
        stage=out/('source-'+kind);stage.mkdir(exist_ok=True)
        for file in (ROOT/'native'/kind).iterdir():
            if file.is_file():shutil.copy2(file,stage/file.name)
        # The already-used lower-filter base classes contain MinGW SAL/GUID/
        # helper-macro compatibility fixes. Use them for the unchanged upper
        # filter too, leaving its original upstream files in native/upper.
        if kind=='upper':
            for name in ('streams.h','streams.cpp'):shutil.copy2(ROOT/'native/qr'/name,stage/name)
            file=stage/'UnityCaptureFilter.cpp'
            text=file.read_text('utf8').replace('_uuidof(IAMStreamConfig)','IID_IAMStreamConfig').replace('_uuidof(IKsPropertySet)','IID_IKsPropertySet').replace('__out LPPROPPAGEINFO','LPPROPPAGEINFO')
            file.write_text(text,encoding='utf8')
        for bits,arch in [(32,'i686'),(64,'x86_64')]:
            compiler=toolchain/'bin'/f'{arch}-w64-mingw32-clang++.exe'
            if not compiler.is_file():raise FileNotFoundError(compiler)
            dest=out/f'{prefix}{bits}.dll'
            args=[str(compiler),'-std=c++17','-shared','-static','-O2','-DNDEBUG','-DWIN32','-D_WINDOWS','-D_USRDLL','-DUNICODE','-D_UNICODE',
                  '-fms-extensions','-Wno-microsoft-extra-qualification','-Wno-write-strings','-Wno-microsoft-exception-spec','-Wno-deprecated-declarations',
                  '-Wl,--no-insert-timestamp','-Wl,--kill-at','-s','UnityCaptureFilter.cpp','streams.cpp','UnityCaptureFilter.def','-o',str(dest),
                  '-lstrmiids','-lole32','-loleaut32','-luuid','-lwinmm','-lgdi32','-luser32','-ladvapi32','-lcomctl32','-lshlwapi']
            log=out/f'{prefix}{bits}.build.log'
            with log.open('wb')as stream:subprocess.run(args,cwd=stage,stdout=stream,stderr=subprocess.STDOUT,check=True)
            products.append(dict(path=dest.relative_to(ROOT).as_posix(),bytes=dest.stat().st_size,sha256=sha(dest)))
            print('Built',dest.name,dest.stat().st_size,flush=True)
    sender=ROOT/'native/sender/PriParaFrameSender.cpp'
    if not sender.is_file():raise FileNotFoundError('Native sender source has not been added yet')
    compiler=toolchain/'bin/x86_64-w64-mingw32-clang++.exe'
    dest=out/'PriParaFrameSender64.dll'
    args=[str(compiler),'-std=c++17','-shared','-static','-O2','-DNDEBUG','-Wl,--no-insert-timestamp','-s',str(sender),'-o',str(dest),'-ladvapi32']
    with (out/'sender.build.log').open('wb')as stream:subprocess.run(args,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)
    app=ROOT/'app/native';app.mkdir(exist_ok=True);shutil.copy2(dest,app/dest.name)
    products.append(dict(path=dest.relative_to(ROOT).as_posix(),bytes=dest.stat().st_size,sha256=sha(dest)))
    version=subprocess.run([str(compiler),'--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
    result=dict(passed=True,compiler_version=version,toolchain=json.loads((ROOT/'scripts/toolchain.json').read_text('utf8')),products=products,
                source_built=True,installed_DLLs_used=False,registration_performed=False)
    (out/'build-report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,default=os.environ.get('LLVM_MINGW_ROOT',ROOT/'.tools/llvm-mingw-20261020-ucrt-x86_64'))
    a=p.parse_args();build(a.toolchain)
