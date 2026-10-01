import os, base64, hashlib, io, pathlib, shutil, subprocess, sys, tarfile

EXPECTED_PARTS = 12
print("MINJAZ_SOURCE_LOADER_START", flush=True)

parts = [os.environ[f"R55{i:02d}"] for i in range(EXPECTED_PARTS)]
encoded = "".join(parts)
encoded += "=" * ((-len(encoded)) % 4)
blob = base64.b64decode(encoded)

actual_sha = hashlib.sha256(blob).hexdigest()
expected_sha = os.environ["R55_SHA256"].strip()
if actual_sha != expected_sha:
    raise RuntimeError(f"runtime sha mismatch: {actual_sha}")

app = pathlib.Path("/app")
if app.exists():
    shutil.rmtree(app)
app.mkdir(parents=True, exist_ok=True)

with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
    tf.extractall(app)

server = app / "server.py"
index = app / "public" / "index.html"
migrate = app / "migrate.py"
storage = app / "storage.py"

assert server.exists()
assert migrate.exists()
assert storage.exists()
assert index.exists() and index.stat().st_size > 200000

subprocess.check_call([sys.executable, "-m", "py_compile", str(server), str(migrate), str(storage)])
os.chdir(app)
subprocess.check_call([sys.executable, "migrate.py"])

print(f"MINJAZ_SOURCE_RUNTIME_OK sha={actual_sha} index_bytes={index.stat().st_size}", flush=True)
print("MINJAZ_SOURCE_SERVER_EXEC", flush=True)
os.execv(sys.executable, [sys.executable, "-u", "server.py"])
