import subprocess
import sys
from pathlib import Path

from experiments.v33 import bench


class PolicyWorker(bench.PolicyWorker):
    def __init__(self, source_root, scenario, protocol, variant, log_path):
        self.error_stream = log_path.open("x", encoding="utf-8", newline="\n")
        self.process = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__).with_name("policy_worker_j6.py"))], cwd=bench.ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_stream, text=True, encoding="utf-8", bufsize=1)
        try:
            self.initial = self.request({"op": "init", "source_root": str(source_root), "W": scenario["context"]["w"], "u_mbps": scenario["context"]["uplink_mbps"], "c_pkt": protocol["c_pkt"], "variant": variant})
        except BaseException:
            self.process.stdin.close()
            self.process.wait(timeout=30)
            self.error_stream.close()
            raise
