"""Direct metadata-only checks of the source-built DirectShow filter DLLs.

No COM registration lookup/changes, system device enumeration or stream is
used. Constructors were inspected: SharedImageMemory construction stores the
channel number; Open()/Receive() is reached only from the uncalled FillBuffer.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pe_bits(path):
    raw = path.read_bytes()
    at = struct.unpack_from("<I", raw, 0x3C)[0]
    if raw[at:at+4] != b"PE\0\0":
        raise ValueError("Not a PE file: " + str(path))
    return {0x14C: 32, 0x8664: 64}[struct.unpack_from("<H", raw, at+4)[0]]


def run(toolchain, filter_dir=None, report_dir=None):
    toolchain = Path(toolchain).resolve()
    filter_dir = Path(filter_dir or ROOT / "build/native").resolve()
    out = Path(report_dir or ROOT / ".local-tests/filter_abi").resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / "tests/filter_abi_probe.cpp"
    builds = []
    results = []
    for bits, arch in [(32, "i686"), (64, "x86_64")]:
        compiler = toolchain / "bin" / (arch + "-w64-mingw32-clang++.exe")
        executable = out / ("FilterAbiProbe" + str(bits) + ".exe")
        command = [str(compiler), "-O2", "-std=c++17", "-static", "-municode",
                   "-Wl,--no-insert-timestamp", "-s", str(source), "-o", str(executable),
                   "-lole32", "-loleaut32", "-luuid", "-lstrmiids"]
        build = subprocess.run(command, cwd=ROOT, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=60)
        (out / ("build" + str(bits) + ".log")).write_text(build.stdout + build.stderr,
                                                          encoding="utf-8")
        build.check_returncode()
        if pe_bits(executable) != bits:
            raise AssertionError("Probe architecture mismatch")
        builds.append({"bits": bits, "arguments": command[1:], "sha256": sha(executable)})
        for kind, prefix in [("upper", "UnityCaptureFilter"), ("qr", "PriParaQRFilter")]:
            dll = filter_dir / (prefix + str(bits) + ".dll")
            if pe_bits(dll) != bits:
                raise AssertionError("Filter architecture mismatch")
            completed = subprocess.run([str(executable), str(dll), kind], cwd=ROOT,
                        capture_output=True, text=True, encoding="utf-8", timeout=15)
            stem = prefix + str(bits)
            (out / (stem + ".log")).write_text(completed.stdout + completed.stderr,
                                                encoding="utf-8")
            completed.check_returncode()
            value = json.loads(completed.stdout)
            assert value["passed"] and value["bits"] == bits and value["kind"] == kind
            assert value["initialStopped"] and not value["frameReceiverCalled"]
            value.update(path=str(dll), sha256=sha(dll), bytes=dll.stat().st_size)
            results.append(value)
    report = {"passed": True, "cases": len(results), "filters": results,
              "probeBuilds": builds, "probeSourceSha256": sha(source),
              "testScriptSha256": sha(Path(__file__)),
              "scope": "Direct source-built DLL COM factory, pin and media/control metadata only",
              "registrationPerformed": False, "registryAccessRequested": False,
              "systemDevicesEnumerated": False, "graphOrPinConnectionCreated": False,
              "RunPauseFillBufferReceiveCalled": False,
              "installedCameraChannelsOpened": False,
              "gameOrQRReaderAccessed": False,
              "limitations": ["No streaming or real camera/game integration was tested.",
                              "The DLL constructor safety is established from the reviewed release source."]}
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "cases": len(results),
                      "report": str(out / "validation.json")}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--toolchain", type=Path,
                        default=os.environ.get("LLVM_MINGW_ROOT", ROOT / ".tools/llvm-mingw-20261020-ucrt-x86_64"))
    parser.add_argument("--filter-dir", type=Path, default=ROOT / "build/native")
    parser.add_argument("--report-dir", type=Path, default=ROOT / ".local-tests/filter_abi")
    args = parser.parse_args()
    run(args.toolchain, args.filter_dir, args.report_dir)
