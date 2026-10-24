"""Profile an actual API or worker process; Ctrl+C flushes a local pstats artifact."""

import argparse
import cProfile
import datetime
import runpy
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("component", choices=["api", "worker"])
args = parser.parse_args()
output = Path(__file__).resolve().parent / "results"
output.mkdir(exist_ok=True)
path = output / f"{args.component}-{datetime.datetime.now(datetime.UTC):%Y%m%dT%H%M%SZ}.pstats"
profiler = cProfile.Profile()
try:
    profiler.enable()
    if args.component == "api":
        import uvicorn

        uvicorn.run("relayops.main:app", host="127.0.0.1", port=8000)
    else:
        runpy.run_module("relayops.workers.runner", run_name="__main__")
finally:
    profiler.disable()
    profiler.dump_stats(path)
    print(f"Profile saved to {path}; inspect with python -m pstats <path>.")
