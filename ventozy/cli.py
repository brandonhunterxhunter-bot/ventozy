"""Punto de entrada para `ventozy` (console script de pyproject).

Delega a run.py para no duplicar la lógica CLI.
"""

import importlib.util
import os
import sys


def main() -> int:
    run_py = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "run.py")
    if not os.path.isfile(run_py):
        # instalado como paquete: buscar run.py instalado
        import ventozy
        run_py = os.path.join(os.path.dirname(ventozy.__file__), "..", "run.py")
    spec = importlib.util.spec_from_file_location("ventozy_run", run_py)
    mod = importlib.util.module_from_spec(spec)
    sys.argv[0] = run_py
    spec.loader.exec_module(mod)   # run.py ejecuta main() bajo __main__... no:
    # cuando se carga así, __name__ != "__main__", así que llamamos main:
    return mod.main()


if __name__ == "__main__":
    sys.exit(main())
