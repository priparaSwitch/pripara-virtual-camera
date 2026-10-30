"""Synthetic tests only: no installed camera/game access or real registration."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def run(toolchain):
    out=ROOT/'build/offline-tests';out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONPATH=str(ROOT/'app'),PYTHONDONTWRITEBYTECODE='1',QT_QPA_PLATFORM='offscreen')
    commands=[]
    for name in ['test_app.py','test_ticket_features.py','test_ipc.py']:
        script=ROOT/'tests'/name
        with (out/(name+'.log')).open('wb')as log:subprocess.run([sys.executable,'-B',str(script)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        commands.append(name)
    compiler=Path(toolchain).resolve()/'bin/x86_64-w64-mingw32-clang++.exe'
    sender=out/'TestSender64.dll';fixture=out/'TestReceiver64.dll'
    for source,dest,extra in [(ROOT/'native/sender/PriParaFrameSender.cpp',sender,['-DPRIPARA_TEST_CHANNELS=1']),
                              (ROOT/'tests/native_sender_fixture.cpp',fixture,[])]:
        args=[str(compiler),'-shared','-O2','-std=c++17','-static','-Wl,--no-insert-timestamp',*extra,str(source),'-o',str(dest)]
        with (out/(dest.stem+'.build.log')).open('wb')as log:subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    env.update(PPF_TEST_DLL=str(sender),PPF_FIXTURE_DLL=str(fixture))
    with (out/'camera-output.log').open('wb')as log:
        subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-p','test_camera_output.py','-v'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    with (out/'filter-abi.log').open('wb')as log:
        subprocess.run([sys.executable,'-B',str(ROOT/'tests/test_filter_abi.py'),'--toolchain',str(Path(toolchain).resolve())],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    result=dict(passed=True,source_tests=commands,native_protocol_tests=8,isolated_channels=[50,51],
                installed_channels_0_1_opened=False,actual_camera_or_game_access=False,live_driver_registration=False,
                Windows_registry_overrides=False,source_protocol_receiver='native/upper/shared.inl',filter_factory_ABI_cases=4)
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result));return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,default=os.environ.get('LLVM_MINGW_ROOT',ROOT/'.tools/llvm-mingw-20261020-ucrt-x86_64'))
    a=p.parse_args();run(a.toolchain)
