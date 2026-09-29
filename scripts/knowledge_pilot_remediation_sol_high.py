#!/usr/bin/env python3
"""Exact GPT-6 Sol/High adapter for the separately approved 13-entry pilot.

The historical runner and method registry remain immutable. This adapter only
selects the local pilot method and validates its actual host observations.
"""
import argparse
import copy
from pathlib import Path

import knowledge_pilot_remediation as prior
from knowledge_export import read,digest,reject,Rejection
from schema_validation import validate_schema_instance

old=prior.old
ROOT=old.ROOT
METHOD=ROOT/'profiles/knowledge/remediation-sol-high.local.v1.json'
CODE='scripts/knowledge_pilot_remediation_sol_high.py'
METHOD_NAME='profiles/knowledge/remediation-sol-high.local.v1.json'
REQUEST_SCHEMA='al-isabah.knowledge-remediation-request.v2'
DECISION_SCHEMA='al-isabah.knowledge-remediation-decision.v2'


def configuration():
    registry=read(METHOD)
    if (registry.get('schema')!='al-isabah.knowledge-method-registry.v1-local'
        or registry.get('status')!='local-pilot-only' or registry.get('realExecutionEnabled') is not False
        or len(registry.get('methods',[]))!=1
        or registry['methods'][0].get('methodId')!='codex-gpt6-sol-high-knowledge-local-remediation-1'
        or registry['methods'][0].get('stages')!=list(old.STAGES)):
        reject('remediation-local-method-mismatch')
    config=registry['methods'][0]['configuration']
    if config!={'provider':'openai','model':'gpt-6-sol','reasoning':'high',
               'orchestration':'explicit-fresh-host-runtime-v1','configurationOrigin':'explicit'}:
        reject('remediation-local-method-mismatch')
    return registry,config


def verify_adapter(commit):
    for path in (CODE,METHOD_NAME):
        if old.git('show',commit+':'+path).replace(b'\r\n',b'\n')!=(ROOT/path).read_bytes().replace(b'\r\n',b'\n'):
            reject('trial-code-worktree-drift')


def request(packet,partition,commit,baseline):
    value=prior.request(packet,partition,commit,baseline)
    if value['fixtureClass']!='synthetic-conformance':verify_adapter(commit)
    registry,config=configuration()
    value.update(schema=REQUEST_SCHEMA,methodRegistrySha256=digest(registry),
                 methodId=registry['methods'][0]['methodId'],
                 taskRequest=old.host_runtime.launch_request('codex-task',config['model'],config['reasoning']),
                 workerRequest=old.host_runtime.launch_request('codex-worker',config['model'],config['reasoning']))
    return value


def authorize(decision,pin,packet,partition,commit,baseline):
    if digest(decision)!=pin:reject('trial-decision-pin-mismatch')
    if decision.get('schema')!=DECISION_SCHEMA:reject('remediation-new-decision-required')
    adapted={**decision,'schema':'al-isabah.knowledge-local-trial-decision.v1'}
    return old.check_decision(adapted,digest(adapted),request(packet,partition,commit,baseline))


def validate_receipt(receipt,stage_input,proposal,pin,prior_receipts):
    expected_keys={'schema','fixtureClass','stage','stageInputSha256','outputSha256','decisionSha256',
                   'methodRegistrySha256','packetSha256','sourceRecordVersionIds','upstreamReceiptSha256',
                   'task','worker','checkpointSha256','receiptSha256'}
    if set(receipt)!=expected_keys or receipt['schema']!='al-isabah.knowledge-local-trial-receipt.v2':
        reject('trial-receipt-shape-mismatch')
    for key,value in [('fixtureClass',stage_input['fixtureClass']),('stage',stage_input['stage']),
                      ('stageInputSha256',digest(stage_input)),('outputSha256',digest(proposal)),
                      ('decisionSha256',pin),('methodRegistrySha256',stage_input['methodRegistrySha256']),
                      ('packetSha256',stage_input['packetSha256']),('sourceRecordVersionIds',stage_input['sourceRecordVersionIds']),
                      ('upstreamReceiptSha256',[r['receiptSha256'] for r in prior_receipts])]:
        if receipt[key]!=value:reject('trial-receipt-binding-mismatch')
    launch_schema=read(old.method.SCHEMA_PATH)
    launch_schema['properties']['worker']['properties']['observed']=read(old.WORKER_OBSERVATION)
    if any(validate_schema_instance(receipt[k],launch_schema['properties'][k]) for k in ('task','worker')):
        reject('trial-host-mismatch')
    registry,config=configuration()
    if stage_input['methodRegistrySha256']!=digest(registry):reject('trial-host-mismatch')
    if (old.host_runtime.launch_errors(receipt['task'],config,'codex-task')
        or old.host_runtime.launch_errors(receipt['worker'],config,'codex-worker')):
        reject('trial-host-mismatch')
    if receipt['task']['request']!=stage_input['taskRequest'] or receipt['worker']['request']!=stage_input['workerRequest']:
        reject('trial-host-mismatch')
    if receipt['worker']['observed']['parentSessionId']!=receipt['task']['observed']['sessionId']:
        reject('trial-worker-parent-mismatch')
    used={r['worker']['observed']['sessionId'] for r in prior_receipts}|{receipt['task']['observed']['sessionId']}
    if (receipt['worker']['observed']['sessionId'] in used
        or any(old.task_identity(r['task'])!=old.task_identity(receipt['task']) for r in prior_receipts)):
        reject('trial-worker-independence-mismatch')
    if (old.receipt_checkpoint(receipt)!=receipt['checkpointSha256']
        or digest({k:v for k,v in receipt.items() if k!='receiptSha256'})!=receipt['receiptSha256']):
        reject('trial-receipt-binding-mismatch')
    return receipt


def prepare(stage,decision,pin,packet,partition,commit,baseline,prior_stages=()):
    req=authorize(decision,pin,packet,partition,commit,baseline)
    if stage not in old.STAGES or len(prior_stages)!=old.STAGES.index(stage):reject('trial-stage-order-mismatch')
    validated=[]
    for n,item in enumerate(prior_stages):
        expected=prepare(old.STAGES[n],decision,pin,packet,partition,commit,baseline,prior_stages[:n])
        if item['input']!=expected:reject('trial-stage-input-drift')
        prior.validate_proposal(item['proposal'],expected,packet)
        validate_receipt(item['receipt'],expected,item['proposal'],pin,[x['receipt'] for x in validated])
        prior.validate_fresh_worker(item['receipt']['worker'],baseline)
        validated.append(item)
    value=old.stage_input_value(stage,req,pin,packet,partition,[],prior.RUNBOOK.read_text(encoding='utf-8-sig'))
    value.update(schema='al-isabah.knowledge-remediation-stage-input.v1',profile=read(prior.PROFILE),
                 outputSchema=read(prior.current.SCHEMA),baseline=copy.deepcopy(baseline),
                 baselineSha256=digest(baseline),priorOutputs=[x['proposal']['output'] for x in validated],
                 priorRemediations=[x['proposal'] for x in validated],
                 priorReceiptSha256=[x['receipt']['receiptSha256'] for x in validated])
    return value


def capture(stage_input,proposal,packet,pin,task,worker,prior_receipts):
    if pin!=stage_input['decisionSha256']:reject('trial-decision-pin-mismatch')
    prior.validate_proposal(proposal,stage_input,packet)
    prior.validate_fresh_worker(worker,stage_input['baseline'])
    receipt={'schema':'al-isabah.knowledge-local-trial-receipt.v2','fixtureClass':stage_input['fixtureClass'],
             'stage':stage_input['stage'],'stageInputSha256':digest(stage_input),'outputSha256':digest(proposal),
             'decisionSha256':pin,'methodRegistrySha256':stage_input['methodRegistrySha256'],
             'packetSha256':packet['packetSha256'],'sourceRecordVersionIds':stage_input['sourceRecordVersionIds'],
             'upstreamReceiptSha256':[r['receiptSha256'] for r in prior_receipts],
             'task':task,'worker':worker,'checkpointSha256':'','receiptSha256':''}
    receipt['checkpointSha256']=old.receipt_checkpoint(receipt)
    receipt['receiptSha256']=digest({k:v for k,v in receipt.items() if k!='receiptSha256'})
    return validate_receipt(receipt,stage_input,proposal,pin,prior_receipts)


def report(decision,pin,packet,partition,commit,baseline,stages):
    if len(stages)!=len(old.STAGES):reject('trial-stage-order-mismatch')
    for n,item in enumerate(stages):
        expected=prepare(old.STAGES[n],decision,pin,packet,partition,commit,baseline,stages[:n])
        if item['input']!=expected:reject('trial-stage-input-drift')
        prior.validate_proposal(item['proposal'],expected,packet)
        prior.validate_fresh_worker(item['receipt']['worker'],baseline)
        validate_receipt(item['receipt'],expected,item['proposal'],pin,[x['receipt'] for x in stages[:n]])
    output=stages[-1]['proposal']['output'];req=decision['request']
    return {'schema':'al-isabah.knowledge-remediation-validation.v1','status':output['status'],
            'fixtureClass':req['fixtureClass'],'codeCommit':commit,'decisionSha256':pin,
            **{k:req[k] for k in ('baselineSha256','baselineReportSha256','baselineOutputSha256',
                                  'profileSha256','outputSchemaSha256','packetSha256','partitionSha256')},
            'stageProposalSha256':[digest(x['proposal']) for x in stages],
            'stageReceiptSha256':[x['receipt']['receiptSha256'] for x in stages],
            'concernOutcomes':stages[-1]['proposal']['concernOutcomes'],'humanReview':'unreviewed',
            'publicReleaseAuthorized':False,'consumerAdmissionAuthorized':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('request','prepare','capture','report'))
    parser.add_argument('--packet',type=Path,default=old.assembly.DEFAULT_PACKET)
    parser.add_argument('--partition',type=Path,default=old.assembly.DEFAULT_METADATA)
    for name in ('original-directory','recovery-directory','directory'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--baseline-report-sha256',required=True)
    parser.add_argument('--decision',type=Path)
    parser.add_argument('--decision-sha256')
    parser.add_argument('--stage',choices=old.STAGES)
    for name in ('task-log','worker-log','task-request','worker-request'):
        parser.add_argument('--'+name,type=Path)
    for name in ('task-session','worker-session','task-turn','worker-turn'):
        parser.add_argument('--'+name)
    args=parser.parse_args()
    try:
        prior.require_directories(args.directory,args.original_directory,args.recovery_directory)
        packet=read(args.packet);partition=read(args.partition)
        commit=old.git('rev-parse','HEAD').decode().strip()
        baseline=prior.load_baseline(args.original_directory,args.recovery_directory,args.baseline_report_sha256,packet)
        if args.action=='request':
            value=request(packet,partition,commit,baseline)
            old.write_new(args.directory/'decision-request.json',value)
            print(digest(value));return 0
        if not args.decision or not args.decision_sha256:reject('trial-authorization-inputs-required')
        decision=read(args.decision);pin=args.decision_sha256
        stages=old.STAGES if args.action=='report' else old.STAGES[:old.STAGES.index(args.stage)] if args.stage else []
        prior_stages=[{k:read(args.directory/(name+'.'+k+'.json')) for k in ('input','proposal','receipt')} for name in stages]
        if args.action=='report':
            value=report(decision,pin,packet,partition,commit,baseline,prior_stages)
            old.write_new(args.directory/'validation-report.json',value)
            print(value['status']);print(digest(value));return 0
        if not args.stage:reject('trial-stage-required')
        stage=prepare(args.stage,decision,pin,packet,partition,commit,baseline,prior_stages)
        path=args.directory/(args.stage+'.input.json')
        if args.action=='prepare':
            old.write_new(path,stage);print(digest(stage));return 0
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
        value=capture(stage,proposal,packet,pin,task,worker,[x['receipt'] for x in prior_stages])
        old.write_new(args.directory/(args.stage+'.receipt.json'),value)
        print(value['receiptSha256']);return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError):
        print('local-remediation-sol-high-operation-rejected');return 1


if __name__=='__main__':raise SystemExit(main())
