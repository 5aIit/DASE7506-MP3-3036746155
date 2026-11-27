"""Write the exact package list of the interpreter that runs it (for requirements-v3.txt)."""
import importlib.metadata as metadata
import sys

lines = sorted(f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions())
header = [f"# Exact environment of the v3 test run: Python {sys.version.split()[0]}, Linux x86_64.",
          "# torch is the CPU wheel: pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu"]
open(sys.argv[1], "w").write("\n".join(header + [l.replace("+cpu", "") if l.startswith("torch==") else l
                                                 for l in lines]) + "\n")
print(len(lines), "packages")
