import hashlib, os, pathlib, shutil, subprocess, sys, tarfile

print("MINJAZ_SOURCE_LOADER_START", flush=True)
root = pathlib.Path(__file__).resolve().parent
artifact = root / "minjaz_rc5_runtime.tgz"
sha_file = root / "minjaz_rc5_runtime.sha256"

if not artifact.exists():
    raise RuntimeError("runtime artifact missing")
if not sha_file.exists():
    raise RuntimeError("runtime sha file missing")

expected_sha = sha_file.read_text(encoding="utf-8").strip().split()[0]
actual_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
if actual_sha != expected_sha:
    raise RuntimeError(f"runtime sha mismatch: {actual_sha}")

app = pathlib.Path("/app")
if app.exists():
    shutil.rmtree(app)
app.mkdir(parents=True, exist_ok=True)

with tarfile.open(artifact, mode="r:gz") as tf:
    tf.extractall(app)

server = app / "server.py"
index = app / "public" / "index.html"
migrate = app / "migrate.py"
storage = app / "storage.py"

assert server.exists(), "server.py missing"
assert migrate.exists(), "migrate.py missing"
assert storage.exists(), "storage.py missing"
assert index.exists() and index.stat().st_size > 200000, "frontend bundle incomplete"

subprocess.check_call([sys.executable, "-m", "py_compile", str(server), str(migrate), str(storage)])
os.chdir(app)
subprocess.check_call([sys.executable, "migrate.py"])

print(f"MINJAZ_SOURCE_RUNTIME_OK sha={actual_sha} index_bytes={index.stat().st_size}", flush=True)
print("MINJAZ_SOURCE_SERVER_EXEC", flush=True)
os.execv(sys.executable, [sys.executable, "-u", "server.py"])
