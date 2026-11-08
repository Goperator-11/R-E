import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding="utf-8")
import importlib.util, unittest
sys.path.insert(0, r"C:\dev\pq_afec_gen33")
sys.path.insert(1, r"C:\dev\pq_afec_gen33\tests")
import test_v33_repro_tools as T
spec = importlib.util.spec_from_file_location("old_scrub", sys.argv[1])
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
T.scrub_for_publish = old
r = unittest.TestResult()
T.ReproductionToolsTests("test_history_check_finds_removed_private_key_and_oversize_blob").run(r)
print("old HEAD scrub:", "failures", [f[1].strip().splitlines()[-1] for f in r.failures], "errors", [e[1].strip().splitlines()[-1] for e in r.errors], "skipped", r.skipped)
