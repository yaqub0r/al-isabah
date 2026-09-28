#!/usr/bin/env python3
"""One-stage local adapter recovery; no model dispatch or new semantic execution."""
import argparse
from pathlib import Path
import knowledge_pilot_trial as trial
from knowledge_export import digest, read, reject, Rejection

STAGE=trial.STAGES[0]
REVIEW_KEYS={'schema','task','worker','additionalWorkerTurnId','initialTurnOutputSha256','initialTurnFinalized','additionalTurnDisposition'}


def original_files(directory):
    """Read original evidence without copying, normalizing, or rewriting its bytes."""
    names={'decision':'decision.json','input':STAGE+'.input.json','output':STAGE+'.output.json'}
    values={key:read(directory/name) for key,name in names.items()}
    values['fileSha256']={key:trial.assembly.sha((directory/name).read_bytes()) for key,name in names.items()}
    return values


def request(original,packet,metadata,commit,review):
    current=trial.decision_request(packet,metadata,commit)
    old=original['decision']['request']
    # Recover exactly the old first-stage input, including its historical runbook.
    instructions=trial.git('show',old['codeCommit']+':docs/translation/knowledge-pilot-local-trial.md').decode('utf-8-sig').replace('\r\n','\n')
    expected={**current,'codeCommit':old['codeCommit'],'runbookLfSha256':trial.assembly.sha(instructions.encode('utf-8'))}
    trial.check_decision(original['decision'],digest(original['decision']),expected)
    stage_input=trial.stage_input_value(STAGE,old,digest(original['decision']),packet,metadata,[],instructions)
    if stage_input!=original['input']:reject('recovery-original-input-mismatch')
    trial.validate_output(original['output'],stage_input,packet)
    if (set(review)!=REVIEW_KEYS or review['schema']!='al-isabah.knowledge-local-trial-repair-review.v1'
            or review['initialTurnFinalized'] is not True
            or review['initialTurnOutputSha256']!=digest(original['output'])
            or review['additionalTurnDisposition']!='metadata_only_no_output_change'
            or not isinstance(review['additionalWorkerTurnId'],str) or not review['additionalWorkerTurnId']
            or review['additionalWorkerTurnId']==review['worker']['observed']['turnId']):
        reject('recovery-initial-turn-review-required')
    # This checks launch shape and independent parent linkage, but writes nothing.
    trial.capture(stage_input,original['output'],packet,digest(original['decision']),review['task'],review['worker'],[])
    return {'schema':'al-isabah.knowledge-local-trial-repair-request.v1',
            'action':'capture_unchanged_initial_output_and_finish_remaining_stages',
            'originalDecisionSha256':digest(original['decision']),
            'originalCodeCommit':old['codeCommit'],'originalInputSha256':digest(stage_input),
            'originalOutputSha256':digest(original['output']),'originalFileSha256':original['fileSha256'],
            'verifierCodeCommit':commit,'remainingStageRequest':current,
            'reviewSha256':digest(review),'taskSessionId':review['task']['observed']['sessionId'],
            'consumedWorkerSessionId':review['worker']['observed']['sessionId'],
            'consumedWorkers':1,'remainingStages':list(trial.STAGES[1:]),'maxRemainingFreshWorkers':2,
            'maxTotalFreshWorkers':3,'rerunExtractionAuthorized':False,
            'publicReleaseAuthorized':False,'consumerAdmissionAuthorized':False}


def authorize(decision,pin,original,packet,metadata,commit,review):
    if digest(decision)!=pin:reject('recovery-decision-pin-mismatch')
    if (set(decision)!={'schema','request','approval','origin'}
            or decision['schema']!='al-isabah.knowledge-local-trial-repair-decision.v1'
            or decision['approval']!='approved'
            or decision['origin']!={'kind':'trusted_coordinator_repair_review','threadId':trial.COORDINATOR}):
        reject('recovery-coordinator-review-required')
    expected=request(original,packet,metadata,commit,review)
    if decision['request']!=expected:reject('recovery-scope-mismatch')
    return expected


def capture_original(decision,pin,original,packet,metadata,commit,review,task,worker):
    authorize(decision,pin,original,packet,metadata,commit,review)
    # Re-observe both logs at capture. Neither worker self-report nor the review
    # alone substitutes for actual selected host metadata.
    if task!=review['task'] or worker!=review['worker']:reject('recovery-launch-mismatch')
    receipt=trial.capture(original['input'],original['output'],packet,digest(original['decision']),task,worker,[])
    value={'schema':'al-isabah.knowledge-local-trial-recovery.v1','kind':'retrospective_verification_not_execution',
           'repairDecisionSha256':pin,'originalExecutionCodeCommit':original['decision']['request']['codeCommit'],
           'verifierCodeCommit':commit,'receipt':receipt,'reviewSha256':digest(review)}
    value['recoverySha256']=digest(value)
    return value


def prepare(stage,decision,pin,original,packet,metadata,commit,review,recovery,prior=()):
    scope=authorize(decision,pin,original,packet,metadata,commit,review)
    if stage not in trial.STAGES[1:] or len(prior)!=trial.STAGES.index(stage)-1:reject('recovery-stage-order-mismatch')
    expected=capture_original(decision,pin,original,packet,metadata,commit,review,review['task'],review['worker'])
    if recovery!=expected:reject('recovery-receipt-mismatch')
    validated=[{**{k:original[k] for k in ('input','output')},'receipt':recovery['receipt']}]
    for n,item in enumerate(prior,1):
        expected_input=prepare(trial.STAGES[n],decision,pin,original,packet,metadata,commit,review,recovery,prior[:n-1])
        if item['input']!=expected_input:reject('trial-stage-input-drift')
        trial.validate_output(item['output'],expected_input,packet)
        trial.validate_receipt(item['receipt'],expected_input,item['output'],pin,[x['receipt'] for x in validated])
        validated.append(item)
    value=trial.stage_input_value(stage,scope['remainingStageRequest'],pin,packet,metadata,validated)
    value['recoverySha256']=recovery['recoverySha256']
    return value


def require_directories(original_directory,directory):
    trial.require_runtime_directory(directory);trial.require_runtime_directory(original_directory)
    if directory.resolve()==original_directory.resolve():reject('recovery-separate-directory-required')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['request','capture-original','prepare','capture','report'])
    p.add_argument('--original-directory',type=Path,required=True)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--review',type=Path,required=True)
    p.add_argument('--decision',type=Path);p.add_argument('--decision-sha256')
    p.add_argument('--packet',type=Path,default=trial.assembly.DEFAULT_PACKET)
    p.add_argument('--partition',type=Path,default=trial.assembly.DEFAULT_METADATA)
    p.add_argument('--stage',choices=trial.STAGES[1:])
    for key in ('task-log','worker-log','task-request','worker-request'):p.add_argument('--'+key,type=Path)
    for key in ('task-session','worker-session','task-turn','worker-turn'):p.add_argument('--'+key)
    args=p.parse_args()
    try:
        require_directories(args.original_directory,args.directory)
        original=original_files(args.original_directory);packet=read(args.packet);metadata=read(args.partition);review=read(args.review)
        commit=trial.git('rev-parse','HEAD').decode().strip()
        if args.action=='request':
            value=request(original,packet,metadata,commit,review)
            trial.write_new(args.directory/'repair-request.json',value);print(digest(value));return 0
        if not args.decision or not args.decision_sha256:reject('trial-authorization-inputs-required')
        decision=read(args.decision);pin=args.decision_sha256
        authorize(decision,pin,original,packet,metadata,commit,review)
        if args.action in {'capture-original','capture'}:
            if not all([args.task_log,args.worker_log,args.task_request,args.worker_request,args.task_session,args.worker_session,args.task_turn,args.worker_turn]):reject('trial-host-inputs-required')
            task={'request':read(args.task_request),'observed':trial.host_runtime.observe_session(args.task_log,args.task_session,args.task_turn)}
            worker={'request':read(args.worker_request),'observed':trial.host_runtime.observe_session(args.worker_log,args.worker_session,args.worker_turn,expected_parent_session_id=task['observed']['sessionId'])}
        if args.action=='capture-original':
            value=capture_original(decision,pin,original,packet,metadata,commit,review,task,worker)
            trial.write_new(args.directory/'recovery.json',value);print(value['recoverySha256']);return 0
        recovery=read(args.directory/'recovery.json')
        if args.action!='report' and not args.stage:reject('trial-stage-required')
        selected=args.stage if args.action!='report' else trial.STAGES[-1]
        prior=[]
        for stage in trial.STAGES[1:trial.STAGES.index(selected)]:
            prior.append({k:read(args.directory/(stage+'.'+k+'.json')) for k in ('input','output','receipt')})
        stage_input=prepare(selected,decision,pin,original,packet,metadata,commit,review,recovery,prior)
        if args.action=='prepare':
            trial.write_new(args.directory/(selected+'.input.json'),stage_input);print(digest(stage_input));return 0
        if stage_input!=read(args.directory/(selected+'.input.json')):reject('trial-stage-input-drift')
        output=read(args.directory/(selected+'.output.json'))
        upstream=[recovery['receipt'],*[x['receipt'] for x in prior]]
        if args.action=='capture':
            receipt=trial.capture(stage_input,output,packet,pin,task,worker,upstream)
            trial.write_new(args.directory/(selected+'.receipt.json'),receipt);print(receipt['receiptSha256']);return 0
        trial.validate_output(output,stage_input,packet)
        receipt=read(args.directory/(selected+'.receipt.json'))
        trial.validate_receipt(receipt,stage_input,output,pin,upstream)
        value={'schema':'al-isabah.knowledge-local-trial-recovery-validation.v1','status':output['status'],
               'repairDecisionSha256':pin,'recoverySha256':recovery['recoverySha256'],
               'originalExecutionCodeCommit':recovery['originalExecutionCodeCommit'],'verifierCodeCommit':commit,
               'stageOutputSha256':[digest(original['output']),*[digest(x['output']) for x in prior],digest(output)],
               'stageReceiptSha256':[x['receiptSha256'] for x in [*upstream,receipt]],
               'humanReview':'unreviewed','publicReleaseAuthorized':False,'consumerAdmissionAuthorized':False}
        trial.write_new(args.directory/'validation-report.json',value);print(value['status']);print(digest(value));return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError):print('local-trial-recovery-rejected');return 1


if __name__=='__main__':raise SystemExit(main())
