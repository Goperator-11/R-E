import sys
sys.dont_write_bytecode = True
import hashlib
import importlib
import importlib.abc
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_NAMES = frozenset(("afec", "padfec", "padfec3"))
APPROVED_EXTRA = {"first_flight_evidence": "arrivals", "server_response": "server_response"}


def finite(name, value, minimum=0.0, nullable=False):
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return value


def first_flight_evidence(value):
    if not isinstance(value, dict) or set(value) != {"src", "sent", "lost", "bitmap", "trunc"}:
        raise ValueError("first_flight_evidence needs src,sent,lost,bitmap,trunc")
    if value["src"] not in ("c1", "ack", "none") or not isinstance(value["trunc"], bool):
        raise ValueError("invalid first-flight evidence source or truncation marker")
    sent, lost, bitmap = value["sent"], value["lost"], value["bitmap"]
    if any(isinstance(count, bool) or not isinstance(count, int) for count in (sent, lost)) or not 0 <= lost <= sent:
        raise ValueError("first-flight counts require 0 <= lost <= sent")
    if bitmap is not None:
        if not isinstance(bitmap, list) or any(type(bit) is not int or bit not in (0, 1) for bit in bitmap):
            raise ValueError("first-flight bitmap must contain integer arrival bits")
        if len(bitmap) > sent or (not value["trunc"] and (len(bitmap) != sent or bitmap.count(0) != lost)):
            raise ValueError("first-flight bitmap and counts disagree")
    return dict(value)


class GuardedPath(list):
    def __init__(self, values, source_root):
        self.source_root = source_root
        self.blocked = []
        super().__init__(item for item in values if self.accept(item, "initial"))

    def accept(self, value, operation):
        if isinstance(value, str) and Path(value or os.getcwd()).resolve().is_relative_to(self.source_root):
            self.blocked.append({"operation": operation, "path": value})
            return False
        return True

    def insert(self, index, value):
        if self.accept(value, "insert"):
            super().insert(index, value)

    def append(self, value):
        if self.accept(value, "append"):
            super().append(value)

    def extend(self, values):
        super().extend(value for value in values if self.accept(value, "extend"))

    def __iadd__(self, values):
        self.extend(values)
        return self

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            super().__setitem__(index, [item for item in value if self.accept(item, "slice")])
        elif self.accept(value, "setitem"):
            super().__setitem__(index, value)


class SourceOnlyLoader(importlib.abc.Loader):
    def __init__(self, finder, path):
        self.finder = finder
        self.path = path

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        content = self.path.read_bytes()
        self.finder.loaded[module.__name__] = {"path": str(self.path), "sha256": hashlib.sha256(content).hexdigest()}
        exec(compile(content, str(self.path), "exec"), module.__dict__)


class PolicyFinder(importlib.abc.MetaPathFinder):
    def __init__(self, source_root):
        self.source_root = source_root
        self.loaded = {}

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] not in PACKAGE_NAMES:
            return None
        parts = fullname.split(".")
        base = self.source_root.joinpath(*parts)
        package = base / "__init__.py"
        source = package if package.is_file() else base.with_suffix(".py")
        source = source.resolve()
        if not source.is_relative_to(self.source_root) or not source.is_file():
            raise ModuleNotFoundError(f"selected policy source does not contain {fullname}")
        loader = SourceOnlyLoader(self, source)
        return importlib.util.spec_from_file_location(fullname, source, loader=loader, submodule_search_locations=[str(source.parent)] if source.name == "__init__.py" else None)


def read_only_audit(event, args):
    if event == "open":
        mode, flags = args[1], args[2]
        writable_mode = isinstance(mode, str) and any(letter in mode for letter in "wax+")
        writable_flags = isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        if writable_mode or writable_flags:
            raise PermissionError("policy worker is read-only")
    if event in ("os.remove", "os.rmdir", "os.rename", "os.mkdir", "os.link", "os.symlink", "os.chmod", "os.truncate", "os.utime", "os.chdir", "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"):
        raise PermissionError(f"policy worker forbids {event}")


class PolicyWorker:
    def __init__(self):
        self.ready = False
        self.states = {}
        self.history = {}
        self.pending = {}

    def initialize(self, request):
        if self.ready:
            raise RuntimeError("one source and variant per worker process")
        if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
            raise RuntimeError("policy worker requires python -I -B")
        if not Path.cwd().resolve().is_relative_to(ROOT):
            raise RuntimeError("worker cwd must stay inside its writable repository")
        source_root = Path(request["source_root"]).resolve(strict=True)
        for name in PACKAGE_NAMES:
            if not (source_root / name / "__init__.py").is_file():
                raise ValueError(f"source_root has no {name} package")
        if any(name.split(".", 1)[0] in PACKAGE_NAMES for name in sys.modules):
            raise RuntimeError("policy packages were imported before isolation")
        self.W = request["W"]
        if isinstance(self.W, bool) or not isinstance(self.W, int) or self.W < 1200:
            raise ValueError("W must be an integer >=1200")
        self.u = finite("u_mbps", request["u_mbps"])
        self.c_pkt = finite("c_pkt", request["c_pkt"])
        self.variant = request.get("variant", "full")
        if self.variant not in ("full", "guard_off", "reeval_off"):
            raise ValueError("unsupported variant")
        self.source_root = source_root
        self.path_guard = GuardedPath(sys.path, source_root)
        sys.path = self.path_guard
        self.finder = PolicyFinder(source_root)
        sys.meta_path.insert(0, self.finder)
        sys.addaudithook(read_only_audit)
        self.learn = importlib.import_module("padfec3.learn3")
        self.decide_module = importlib.import_module("padfec3.decide3")
        self.runtime_overrides = {}
        if self.variant == "reeval_off":
            self.runtime_overrides["learn3.REEVAL_EVERY"] = {"original": self.learn.REEVAL_EVERY, "effective": 2 ** 63}
            self.learn.REEVAL_EVERY = 2 ** 63
        if self.variant == "guard_off":
            self.runtime_overrides["observe3.j_pred"] = {"effective": None}
        parameters = inspect.signature(self.learn.observe3).parameters
        self.extras = sorted(name for name, target in APPROVED_EXTRA.items() if target in parameters and parameters[target].kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY))
        self.ready = True
        return {"policy_version": self.learn.POLICY_VERSION, "state_version": self.learn.STATE_VERSION, "variant": self.variant, "runtime_overrides": self.runtime_overrides, "capabilities": {"observe_extra": self.extras}, "audit": self.audit()}

    def destination(self, request):
        name = request.get("destination", "default")
        if not isinstance(name, str) or not name:
            raise ValueError("destination must be a nonempty string")
        if name not in self.states:
            self.states[name] = self.learn.new_state()
            self.history[name] = {"supplied_policy_rtt_min_ms": None, "observed_hct_min_ms": None, "supplied_rtt_count": 0, "observations": 0}
        return name, self.states[name]

    def summary(self, name, state):
        posterior = self.learn.post_summary(self.learn.combined(state))
        return {**posterior, "S_hat": self.learn.s_hat(state), "S_scope": getattr(state, "S_scope", "legacy_unclassified"), "size_window_count": len(state.size_history["window"]), "size_catalog_count": len(state.size_history["catalog"]), "size_reset_count": state.size_history["resets"], "k_hat": self.learn.k_hat(state), "stats": dict(state.stats), "guard_alarms": dict(state.g_alarm), "n_dec": state.n_dec, "n_reeval": state.n_reeval, **self.history[name]}

    def audit(self):
        if sys.path is not self.path_guard:
            raise RuntimeError("policy changed sys.path object")
        if any(isinstance(value, str) and Path(value or os.getcwd()).resolve().is_relative_to(self.source_root) for value in sys.path):
            raise RuntimeError("policy root leaked into sys.path")
        actual = {}
        for name, module in sorted(sys.modules.items()):
            if name.split(".", 1)[0] in PACKAGE_NAMES:
                path = Path(module.__file__).resolve()
                if not path.is_relative_to(self.source_root):
                    raise RuntimeError(f"policy module {name} came from a different source")
                actual[name] = str(path)
        changed = []
        for name, entry in self.finder.loaded.items():
            if hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
                changed.append(name)
        if changed:
            raise RuntimeError("policy sources changed while running: " + ", ".join(changed))
        return {"source_root": str(self.source_root), "worker_cwd": str(Path.cwd().resolve()), "loaded_modules": dict(sorted(self.finder.loaded.items())), "actual_module_paths": actual, "source_sha256": {entry["path"]: entry["sha256"] for entry in self.finder.loaded.values()}, "path_insertions_blocked": list(self.path_guard.blocked), "sys_path": list(sys.path), "isolated": bool(sys.flags.isolated), "dont_write_bytecode": sys.dont_write_bytecode, "source_unchanged": True, "read_only_audit": True}

    def dispatch(self, request):
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        op = request.get("op")
        allowed = {
            "init": {"op", "id", "source_root", "W", "u_mbps", "c_pkt", "variant"},
            "reset": {"op", "id", "destination"},
            "decide": {"op", "id", "destination", "rtt_ms"},
            "observe": {"op", "id", "destination", "action", "hct_ms", "ok", "k_obs", "srv_bytes", "rtt_ms", "j_pred", "optional"},
            "snapshot": {"op", "id", "destination"},
        }
        if op not in allowed:
            raise ValueError("unsupported operation")
        unexpected = set(request) - allowed[op]
        if unexpected:
            raise ValueError("unsupported fields: " + ", ".join(sorted(unexpected)))
        if op == "init":
            return self.initialize(request)
        if not self.ready:
            raise RuntimeError("init is required")
        name, state = self.destination(request)
        if op == "reset":
            del self.states[name]
            del self.history[name]
            self.pending.pop(name, None)
            name, state = self.destination(request)
            return {"state": self.summary(name, state)}
        if op == "snapshot":
            return {"state": self.summary(name, state), "serialized": state.to_json(), "audit": self.audit()}
        rtt = finite("rtt_ms", request.get("rtt_ms"), nullable=True)
        if op == "decide":
            if name in self.pending:
                raise RuntimeError("previous decision needs exactly one observation")
            before = self.summary(name, state)
            decision = self.decide_module.decide3(state, self.W, self.u, rtt, self.c_pkt)
            self.pending[name] = tuple(decision["action"])
            return {"decision": decision, "before": before, "state": self.summary(name, state)}
        if name not in self.pending:
            raise RuntimeError("observe needs a preceding decision for this destination")
        if tuple(request.get("action", ())) != self.pending[name]:
            raise ValueError("observation action differs from the preceding decision")
        if not isinstance(request["ok"], bool):
            raise ValueError("ok must be a boolean")
        finite("hct_ms", request.get("hct_ms"), nullable=not request["ok"])
        finite("srv_bytes", request.get("srv_bytes"), nullable=True)
        j_pred = finite("j_pred", request.get("j_pred"), nullable=True)
        optional = request.get("optional", {})
        if not isinstance(optional, dict) or set(optional) - set(self.extras):
            raise ValueError("optional fields must be explicitly supported: " + ", ".join(self.extras))
        arguments = {}
        for key, value in optional.items():
            if key == "first_flight_evidence":
                arguments[APPROVED_EXTRA[key]] = first_flight_evidence(value)
            else:
                self.learn.server_size.normalize(value, request.get("srv_bytes"), request["ok"])
                arguments[APPROVED_EXTRA[key]] = value
        if self.variant == "guard_off":
            j_pred = None
        info = self.learn.observe3(state, tuple(request["action"]), request["hct_ms"], request["ok"], request.get("k_obs"), request.get("srv_bytes"), rtt, W=self.W, u_mbps=self.u, c_pkt=self.c_pkt, j_pred=j_pred, **arguments)
        del self.pending[name]
        history = self.history[name]
        history["observations"] += 1
        if rtt is not None and rtt > 0:
            current = history["supplied_policy_rtt_min_ms"]
            history["supplied_policy_rtt_min_ms"] = rtt if current is None else min(current, rtt)
            history["supplied_rtt_count"] += 1
        if request["ok"]:
            value = request["hct_ms"]
            current = history["observed_hct_min_ms"]
            history["observed_hct_min_ms"] = value if current is None else min(current, value)
        return {"observation": info, "state": self.summary(name, state), "j_pred_used": j_pred}


def reject_constant(value):
    raise ValueError("nonfinite JSON value: " + value)


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    worker = PolicyWorker()
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line, parse_constant=reject_constant)
            result = worker.dispatch(request)
            response = {"ok": True, "op": request["op"], "id": request.get("id"), "result": result}
            print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "op": request.get("op") if isinstance(request, dict) else None, "id": request.get("id") if isinstance(request, dict) else None, "error": {"type": type(exc).__name__, "message": str(exc)}}, ensure_ascii=False, allow_nan=False), flush=True)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
