"""Explicit frozen-bundle check: no QApplication, IPC, camera or UAC calls."""
import hashlib,json,sys
from pathlib import Path
def run(report_path):
    import numpy as np
    from PIL import Image
    import PySide6
    import camera_output
    from ticket_capture import split_ticket
    native=camera_output._Native()
    assert native.dll.PPF_Version()==0x10000
    sample=np.zeros((756,1548,3),np.uint8);sample[0,0]=(12,34,56)
    full,tomo,my=split_ticket(Image.fromarray(sample))
    assert full.size==(756,1548)and tomo.size==(756,508)and my.size==(756,1040)
    internal=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    result=dict(passed=True,version='1.1.1',frozen=bool(getattr(sys,'frozen',False)),
                numpy=np.__version__,PySide6=PySide6.__version__,
                sender_version=hex(native.dll.PPF_Version()),sender_sha256=hashlib.sha256(camera_output._dll_path().read_bytes()).hexdigest(),
                internal_folder_present=internal.is_dir(),ticket_split_sizes=[list(x.size)for x in (full,tomo,my)],
                camera_opened=False,driver_registration=False,IPC_or_mutex_created=False,
                QApplication_created=False,producer_started=False,game_files_read_or_written=False)
    report_path=Path(report_path);report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    return result
