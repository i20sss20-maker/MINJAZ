# Temporary v30.2 validation bridge. Restored after the file-center isolation run.
from pathlib import Path
_target=Path(__file__).with_name("e2e_file_center_isolation.py")
exec(compile(_target.read_text(encoding="utf-8"),str(_target),"exec"))
