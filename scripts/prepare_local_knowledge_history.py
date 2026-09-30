#!/usr/bin/env python3
"""Assemble preserved stage files into history without fabricating execution evidence."""
import argparse
from pathlib import Path
import knowledge_pilot_trial as old
from knowledge_local_execution import HISTORY_SCHEMA,validate_history
from knowledge_export import read,digest,reject,Rejection


def assemble(directory,decision_path,partition_path,decision_pin,report_pin):
    decision=read(decision_path);report=read(directory/'validation-report.json')
    if digest(decision)!=decision_pin or digest(report)!=report_pin:reject('local-history-external-pin-mismatch')
    stages=[{key:read(directory/(stage+'.'+key+'.json')) for key in ('input','proposal','receipt')} for stage in old.STAGES]
    history={'schema':HISTORY_SCHEMA,'decision':decision,'partition':read(partition_path),
             'baseline':stages[0]['input']['baseline'],'stages':stages,'report':report}
    validate_history(history)
    return history


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('directory','decision','partition','output'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('decision-sha256','report-sha256'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    try:
        old.require_runtime_directory(args.output.parent)
        base=old.ROOT/'.runtime/knowledge/issue-0089'
        if any(args.output.resolve().is_relative_to(path.resolve()) for path in (args.directory,base/'trial',base/'adapter-recovery')):
            reject('local-history-separate-output-required')
        history=assemble(args.directory,args.decision,args.partition,args.decision_sha256,args.report_sha256)
        old.write_new(args.output,history);print(digest(history));return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError):print('local-history-assembly-rejected');return 1


if __name__=='__main__':raise SystemExit(main())
