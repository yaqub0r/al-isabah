#!/usr/bin/env python3
"""Prepare a separately authorized successor; never launch semantic workers."""
import argparse
import copy
from pathlib import Path

import knowledge_coverage_gate as gate
import knowledge_local_execution as execution
import knowledge_pilot_remediation as remediation
import knowledge_pilot_remediation_sol_high as sol
import knowledge_pilot_validation_v2 as private
from knowledge_export import read,digest,reject,Rejection

old=sol.old
ROOT=old.ROOT
RUNBOOK=ROOT/'docs/translation/knowledge-gated-successor-runbook.md'
CODE='scripts/knowledge_gated_successor.py'
RUNBOOK_NAME='docs/translation/knowledge-gated-successor-runbook.md'
REQUEST_SCHEMA='al-isabah.knowledge-gated-successor-request.v1'
DECISION_SCHEMA='al-isabah.knowledge-gated-successor-decision.v1'
STAGE_SCHEMA='al-isabah.knowledge-gated-successor-stage-input.v1'
RECEIPT_SCHEMA='al-isabah.knowledge-gated-successor-receipt.v1'
GATE_STATUS='partial_progress'


def validate_baseline(history,packet,partition,history_pin,report_pin,output_pin):
    if digest(history)!=history_pin or digest(history['report'])!=report_pin:
        reject('successor-baseline-pin-mismatch')
    locked=execution.validate_history(history)
    final=history['stages'][-1]['proposal']['output']
    if (locked!=packet or history['partition']!=partition
        or history['decision']['request']['codeCommit']!=execution.SOL_HIGH_COMMIT
        or digest(final)!=output_pin or history['report']['status']!='partial'
        or history['report']['humanReview']!='unreviewed'):
        reject('successor-baseline-mismatch')
    old.validate_packet(packet,partition)
    return final


def validate_seed(seed,packet,profile,baseline,report,seed_pin):
    if digest(seed)!=seed_pin:reject('successor-seed-pin-mismatch')
    schema=read(gate.SCHEMA)
    gate.schema_vocabulary(schema);gate.shape(seed,schema['$defs']['seed'],schema)
    if (seed['status']!='reviewed_for_gate' or seed['sourceArtifactSha256']!=packet['sourceArtifactSha256']
        or seed['packetSha256']!=packet['packetSha256'] or seed['baselineOutputSha256']!=digest(baseline)
        or seed['profileSha256']!=digest(profile) or seed['originReportSha256']!=digest(report)
        or seed['requestedSourceRecordVersionIds']!=sorted(r['id'] for r in packet['records'])):
        reject('successor-seed-scope-mismatch')
    obligations={row['id']:row for row in seed['obligations']}
    if len(obligations)!=len(seed['obligations']):reject('successor-seed-scope-mismatch')
    records={r['id'] for r in packet['records']}
    spans={s['id']:u['sourceRecordVersionId'] for u in packet['units'] for s in u['spans']}
    for row in obligations.values():
        if (row['recordId'] not in records or not row['sourceSpanIds']
            or any(spans.get(s)!=row['recordId'] for s in row['sourceSpanIds'])
            or row['kind']=='semantic_gap' and not row['expectedSemantics']):
            reject('successor-seed-scope-mismatch')
        for spec in row['expectedSemantics']:
            kind,name=spec['kind'],spec['semanticId']
            if (not name or kind=='claims' and name not in {x['id'] for x in profile['predicates']}
                or kind=='events' and name not in profile['eventTypes']
                or kind=='values' and not any(name==k+'|'+u['id'] for u in profile['valueUnits'] for k in u['valueKinds'])
                or kind=='reports' and name!='new_transmission_or_attribution'):
                reject('successor-seed-semantics-invalid')
    return seed


def verify_committed_code(commit):
    if old.git('rev-parse','HEAD').decode().strip()!=commit:reject('trial-code-commit-mismatch')
    for name in (CODE,RUNBOOK_NAME,'scripts/knowledge_local_execution.py','scripts/knowledge_coverage_gate.py',
                 'schemas/knowledge-coverage-gate.v1.schema.json',sol.CODE,sol.METHOD_NAME):
        if old.git('show',commit+':'+name).replace(b'\r\n',b'\n')!=(ROOT/name).read_bytes().replace(b'\r\n',b'\n'):
            reject('trial-code-worktree-drift')
    execution.verify_sol_high_dependencies()
    execution.verify_historical_dependencies()


def request(packet,partition,history,seed,commit,history_pin,report_pin,output_pin,seed_pin):
    verify_committed_code(commit)
    baseline=validate_baseline(history,packet,partition,history_pin,report_pin,output_pin)
    profile=read(remediation.PROFILE)
    validate_seed(seed,packet,profile,baseline,history['report'],seed_pin)
    registry,config=sol.configuration()
    return {'schema':REQUEST_SCHEMA,'fixtureClass':packet.get('fixtureClass','not-a-fixture'),
            'issue':89,'action':'bounded_known_coverage_successor','coordinatorThreadId':old.COORDINATOR,
            'codeCommit':commit,'sourceArtifactSha256':packet['sourceArtifactSha256'],
            'packetSha256':packet['packetSha256'],'partitionSha256':partition['partitionSha256'],
            'partitionFileSha256':digest(partition),'sourceOrdinals':partition['sourceOrdinals'],
            'profileSha256':digest(profile),'outputSchemaSha256':digest(read(private.SCHEMA)),
            'baselineHistorySha256':history_pin,'baselineDecisionSha256':digest(history['decision']),
            'baselineReportSha256':report_pin,'baselineOutputSha256':output_pin,
            'baselineReceiptSha256':[x['receipt']['receiptSha256'] for x in history['stages']],
            'seedSha256':seed_pin,'seedSchemaSha256':digest(read(gate.SCHEMA)),
            'historyVerifierLfSha256':old.assembly.lf_sha(ROOT/'scripts/knowledge_local_execution.py'),
            'gateCodeLfSha256':old.assembly.lf_sha(ROOT/'scripts/knowledge_coverage_gate.py'),
            'runnerLfSha256':old.assembly.lf_sha(ROOT/CODE),'runbookLfSha256':old.assembly.lf_sha(RUNBOOK),
            'methodRegistrySha256':digest(registry),'methodId':registry['methods'][0]['methodId'],
            'methodLfSha256':old.assembly.lf_sha(sol.METHOD),
            'stages':list(old.STAGES),'maxFreshWorkers':3,'gateStatusRequired':GATE_STATUS,
            'taskRequest':old.host_runtime.launch_request('codex-task',config['model'],config['reasoning']),
            'workerRequest':old.host_runtime.launch_request('codex-worker',config['model'],config['reasoning']),
            'provider':config['provider'],'humanReview':'unreviewed',
            'publicReleaseAuthorized':False,'consumerAdmissionAuthorized':False}


def authorize(decision,pin,packet,partition,history,seed,commit,history_pin,report_pin,output_pin,seed_pin):
    if digest(decision)!=pin or decision.get('schema')!=DECISION_SCHEMA:reject('successor-exact-decision-required')
    adapted={**decision,'schema':'al-isabah.knowledge-local-trial-decision.v1'}
    return old.check_decision(adapted,digest(adapted),
           request(packet,partition,history,seed,commit,history_pin,report_pin,output_pin,seed_pin))


def baseline_value(history):
    def workers(node):
        if isinstance(node,dict):
            receipt=node.get('receipt')
            if isinstance(receipt,dict) and isinstance(receipt.get('worker'),dict):
                yield receipt['worker']['observed']['sessionId']
            for key,value in node.items():
                if key!='receipt':yield from workers(value)
        elif isinstance(node,list):
            for value in node:yield from workers(value)
    return {'schema':'al-isabah.knowledge-gated-successor-baseline.v1','report':copy.deepcopy(history['report']),
            'historicalWorkerSessionIds':sorted(set(workers(history))),
            'stages':[{'input':copy.deepcopy(x['input']),'proposal':copy.deepcopy(x['proposal']),
                       'output':copy.deepcopy(x['proposal']['output']),'receipt':copy.deepcopy(x['receipt'])}
                      for x in history['stages']]}


def gate_result(packet,partition,history,seed,stage,proposal,ledger,req):
    pins={'sourceArtifactSha256':req['sourceArtifactSha256'],'packetSha256':req['packetSha256'],
          'baselineOutputSha256':req['baselineOutputSha256'],'profileSha256':req['profileSha256'],
          'seedSha256':req['seedSha256'],'originReportSha256':req['baselineReportSha256']}
    return gate.validate(packet,partition,read(remediation.PROFILE),history['stages'][-1]['input'],
                         history['stages'][-1]['proposal']['output'],stage,proposal,seed,ledger,pins)


def final_reconciliation(packet,partition,history,seed,stage,proposal,ledger,req,extraction_binding):
    try:
        checked=gate_result(packet,partition,history,seed,stage,proposal,ledger,req)
        status='retained_partial_progress'
    except Rejection as error:
        if str(error)!='coverage-no-material-progress':raise
        checked=None;status='not_established'
    return {'schema':'al-isabah.knowledge-gated-successor-final-reconciliation.v1',
            'status':status,'extractionGateSha256':extraction_binding['gateResultSha256'],
            'finalProposalSha256':digest(proposal),'finalLedgerSha256':digest(ledger),
            'materialObligationIds':checked['materialObligationIds'] if checked else [],
            'humanReview':'unreviewed','exhaustiveCoverage':False,
            'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False}


def gate_binding(first,packet,partition,history,seed,req):
    if set(first)!={'input','proposal','ledger','gate','receipt'}:reject('successor-gate-evidence-required')
    actual=gate_result(packet,partition,history,seed,first['input'],first['proposal'],first['ledger'],req)
    if first['gate']!=actual or actual['status']!=GATE_STATUS:reject('successor-gate-evidence-mismatch')
    receipt=first['receipt']
    if (receipt.get('firstProposalSha256')!=digest(first['proposal'])
        or receipt.get('ledgerSha256')!=digest(first['ledger'])
        or receipt.get('gateResultSha256')!=digest(actual)):
        reject('successor-gate-receipt-mismatch')
    return {'proposalSha256':digest(first['proposal']),'ledgerSha256':digest(first['ledger']),
            'gateResultSha256':digest(actual),'firstReceiptSha256':first['receipt']['receiptSha256']}


def prepare(name,decision,pin,packet,partition,history,seed,commit,history_pin,report_pin,output_pin,seed_pin,prior=()):
    req=authorize(decision,pin,packet,partition,history,seed,commit,history_pin,report_pin,output_pin,seed_pin)
    if name not in old.STAGES or len(prior)!=old.STAGES.index(name):reject('trial-stage-order-mismatch')
    checked=[]
    for n,item in enumerate(prior):
        expected=prepare(old.STAGES[n],decision,pin,packet,partition,history,seed,commit,
                         history_pin,report_pin,output_pin,seed_pin,prior[:n])
        if item['input']!=expected:reject('trial-stage-input-drift')
        remediation.validate_proposal(item['proposal'],expected,packet)
        if n==0:
            binding=gate_binding(item,packet,partition,history,seed,req)
        else:
            if set(item)!={'input','proposal','receipt'}:reject('successor-stage-shape-mismatch')
            binding=gate_binding(prior[0],packet,partition,history,seed,req)
        validate_receipt(item['receipt'],expected,item['proposal'],packet,pin,
                         [x['receipt'] for x in checked],binding,
                         item['ledger'] if n==0 else None,item['gate'] if n==0 else None)
        checked.append(item)
    if checked and checked[0]['gate']['status']!=GATE_STATUS:reject('successor-gate-not-passed')
    base=baseline_value(history)
    value=old.stage_input_value(name,req,pin,packet,partition,[],RUNBOOK.read_text(encoding='utf-8-sig'))
    value.update(schema=STAGE_SCHEMA,profile=read(remediation.PROFILE),outputSchema=read(private.SCHEMA),
                 baseline=base,baselineSha256=digest(base),baselineHistorySha256=history_pin,
                 seed=copy.deepcopy(seed),seedSha256=seed_pin,
                 gateBinding=gate_binding(checked[0],packet,partition,history,seed,req) if checked else {},
                 extractionEvidence={'ledger':copy.deepcopy(checked[0]['ledger']),
                                     'gateResult':copy.deepcopy(checked[0]['gate'])} if checked else {},
                 priorOutputs=[x['proposal']['output'] for x in checked],
                 priorRemediations=[x['proposal'] for x in checked],
                 priorReceiptSha256=[x['receipt']['receiptSha256'] for x in checked])
    return value


def capture(stage,proposal,packet,pin,task,worker,prior_receipts,binding,ledger=None,gate_evidence=None,
            final_ledger=None,final_evidence=None):
    if pin!=stage['decisionSha256']:reject('trial-decision-pin-mismatch')
    if stage['stage']==old.STAGES[0]:
        if ledger is None or gate_evidence is None or stage['gateBinding'] or not binding:
            reject('successor-gate-evidence-required')
        if (gate_evidence.get('status')!=GATE_STATUS
            or binding['proposalSha256']!=digest(proposal) or binding['ledgerSha256']!=digest(ledger)
            or binding['gateResultSha256']!=digest(gate_evidence)):
            reject('successor-gate-evidence-mismatch')
    elif (binding!=stage['gateBinding']
          or not prior_receipts or binding['firstReceiptSha256']!=prior_receipts[0]['receiptSha256']):
        reject('successor-gate-evidence-mismatch')
    if stage['stage']==old.STAGES[2]:
        if (ledger is not None or gate_evidence is not None or final_ledger is None
            or final_evidence is None or final_evidence.get('finalProposalSha256')!=digest(proposal)
            or final_evidence.get('finalLedgerSha256')!=digest(final_ledger)
            or final_evidence.get('extractionGateSha256')!=binding['gateResultSha256']):
            reject('successor-final-evidence-mismatch')
    elif final_ledger is not None or final_evidence is not None or (stage['stage']!=old.STAGES[0] and (ledger is not None or gate_evidence is not None)):
        reject('successor-final-evidence-mismatch')
    if worker['observed']['sessionId'] in stage['baseline']['historicalWorkerSessionIds']:
        reject('successor-historical-worker-reuse')
    base=sol.capture(stage,proposal,packet,pin,task,worker,prior_receipts)
    value={**base,'schema':RECEIPT_SCHEMA,'firstProposalSha256':binding['proposalSha256'],
           'ledgerSha256':binding['ledgerSha256'],'gateResultSha256':binding['gateResultSha256'],
           'finalLedgerSha256':digest(final_ledger) if final_ledger is not None else '',
           'finalReconciliationSha256':digest(final_evidence) if final_evidence is not None else ''}
    value['checkpointSha256']=old.receipt_checkpoint(value)
    value['receiptSha256']=digest({k:v for k,v in value.items() if k!='receiptSha256'})
    return value


def validate_receipt(receipt,stage,proposal,packet,pin,prior_receipts,binding,ledger=None,gate_evidence=None,
                     final_ledger=None,final_evidence=None):
    expected=capture(stage,proposal,packet,pin,receipt['task'],receipt['worker'],prior_receipts,binding,
                     ledger,gate_evidence,final_ledger,final_evidence)
    if receipt!=expected:reject('successor-receipt-mismatch')
    return receipt


def report(decision,pin,packet,partition,history,seed,commit,history_pin,report_pin,output_pin,seed_pin,stages):
    if len(stages)!=3:reject('trial-stage-order-mismatch')
    if set(stages[-1])!={'input','proposal','ledger','gate','receipt'}:
        reject('successor-final-evidence-required')
    binding=gate_binding(stages[0],packet,partition,history,seed,decision['request'])
    final=final_reconciliation(packet,partition,history,seed,stages[-1]['input'],
                               stages[-1]['proposal'],stages[-1]['ledger'],decision['request'],binding)
    if stages[-1]['gate']!=final:reject('successor-final-evidence-mismatch')
    for n,item in enumerate(stages):
        expected=prepare(old.STAGES[n],decision,pin,packet,partition,history,seed,commit,
                         history_pin,report_pin,output_pin,seed_pin,stages[:n])
        if item['input']!=expected:reject('trial-stage-input-drift')
        validate_receipt(item['receipt'],expected,item['proposal'],packet,pin,
                         [x['receipt'] for x in stages[:n]],binding,
                         item['ledger'] if n==0 else None,item['gate'] if n==0 else None,
                         item['ledger'] if n==2 else None,item['gate'] if n==2 else None)
    if stages[-1]['proposal']['output']['status']=='complete':reject('successor-premature-completion')
    return {'schema':'al-isabah.knowledge-gated-successor-validation.v1','status':'partial',
            'extractionGateStatus':GATE_STATUS,'finalKnownCoverageStatus':final['status'],
            'finalMaterialObligationIds':final['materialObligationIds'],'humanReview':'unreviewed',
            'independentSemanticReview':'completed_with_residuals',
            'decisionSha256':pin,'baselineHistorySha256':history_pin,
            'baselineReportSha256':report_pin,'baselineOutputSha256':output_pin,
            'seedSha256':seed_pin,'gateResultSha256':binding['gateResultSha256'],
            'finalLedgerSha256':digest(stages[-1]['ledger']),
            'finalReconciliationSha256':digest(final),
            'stageProposalSha256':[digest(x['proposal']) for x in stages],
            'stageReceiptSha256':[x['receipt']['receiptSha256'] for x in stages],
            'exhaustiveCoverage':False,'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False}


def require_directory(directory):
    old.require_runtime_directory(directory)
    base=ROOT/'.runtime/knowledge/issue-0089'
    if any(directory.resolve().is_relative_to((base/name).resolve()) or (base/name).resolve().is_relative_to(directory.resolve())
           for name in ('trial','adapter-recovery','remediation-draft3-e2a8985','remediation-sol-high-dbb54fa')):
        reject('successor-separate-directory-required')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('request','prepare','gate','capture','report'))
    for name in ('history','seed','directory'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--packet',type=Path,default=old.assembly.DEFAULT_PACKET)
    p.add_argument('--partition',type=Path,default=old.assembly.DEFAULT_METADATA)
    for name in ('history-sha256','baseline-report-sha256','baseline-output-sha256','seed-sha256'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--decision',type=Path);p.add_argument('--decision-sha256');p.add_argument('--stage',choices=old.STAGES)
    for key in ('task-log','worker-log','task-request','worker-request'):p.add_argument('--'+key,type=Path)
    for key in ('task-session','worker-session','task-turn','worker-turn'):p.add_argument('--'+key)
    args=p.parse_args()
    try:
        require_directory(args.directory)
        packet=read(args.packet);partition=read(args.partition);history=read(args.history);seed=read(args.seed)
        commit=old.git('rev-parse','HEAD').decode().strip()
        common=(packet,partition,history,seed,commit,args.history_sha256,args.baseline_report_sha256,
                args.baseline_output_sha256,args.seed_sha256)
        if args.action=='request':
            value=request(*common);old.write_new(args.directory/'decision-request.json',value)
            print(digest(value));return 0
        if not args.decision or not args.decision_sha256:reject('successor-exact-decision-required')
        decision=read(args.decision);pin=args.decision_sha256
        if args.action=='gate':
            name=args.stage
            if name not in (old.STAGES[0],old.STAGES[2]):reject('successor-gate-stage-required')
            prior=[]
            for previous in old.STAGES[:old.STAGES.index(name)]:
                keys=('input','proposal','ledger','gate','receipt') if previous==old.STAGES[0] else ('input','proposal','receipt')
                prior.append({k:read(args.directory/(previous+'.'+k+'.json')) for k in keys})
            stage=read(args.directory/(name+'.input.json'))
            expected=prepare(name,decision,pin,*common,prior)
            if stage!=expected:reject('trial-stage-input-drift')
            proposal=read(args.directory/(name+'.proposal.json'))
            ledger=read(args.directory/(name+'.ledger.json'))
            value=(gate_result(packet,partition,history,seed,stage,proposal,ledger,decision['request'])
                   if name==old.STAGES[0] else final_reconciliation(packet,partition,history,seed,
                       stage,proposal,ledger,decision['request'],
                       gate_binding(prior[0],packet,partition,history,seed,decision['request'])))
            old.write_new(args.directory/(name+'.gate.json'),value);print(digest(value));return 0
        names=old.STAGES if args.action=='report' else old.STAGES[:old.STAGES.index(args.stage)] if args.stage else []
        prior=[]
        for name in names:
            keys=('input','proposal','ledger','gate','receipt') if name in (old.STAGES[0],old.STAGES[2]) else ('input','proposal','receipt')
            prior.append({k:read(args.directory/(name+'.'+k+'.json')) for k in keys})
        if args.action=='report':
            value=report(decision,pin,*common,prior)
            old.write_new(args.directory/'validation-report.json',value);print(digest(value));return 0
        if not args.stage:reject('trial-stage-required')
        stage=prepare(args.stage,decision,pin,*common,prior);path=args.directory/(args.stage+'.input.json')
        if args.action=='prepare':old.write_new(path,stage);print(digest(stage));return 0
        if read(path)!=stage:reject('trial-stage-input-drift')
        if not all([args.task_log,args.worker_log,args.task_request,args.worker_request,
                    args.task_session,args.worker_session,args.task_turn,args.worker_turn]):
            reject('trial-host-inputs-required')
        task={'request':read(args.task_request),
              'observed':old.host_runtime.observe_session(args.task_log,args.task_session,args.task_turn)}
        worker={'request':read(args.worker_request),
                'observed':old.host_runtime.observe_session(args.worker_log,args.worker_session,args.worker_turn,
                     expected_parent_session_id=task['observed']['sessionId'])}
        proposal=read(args.directory/(args.stage+'.proposal.json'))
        if not prior:
            ledger=read(args.directory/(args.stage+'.ledger.json'))
            gate_evidence=read(args.directory/(args.stage+'.gate.json'))
            if gate_evidence!=gate_result(packet,partition,history,seed,stage,proposal,ledger,decision['request']):
                reject('successor-gate-evidence-mismatch')
        final_ledger=final_evidence=None
        if args.stage==old.STAGES[2]:
            final_ledger=read(args.directory/(args.stage+'.ledger.json'))
            final_evidence=read(args.directory/(args.stage+'.gate.json'))
            if final_evidence!=final_reconciliation(packet,partition,history,seed,stage,proposal,
                 final_ledger,decision['request'],gate_binding(prior[0],packet,partition,history,seed,decision['request'])):
                reject('successor-final-evidence-mismatch')
        binding=(gate_binding(prior[0],packet,partition,history,seed,decision['request']) if prior else
                 {'proposalSha256':digest(proposal),'ledgerSha256':digest(ledger),
                  'gateResultSha256':digest(gate_evidence),'firstReceiptSha256':''})
        value=capture(stage,proposal,packet,pin,task,worker,[x['receipt'] for x in prior],binding,
                      ledger if not prior else None,gate_evidence if not prior else None,
                      final_ledger,final_evidence)
        old.write_new(args.directory/(args.stage+'.receipt.json'),value);print(value['receiptSha256']);return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError,IndexError,AttributeError):
        print('gated-successor-operation-rejected');return 1


if __name__=='__main__':raise SystemExit(main())
