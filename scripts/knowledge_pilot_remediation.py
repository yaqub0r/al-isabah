#!/usr/bin/env python3
"""Separately authorized, local-only draft3 remediation; never dispatches models."""
import argparse
import copy
from pathlib import Path
import knowledge_pilot_trial as old
import knowledge_pilot_validation_v2 as current
from knowledge_export import read, digest, reject, Rejection

ROOT=old.ROOT
PROFILE=ROOT/'profiles/knowledge/volume-08.v2-draft3.json'
RUNBOOK=ROOT/'docs/translation/knowledge-pilot-remediation.md'
CRITICAL=('scripts/knowledge_pilot_remediation.py','scripts/knowledge_pilot_validation_v2.py',
          'scripts/knowledge_export_v2_draft3.py','scripts/knowledge_predicate_v3.py',
          'schemas/knowledge-pilot-stage-output.v2.schema.json',
          'schemas/al-isabah-knowledge-export.v2-draft3.schema.json',
          'profiles/knowledge/volume-08.v2-draft3.json','docs/translation/knowledge-pilot-remediation.md')


def baseline_value(stages,report,pin,packet):
    """Replay captured historical evidence, without reauthorizing its exhausted run."""
    if digest(report)!=pin:reject('remediation-baseline-pin-mismatch')
    if len(stages)!=3:reject('remediation-baseline-stage-mismatch')
    prior=[]
    for name,item in zip(old.STAGES,stages):
        stage=item['input']
        if (stage['stage']!=name or stage['lockedInput']!=packet
            or stage['priorOutputs']!=[x['output'] for x in prior]
            or stage['priorReceiptSha256']!=[x['receipt']['receiptSha256'] for x in prior]
            or stage['profile']!=read(old.PROFILE) or stage['profileSha256']!=digest(read(old.PROFILE))
            or stage['outputSchema']!=read(old.SCHEMA) or stage['outputSchemaSha256']!=digest(read(old.SCHEMA))):
            reject('remediation-baseline-stage-mismatch')
        old.validate_output(item['output'],stage,packet)
        old.validate_receipt(item['receipt'],stage,item['output'],stage['decisionSha256'],[x['receipt'] for x in prior])
        prior.append(item)
    if (report['stageOutputSha256']!=[digest(x['output']) for x in stages]
        or report['stageReceiptSha256']!=[x['receipt']['receiptSha256'] for x in stages]
        or report['status']!=stages[-1]['output']['status']
        or report['publicReleaseAuthorized'] is not False or report['consumerAdmissionAuthorized'] is not False):
        reject('remediation-baseline-report-mismatch')
    return {'schema':'al-isabah.knowledge-remediation-baseline.v1','report':copy.deepcopy(report),
            'reportSha256':pin,'stages':copy.deepcopy(stages)}


def baseline_output(baseline):return baseline['stages'][-1]['output']


def load_baseline(original,recovery,pin,packet):
    first=old.STAGES[0]
    stages=[{'input':read(original/(first+'.input.json')),'output':read(original/(first+'.output.json')),
             'receipt':read(recovery/'recovery.json')['receipt']}]
    stages.extend({k:read(recovery/(stage+'.'+k+'.json')) for k in ('input','output','receipt')} for stage in old.STAGES[1:])
    return baseline_value(stages,read(recovery/'validation-report.json'),pin,packet)


def request(packet,metadata,commit,baseline):
    baseline_value(baseline['stages'],baseline['report'],baseline['reportSha256'],packet)
    value=old.decision_request(packet,metadata,commit)
    if value['fixtureClass']!='synthetic-conformance':
        for path in CRITICAL:
            if old.git('show',commit+':'+path).replace(b'\r\n',b'\n')!=(ROOT/path).read_bytes().replace(b'\r\n',b'\n'):
                reject('trial-code-worktree-drift')
    value.update(schema='al-isabah.knowledge-remediation-request.v1',action='bounded_local_knowledge_remediation',
                 profileSha256=digest(read(PROFILE)),outputSchemaSha256=digest(read(current.SCHEMA)),
                 runbookLfSha256=old.assembly.lf_sha(RUNBOOK),baselineSha256=digest(baseline),
                 baselineReportSha256=baseline['reportSha256'],baselineOutputSha256=digest(baseline_output(baseline)),
                 baselineConcernIds=sorted(c['id'] for c in baseline_output(baseline)['concerns']))
    return value


def authorize(decision,pin,packet,metadata,commit,baseline):
    if digest(decision)!=pin:reject('trial-decision-pin-mismatch')
    if decision.get('schema')!='al-isabah.knowledge-remediation-decision.v1':reject('remediation-new-decision-required')
    # Reuse the exact trusted-operator origin checks, with a distinct decision version.
    adapted={**decision,'schema':'al-isabah.knowledge-local-trial-decision.v1'}
    result=old.check_decision(adapted,digest(adapted),request(packet,metadata,commit,baseline))
    return result


def validate_proposal(proposal,stage_input,packet):
    if set(proposal)!={'schema','output','baselineSha256','concernOutcomes','objectSuccessors'} or proposal['schema']!='al-isabah.knowledge-remediation-proposal.v1':
        reject('remediation-proposal-shape-mismatch')
    baseline=stage_input['baseline']
    if digest(baseline)!=stage_input['baselineSha256'] or proposal['baselineSha256']!=stage_input['baselineSha256']:
        reject('remediation-baseline-pin-mismatch')
    previous=baseline_output(baseline);output=proposal['output']
    current.validate_output(output,stage_input,packet)
    original={c['id']:c for c in previous['concerns']};now={c['id']:c for c in output['concerns']}
    outcomes={c['baselineConcernId']:c for c in proposal['concernOutcomes']}
    if len(outcomes)!=len(proposal['concernOutcomes']) or set(outcomes)!=set(original):reject('remediation-concern-loss')
    for cid,concern in original.items():
        row=outcomes[cid]
        if (set(row)!={'baselineConcernId','baselineConcernSha256','outcome','rationale'}
            or row['baselineConcernSha256']!=digest(concern) or row['outcome'] not in {'resolved','residual'}
            or not isinstance(row['rationale'],str) or not row['rationale'].strip()
            or cid not in now or now[cid]['category']!=concern['category'] or now[cid]['sourceSpanIds']!=concern['sourceSpanIds']
            or now[cid]['status']!=('resolved' if row['outcome']=='resolved' else 'open')):
            reject('remediation-concern-loss')
    # Each baseline object is retained byte-for-byte or has an explicit, same-kind successor.
    # No silent deletion or ID reuse, including the v1->v2 claim shape transition.
    mapping={ (r['before']['kind'],r['before']['id']):r for r in proposal['objectSuccessors'] }
    if len(mapping)!=len(proposal['objectSuccessors']):reject('remediation-successor-mismatch')
    expected=set();used=set()
    for kind in old.COLLECTIONS:
        now_objects={v['id']:v for v in output[kind]}
        for prior in [previous,*stage_input['priorOutputs']]:
            for value in prior[kind]:
                if value['id'] in now_objects and now_objects[value['id']]!=value:reject('trial-immutable-id-conflict')
        for value in previous[kind]:
            if value['id'] in now_objects:continue
            key=(kind,value['id']);expected.add(key);row=mapping.get(key)
            if (row is None or set(row)!={'before','beforeSha256','after','rationale'}
                or row['before']!={'kind':kind,'id':value['id']} or row['beforeSha256']!=digest(value)
                or set(row['after'])!={'kind','id'} or row['after']['kind']!=kind
                or row['after']['id'] not in now_objects or row['after']['id'] in {x['id'] for x in previous[kind]}
                or not isinstance(row['rationale'],str) or not row['rationale'].strip()):reject('remediation-successor-mismatch')
            target=(kind,row['after']['id'])
            if target in used:reject('remediation-successor-mismatch')
            used.add(target)
            if kind=='entities' and value['logicalEntityId']!=now_objects[row['after']['id']]['logicalEntityId']:reject('logical-identity-conflict')
    if set(mapping)!=expected:reject('remediation-successor-mismatch')
    return proposal


def prepare(stage,decision,pin,packet,metadata,commit,baseline,prior=()):
    req=authorize(decision,pin,packet,metadata,commit,baseline)
    if stage not in old.STAGES or len(prior)!=old.STAGES.index(stage):reject('trial-stage-order-mismatch')
    validated=[]
    for n,item in enumerate(prior):
        expected=prepare(old.STAGES[n],decision,pin,packet,metadata,commit,baseline,prior[:n])
        if item['input']!=expected:reject('trial-stage-input-drift')
        validate_proposal(item['proposal'],expected,packet)
        old.validate_receipt(item['receipt'],expected,item['proposal'],pin,[x['receipt'] for x in validated])
        validate_fresh_worker(item['receipt']['worker'],baseline)
        validated.append(item)
    value=old.stage_input_value(stage,req,pin,packet,metadata,[],RUNBOOK.read_text(encoding='utf-8-sig'))
    value.update(schema='al-isabah.knowledge-remediation-stage-input.v1',profile=read(PROFILE),outputSchema=read(current.SCHEMA),
                 baseline=copy.deepcopy(baseline),baselineSha256=digest(baseline),
                 priorOutputs=[x['proposal']['output'] for x in validated],
                 priorRemediations=[x['proposal'] for x in validated],priorReceiptSha256=[x['receipt']['receiptSha256'] for x in validated])
    return value


def validate_fresh_worker(worker,baseline):
    if worker['observed']['sessionId'] in {x['receipt']['worker']['observed']['sessionId'] for x in baseline['stages']}:
        reject('remediation-historical-worker-reuse')


def capture(stage_input,proposal,packet,pin,task,worker,prior_receipts):
    if pin!=stage_input['decisionSha256']:reject('trial-decision-pin-mismatch')
    validate_proposal(proposal,stage_input,packet);validate_fresh_worker(worker,stage_input['baseline'])
    receipt={'schema':'al-isabah.knowledge-local-trial-receipt.v2','fixtureClass':stage_input['fixtureClass'],
             'stage':stage_input['stage'],'stageInputSha256':digest(stage_input),'outputSha256':digest(proposal),
             'decisionSha256':pin,'methodRegistrySha256':stage_input['methodRegistrySha256'],
             'packetSha256':packet['packetSha256'],'sourceRecordVersionIds':stage_input['sourceRecordVersionIds'],
             'upstreamReceiptSha256':[r['receiptSha256'] for r in prior_receipts],'task':task,'worker':worker,
             'checkpointSha256':'','receiptSha256':''}
    receipt['checkpointSha256']=old.receipt_checkpoint(receipt)
    receipt['receiptSha256']=digest({k:v for k,v in receipt.items() if k!='receiptSha256'})
    return old.validate_receipt(receipt,stage_input,proposal,pin,prior_receipts)


def report(decision,pin,packet,metadata,commit,baseline,stages):
    if len(stages)!=3:reject('trial-stage-order-mismatch')
    for n,item in enumerate(stages):
        expected=prepare(old.STAGES[n],decision,pin,packet,metadata,commit,baseline,stages[:n])
        if expected!=item['input']:reject('trial-stage-input-drift')
        validate_proposal(item['proposal'],expected,packet);validate_fresh_worker(item['receipt']['worker'],baseline)
        old.validate_receipt(item['receipt'],expected,item['proposal'],pin,[x['receipt'] for x in stages[:n]])
    output=stages[-1]['proposal']['output'];req=decision['request']
    return {'schema':'al-isabah.knowledge-remediation-validation.v1','status':output['status'],
            'fixtureClass':req['fixtureClass'],'codeCommit':commit,'decisionSha256':pin,
            **{k:req[k] for k in ('baselineSha256','baselineReportSha256','baselineOutputSha256','profileSha256','outputSchemaSha256','packetSha256','partitionSha256')},
            'stageProposalSha256':[digest(x['proposal']) for x in stages],
            'stageReceiptSha256':[x['receipt']['receiptSha256'] for x in stages],
            'concernOutcomes':stages[-1]['proposal']['concernOutcomes'],
            'humanReview':'unreviewed','publicReleaseAuthorized':False,'consumerAdmissionAuthorized':False}


def require_directories(directory,original,recovery):
    old.require_runtime_directory(directory)
    target=directory.resolve()
    for protected in (original.resolve(),recovery.resolve()):
        if target.is_relative_to(protected) or protected.is_relative_to(target):reject('remediation-separate-directory-required')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['request','prepare','capture','report'])
    p.add_argument('--packet',type=Path,default=old.assembly.DEFAULT_PACKET);p.add_argument('--partition',type=Path,default=old.assembly.DEFAULT_METADATA)
    for name in ('original-directory','recovery-directory','directory'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--baseline-report-sha256',required=True);p.add_argument('--decision',type=Path);p.add_argument('--decision-sha256');p.add_argument('--stage',choices=old.STAGES)
    for key in ('task-log','worker-log','task-request','worker-request'):p.add_argument('--'+key,type=Path)
    for key in ('task-session','worker-session','task-turn','worker-turn'):p.add_argument('--'+key)
    args=p.parse_args()
    try:
        require_directories(args.directory,args.original_directory,args.recovery_directory)
        packet=read(args.packet);metadata=read(args.partition);commit=old.git('rev-parse','HEAD').decode().strip()
        baseline=load_baseline(args.original_directory,args.recovery_directory,args.baseline_report_sha256,packet)
        if args.action=='request':
            value=request(packet,metadata,commit,baseline);old.write_new(args.directory/'decision-request.json',value);print(digest(value));return 0
        if not args.decision or not args.decision_sha256:reject('trial-authorization-inputs-required')
        decision=read(args.decision);pin=args.decision_sha256
        stages=old.STAGES if args.action=='report' else old.STAGES[:old.STAGES.index(args.stage)] if args.stage else []
        prior=[{k:read(args.directory/(s+'.'+k+'.json')) for k in ('input','proposal','receipt')} for s in stages]
        if args.action=='report':
            value=report(decision,pin,packet,metadata,commit,baseline,prior);old.write_new(args.directory/'validation-report.json',value);print(value['status']);print(digest(value));return 0
        if not args.stage:reject('trial-stage-required')
        stage=prepare(args.stage,decision,pin,packet,metadata,commit,baseline,prior);path=args.directory/(args.stage+'.input.json')
        if args.action=='prepare':old.write_new(path,stage);print(digest(stage));return 0
        if read(path)!=stage:reject('trial-stage-input-drift')
        if not all([args.task_log,args.worker_log,args.task_request,args.worker_request,args.task_session,args.worker_session,args.task_turn,args.worker_turn]):reject('trial-host-inputs-required')
        task={'request':read(args.task_request),'observed':old.host_runtime.observe_session(args.task_log,args.task_session,args.task_turn)}
        worker={'request':read(args.worker_request),'observed':old.host_runtime.observe_session(args.worker_log,args.worker_session,args.worker_turn,expected_parent_session_id=task['observed']['sessionId'])}
        proposal=read(args.directory/(args.stage+'.proposal.json'))
        value=capture(stage,proposal,packet,pin,task,worker,[x['receipt'] for x in prior])
        old.write_new(args.directory/(args.stage+'.receipt.json'),value);print(value['receiptSha256']);return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError):print('local-remediation-operation-rejected');return 1


if __name__=='__main__':raise SystemExit(main())
