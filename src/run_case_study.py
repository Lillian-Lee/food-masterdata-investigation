"""Replay supplied evidence, test it and publish all three local report formats.

No fixture reset occurs here. Every subprocess must succeed before completion.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from pipeline_core import BASE_DIR


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--skip-workbook',action='store_true',help='Generate HTML and Markdown only')
    args=parser.parse_args()
    for script in ['approval_workflow.py','test_regressions.py','test_labeled_cases.py','generate_reports.py']:
        subprocess.run([sys.executable,str(BASE_DIR/'src'/script)],cwd=BASE_DIR,check=True)
    if not args.skip_workbook:
        bundled=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
        node=os.environ.get('ARTIFACT_NODE') or (str(bundled) if bundled.exists() else shutil.which('node'))
        if not node:
            raise RuntimeError('Node runtime required for workbook. Use --skip-workbook for HTML/Markdown only.')
        subprocess.run([node,str(BASE_DIR/'src/build_workbook.mjs')],cwd=BASE_DIR,check=True)
    print('Case study replay complete. Open reports/portfolio.html or reports/exception_report.xlsx.')


if __name__=='__main__':
    main()
