"""sanity_compile.py

Recursively compile all .py files to detect syntax errors quickly.
Usage: python sanity_compile.py
"""
import compileall
import sys
import os

root = os.path.dirname(__file__)
print("Compiling python files under {} ...".format(root))
ok = compileall.compile_dir(root, force=True, quiet=1)
if ok:
    print("All python files compiled successfully.")
    sys.exit(0)
else:
    print("One or more files failed to compile. See output above.")
    sys.exit(2)

