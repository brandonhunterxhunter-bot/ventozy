"""Punto de entrada para `ventozy` (console script de pyproject).

Delega a run.py para no duplicar la lógica CLI.
"""

import importlib.util
import os
import sys


def main() -> int:
    # instalado con pip: run.py vive como módulo `run` en site-packages…
    try:
        import run
        return run.main()
    except ImportError:
        pass
    # …en el repo: run.py es el archivo hermano del paquete
    run_py = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "run.py")
    spec = importlib.util.spec_from_file_location("ventozy_run", run_py)
    mod = importlib.util.module_from_spec(spec)
    sys.argv[0] = run_py
    spec.loader.exec_module(mod)   # __name__ != "__main__" al cargar así
    return mod.main()


if __name__ == "__main__":
    sys.exit(main())
