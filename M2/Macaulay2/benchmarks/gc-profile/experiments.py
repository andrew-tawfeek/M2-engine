#!/usr/bin/env python3
"""Run the complete serial experiment matrix; finished samples are reused."""
import subprocess
from pathlib import Path
here=Path(__file__).resolve().parent
batches=[
 ['--kind','resource','--trials','5'],
 ['--kind','control','--workloads','forms','--modes','off','late-off','reserve','--trials','5'],
 ['--kind','stat','--workloads','forms','global','--trials','3'],
 ['--kind','record','--workloads','forms','--trials','3'],
 ['--kind','record','--workloads','global','gbZZbug3','--trials','1'],
 ['--kind','stat','--workloads','forms','--modes','reserve','--trials','3'],
 ['--kind','record','--workloads','forms','--modes','reserve','--trials','1'],
]
for arguments in batches:
 subprocess.run(['python3',str(here/'run.py'),*arguments],check=True)
