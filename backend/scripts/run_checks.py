"""Run backend regressions with isolated storage and test-module processes."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile


def main():
    backend = Path(__file__).resolve().parents[1]
    failures = []
    with tempfile.TemporaryDirectory(prefix="bapeten-checks-") as data:
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(backend), str(backend / "engine"))),
            "BAPETEN_DATA_DIR": data,
            "BAPETEN_API_TOKEN": "test-only-token",
            "BAPETEN_ALLOW_UNAUTHENTICATED_LOCAL_DEV": "0",
            "BAPETEN_VPN_MULTIUSER": "0",
            "BAPETEN_CORS_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173",
            "BAPETEN_OCR_PROCESSES": "2",
            "BAPETEN_FRONTEND_DIST": "",
        }
        suites = [(backend / "tests", "test_*.py")]
        suites += [(p.parent, p.name) for p in sorted((backend / "engine/tests").glob("test_*.py"))]
        # Some OCR tests stub optional dependencies in sys.modules; isolate each module.
        for directory, pattern in suites:
            label = f"{directory.relative_to(backend)}/{pattern}"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(directory),
                    "-p",
                    pattern,
                    "-v",
                ],
                cwd=backend,
                env=env,
                capture_output=True,
                text=True,
            )
            print(f"{'PASS' if result.returncode == 0 else 'FAIL'} {label}", flush=True)
            if result.returncode:
                failures.append(label)
                print(result.stdout + result.stderr, flush=True)
        print(f"{len(suites) - len(failures)}/{len(suites)} test suites passed.")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
