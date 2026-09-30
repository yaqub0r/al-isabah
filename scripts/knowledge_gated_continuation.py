#!/usr/bin/env python3
"""Issue 89 supplemental launch gate; original a56 execution remains immutable."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import knowledge_gated_successor as original
from knowledge_export import read,digest,canonical,reject,Rejection

ROOT=original.ROOT
CODE='scripts/knowledge_gated_continuation.py'
RUNBOOK='docs/translation/knowledge-gated-continuation.md'
ORIGINAL_COMMIT='a56a7c5aa3864d87caf7b5d267647ae66ef7016e'
PINS={
 'decision-request.json':'b5b26184d5854d5fd79a1ed3479ebb216a0ff211b0025555eb2b45c18e6110ea',
 'approved-decision.json':'ea5ad281cf62d9a09c8d35e649e72ae134b47ca0d00424acf25c73718e51819e',
 'knowledge_extraction.input.json':'22f33dc2b175fab3ad8d3eaad83c739dae72b30f870bdd51461af1845541f0fd',
 'knowledge_extraction.proposal.json':'e9d09e45c0b29884ee28ca5ff6e9b07e5f5ef7f1fffc0f0785d694add4f0bfcf',
 'knowledge_extraction.ledger.json':'5a7d6112087945b587982d53f3f66ae79f9065cf2287d5e67d771fad6f08c762',
 'knowledge_extraction.gate.json':'42e96ec59bf47304b42fbe04d24ff7af525c665c5b2f9b8a4d987afa4e0958be',
 'knowledge_extraction.receipt.json':'ce6eb06cef4b961907de8b80ceb8274d9dc7a032fc2996eab093537fdce15ecf',
 'knowledge_independent_review.input.json':'7a1c3ef990a717ee4f4ce6a84817d2f79fd3202ca72ffe22205ee10bf794ea57',
}
FAILED_SESSION='01a0edbb-1bcf-7522-b901-4d6660e83bb9'
FAILED_TURN='01a0edbb-1c6c-7e23-9c7b-0cd602fb04a9'
FAILED_LOG_SHA='7595b43864af66a16d559851e85705cd17bb81cc45cb2cb844425c206f30b881'
FAILED_ERROR='Selected model is at capacity. Please try a different model.'
REVIEW,ADJUDICATION=original.old.STAGES[1:]
REQUEST_SCHEMA='al-isabah.knowledge-gated-continuation-request.v1'
DECISION_SCHEMA='al-isabah.knowledge-gated-continuation-decision.v1'
STAGE_SCHEMA='al-isabah.knowledge-gated-continuation-stage-input.v1'
RECEIPT_SCHEMA='al-isabah.knowledge-gated-continuation-receipt.v1'
REPAIR_SCHEMA='al-isabah.knowledge-gated-continuation-execution-repair.v1'
TERMINAL_PHASES={'final','final_answer'}
REVIEW_CORRECTION_PINS={
 'request':'9d1502dafb2170235ab2668e5a05c27ebbcb76726194eb942bcd57e31853afc2',
 'decision':'5c8da1cdd54d2f50600e6a01c0e33c9add656302ba30ad38089b399a6e51f472',
 'input':'a3be54f0057f1d415b93ad03ec30cc99737987b2e9f5add0ddae1304d7ce1e25',
 'reservation':'520b7b85c6fb2ca71fd421e897f93cfee81abda9938412b95d63d40a333ad874',
 'attempt':'ddb41cc6f905e2fe354314ca3cbf8339f976a4eaacdee0ef049d1da11fa6e651',
 'proposal':'58f57a98cd688d77bbbdba90e7221271cb35aba9967a03358f887a6fc3c71581',
 'log':'a8831a7f35d79488cd6422ebf6bca51d7b94d592398542e2e04f85713dd9ae67',
}


def same_committed(path,commit):
    original_bytes=original.old.git('show',commit+':'+path).replace(b'\r\n',b'\n')
    if original_bytes!=(ROOT/path).read_bytes().replace(b'\r\n',b'\n'):
        reject('continuation-code-drift')


def verify_historical_code():
    for path in (original.CODE,original.RUNBOOK_NAME,'scripts/knowledge_local_execution.py',
                 'scripts/knowledge_coverage_gate.py','schemas/knowledge-coverage-gate.v1.schema.json',
                 original.sol.CODE,original.sol.METHOD_NAME):
        same_committed(path,ORIGINAL_COMMIT)
    original.execution.verify_sol_high_dependencies()
    original.execution.verify_historical_dependencies()


def verify_current_code(commit):
    if original.old.git('rev-parse','HEAD').decode().strip()!=commit:
        reject('continuation-code-commit-mismatch')
    for path in (CODE,RUNBOOK):same_committed(path,commit)


def load_context(directory,packet,partition,history,seed,continuation_directory):
    files={name:read(directory/name) for name in PINS}
    for name,pin in PINS.items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=pin:
            reject('continuation-original-artifact-drift')
    if any((directory/(REVIEW+'.'+suffix+'.json')).exists() for suffix in ('proposal','receipt')):
        reject('continuation-original-review-not-empty')
    first={key:files['knowledge_extraction.'+key+'.json'] for key in ('input','proposal','ledger','gate','receipt')}
    return {'files':files,'first':first,'request':files['decision-request.json'],
            'decision':files['approved-decision.json'],'reviewInput':files[REVIEW+'.input.json'],
            'packet':packet,'partition':partition,'history':history,'seed':seed,
            'continuationDirectory':str(continuation_directory.resolve())}


def legacy_input(name,ctx,prior):
    req=ctx['request'];pin=digest(ctx['decision']);packet=ctx['packet'];partition=ctx['partition']
    value=original.old.stage_input_value(name,req,pin,packet,partition,[],
                original.RUNBOOK.read_text(encoding='utf-8-sig'))
    baseline=original.baseline_value(ctx['history'])
    value.update(schema=original.STAGE_SCHEMA,profile=read(original.remediation.PROFILE),
                 outputSchema=read(original.private.SCHEMA),baseline=baseline,
                 baselineSha256=digest(baseline),baselineHistorySha256=digest(ctx['history']),
                 seed=copy.deepcopy(ctx['seed']),seedSha256=digest(ctx['seed']),
                 gateBinding=original.gate_binding(ctx['first'],packet,partition,ctx['history'],ctx['seed'],req) if prior else {},
                 extractionEvidence={'ledger':copy.deepcopy(ctx['first']['ledger']),
                                     'gateResult':copy.deepcopy(ctx['first']['gate'])} if prior else {},
                 priorOutputs=[x['proposal']['output'] for x in prior],
                 priorRemediations=[x['proposal'] for x in prior],
                 priorReceiptSha256=[x['receipt']['receiptSha256'] for x in prior])
    return value


def validate_original(ctx):
    verify_historical_code()
    req=ctx['request'];decision=ctx['decision'];packet=ctx['packet'];partition=ctx['partition']
    history=ctx['history'];seed=ctx['seed'];first=ctx['first']
    if (req['codeCommit']!=ORIGINAL_COMMIT or req['runnerLfSha256']!=original.old.assembly.lf_sha(ROOT/original.CODE)
        or req['maxFreshWorkers']!=3 or req['stages']!=list(original.old.STAGES)
        or req['packetSha256']!=packet['packetSha256'] or req['partitionFileSha256']!=digest(partition)
        or req['seedSha256']!=digest(seed) or req['baselineHistorySha256']!=digest(history)
        or req['baselineDecisionSha256']!=digest(history['decision'])
        or req['baselineReceiptSha256']!=[x['receipt']['receiptSha256'] for x in history['stages']]):
        reject('continuation-original-scope-mismatch')
    adapted={**decision,'schema':'al-isabah.knowledge-local-trial-decision.v1'}
    original.old.check_decision(adapted,digest(adapted),req)
    baseline=original.validate_baseline(history,packet,partition,req['baselineHistorySha256'],
                                        req['baselineReportSha256'],req['baselineOutputSha256'])
    original.validate_seed(seed,packet,read(original.remediation.PROFILE),baseline,
                           history['report'],req['seedSha256'])
    if (first['input']!=legacy_input(original.old.STAGES[0],ctx,[])
        or ctx['reviewInput']!=legacy_input(REVIEW,ctx,[first])):
        reject('continuation-original-stage-drift')
    binding=original.gate_binding(first,packet,partition,history,seed,req)
    original.validate_receipt(first['receipt'],first['input'],first['proposal'],packet,
                              digest(decision),[],binding,first['ledger'],first['gate'])
    return binding


def failed_launch(ctx,log):
    if hashlib.sha256(log.read_bytes()).hexdigest()!=FAILED_LOG_SHA:
        reject('continuation-failed-log-drift')
    task=ctx['first']['receipt']['task'];parent=task['observed']['sessionId']
    worker={'request':ctx['request']['workerRequest'],
            'observed':original.old.host_runtime.observe_session(log,FAILED_SESSION,FAILED_TURN,
                         expected_parent_session_id=parent)}
    _,config=original.sol.configuration()
    if original.old.host_runtime.launch_errors(worker,config,'codex-worker'):
        reject('continuation-failed-host-mismatch')
    completed=[];final=[]
    try:
        with log.open(encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line);payload=row.get('payload',{})
                if row.get('type')=='event_msg' and payload.get('type')=='task_complete':completed.append(payload)
                if (row.get('type')=='response_item' and payload.get('type')=='message'
                    and payload.get('role')=='assistant' and payload.get('phase') in TERMINAL_PHASES):
                    final.append(payload)
    except (OSError,ValueError,TypeError,AttributeError):
        reject('continuation-failed-log-drift')
    if (len(completed)!=1 or completed[0].get('turn_id')!=FAILED_TURN
        or completed[0].get('error',{}).get('message')!=FAILED_ERROR or final):
        reject('continuation-failure-not-proven')
    if (worker['observed']['sessionId']==ctx['first']['receipt']['worker']['observed']['sessionId']
        or worker['observed']['sessionId'] in original.baseline_value(ctx['history'])['historicalWorkerSessionIds']):
        reject('continuation-reused-session')
    return {'schema':'al-isabah.knowledge-gated-continuation-failed-launch.v1',
            'stage':REVIEW,'status':'failed_capacity','logSha256':FAILED_LOG_SHA,
            'taskSessionId':parent,'worker':worker,'noProposalOrReceipt':True}


def request(ctx,log,commit,preview=False):
    if not preview:verify_current_code(commit)
    binding=validate_original(ctx);failed=failed_launch(ctx,log);first=ctx['first'];req=ctx['request']
    return {'schema':REQUEST_SCHEMA if not preview else 'al-isabah.knowledge-gated-continuation-preview.v1',
            'issue':89,'action':'replace_failed_review_then_adjudicate',
            'codeCommit':commit if not preview else 'PENDING_REVIEWED_COMMIT',
            'continuationCodeLfSha256':original.old.assembly.lf_sha(ROOT/CODE),
            'continuationRunbookLfSha256':original.old.assembly.lf_sha(ROOT/RUNBOOK),
            'originalCodeCommit':ORIGINAL_COMMIT,'originalRequestSha256':digest(req),
            'continuationDirectory':ctx['continuationDirectory'],
            'originalDecisionSha256':digest(ctx['decision']),
            'originalExtractionInputSha256':digest(first['input']),
            'originalExtractionProposalSha256':digest(first['proposal']),
            'originalExtractionLedgerSha256':digest(first['ledger']),
            'originalExtractionGateSha256':digest(first['gate']),
            'originalExtractionReceiptSha256':digest(first['receipt']),
            'originalReviewInputSha256':digest(ctx['reviewInput']),
            'baselineHistorySha256':req['baselineHistorySha256'],
            'sourceArtifactSha256':req['sourceArtifactSha256'],'packetSha256':req['packetSha256'],
            'partitionFileSha256':req['partitionFileSha256'],'profileSha256':req['profileSha256'],
            'seedSha256':req['seedSha256'],'gateBinding':binding,
            'failedLaunch':failed,'failedLaunchSha256':digest(failed),
            'priorWorkerSessionIds':[first['receipt']['worker']['observed']['sessionId'],FAILED_SESSION],
            'maxAdditionalWorkerLaunches':2,'maxTotalWorkerLaunches':4,
            'stageSlotPolicy':'reserve_once_before_dispatch_bind_once_after_launch',
            'remainingStages':[REVIEW,ADJUDICATION],
            'taskRequest':req['taskRequest'],'workerRequest':req['workerRequest'],
            'noExtractionRerun':True,'automaticRetryAuthorized':False,
            'humanReview':'unreviewed','consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False}


def authorize(ctx,log,commit,decision,pin):
    if digest(decision)!=pin or decision.get('schema')!=DECISION_SCHEMA:
        reject('continuation-exact-decision-required')
    if 'repair' in ctx:
        repair=validate_repair(ctx,log,commit,decision,pin)
        return decision['request']
    adapted={**decision,'schema':'al-isabah.knowledge-local-trial-decision.v1'}
    return original.old.check_decision(adapted,digest(adapted),request(ctx,log,commit))


def attempts(ctx,req,review=None):
    first=ctx['first']['receipt']['worker']['observed']
    rows=[{'stage':original.old.STAGES[0],'status':'completed','sessionId':first['sessionId'],
           'turnId':first['turnId'],'receiptSha256':ctx['first']['receipt']['receiptSha256']},
          {'stage':REVIEW,'status':'failed_capacity','sessionId':FAILED_SESSION,
           'turnId':FAILED_TURN,'failedLaunchSha256':req['failedLaunchSha256']}]
    if review is not None:
        observed=review['receipt']['worker']['observed']
        row={'stage':REVIEW,'status':'completed','sessionId':observed['sessionId'],
                     'turnId':observed['turnId'],'reservationSha256':digest(review['reservation']),
                     'attemptSha256':digest(review['attempt']),
                     'receiptSha256':review['receipt']['receiptSha256']}
        if 'repair' in ctx:row.update(originalAttemptStatus='unknown',executionRepairSha256=ctx['repairPin'])
        rows.append(row)
    return rows


def require_directory(directory,ctx):
    if str(directory.resolve())!=ctx['continuationDirectory']:
        reject('continuation-directory-mismatch')


def prepare(name,ctx,log,commit,decision,pin,review=None):
    req=authorize(ctx,log,commit,decision,pin)
    if name==REVIEW and review is not None or name==ADJUDICATION and review is None or name not in (REVIEW,ADJUDICATION):
        reject('continuation-stage-order-mismatch')
    first=ctx['first'];packet=ctx['packet']
    if review is not None:
        expected=prepare(REVIEW,ctx,log,commit,decision,pin)
        if review['input']!=expected:reject('continuation-review-input-drift')
        validate_receipt(REVIEW,review,ctx,log,commit,decision,pin)
        value=original.old.stage_input_value(name,ctx['request'],pin,packet,ctx['partition'],[],
                    (ROOT/RUNBOOK).read_text(encoding='utf-8-sig'))
        value.update(schema=STAGE_SCHEMA,profile=read(original.remediation.PROFILE),
                     outputSchema=read(original.private.SCHEMA),baseline=copy.deepcopy(first['input']['baseline']),
                     baselineSha256=first['input']['baselineSha256'],
                     baselineHistorySha256=first['input']['baselineHistorySha256'],
                     seed=copy.deepcopy(ctx['seed']),seedSha256=digest(ctx['seed']),
                     gateBinding=copy.deepcopy(req['gateBinding']),
                     extractionEvidence=copy.deepcopy(ctx['reviewInput']['extractionEvidence']),
                     priorOutputs=[first['proposal']['output'],review['proposal']['output']],
                     priorRemediations=[first['proposal'],review['proposal']],
                     priorReceiptSha256=[first['receipt']['receiptSha256'],review['receipt']['receiptSha256']])
    else:
        if 'repair' in ctx:return read(Path(ctx['continuationDirectory'])/(REVIEW+'.input.json'))
        value=copy.deepcopy(ctx['reviewInput'])
        value.update(schema=STAGE_SCHEMA,decisionSha256=pin,
                     instructions=(ROOT/RUNBOOK).read_text(encoding='utf-8-sig'))
    value.update(continuationRequestSha256=digest(req),originalDecisionSha256=digest(ctx['decision']),
                 continuationDirectory=ctx['continuationDirectory'],
                 failedLaunch=copy.deepcopy(req['failedLaunch']),launchAttempts=attempts(ctx,req,review),
                 maxAdditionalWorkerLaunches=2,maxTotalWorkerLaunches=4)
    if 'repair' in ctx:
        value.update(executionRepairSha256=ctx['repairPin'],executionRepairCodeCommit=commit,
                     originalUserScopeDecisionSha256=pin)
    return value


def final_evidence(ctx,stage,proposal,ledger,req):
    return original.final_reconciliation(ctx['packet'],ctx['partition'],ctx['history'],ctx['seed'],
                                         stage,proposal,ledger,ctx['request'],req['gateBinding'])


def reservation(name,ctx,log,commit,decision,pin,review=None):
    stage=prepare(name,ctx,log,commit,decision,pin,review)
    prior=attempts(ctx,decision['request'],review)
    if len(prior) not in (2,3) or len(prior)+1>decision['request']['maxTotalWorkerLaunches']:
        reject('continuation-worker-budget-or-reuse')
    return {'schema':'al-isabah.knowledge-gated-continuation-reservation.v1',
            'stage':name,'slotNumber':len(prior)+1,'stageInputSha256':digest(stage),
            'continuationDirectory':ctx['continuationDirectory'],
            'continuationDecisionSha256':pin,'continuationRequestSha256':digest(decision['request']),
            'priorAttemptsSha256':digest(prior),'status':'reserved'}


def write_once(path,value):
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(canonical(value))
    except FileExistsError:reject('continuation-slot-already-consumed')


def reserve_once(directory,name,ctx,log,commit,decision,pin,review=None):
    if 'repair' in ctx and name==REVIEW:reject('continuation-review-launch-already-consumed')
    require_directory(directory,ctx)
    path=directory/(name+'.reservation.json')
    if path.exists():reject('continuation-slot-already-consumed')
    value=reservation(name,ctx,log,commit,decision,pin,review)
    if read(directory/(name+'.input.json'))!=prepare(name,ctx,log,commit,decision,pin,review):
        reject('continuation-stage-input-drift')
    write_once(path,value)
    return value


def terminal_result(raw,turn):
    completed=[];final=[]
    try:
        for position,line in enumerate(raw.decode('utf-8').splitlines()):
            row=json.loads(line);payload=row.get('payload',{})
            if row.get('type')=='event_msg' and payload.get('type')=='task_complete':
                completed.append((position,payload))
            if (row.get('type')=='response_item' and payload.get('type')=='message'
                and payload.get('role')=='assistant' and payload.get('phase') in TERMINAL_PHASES):
                final.append((position,payload['phase']))
    except (UnicodeError,ValueError,TypeError,AttributeError):
        reject('continuation-attempt-log-drift')
    if len(completed)>1 or completed and completed[0][1].get('turn_id')!=turn:
        reject('continuation-attempt-log-drift')
    if completed and completed[0][1].get('error'):
        error=completed[0][1]['error']
        return ('failed_capacity' if isinstance(error,dict) and error.get('message')==FAILED_ERROR
                else 'failed_other'),None
    prior_final=[phase for position,phase in final if completed and position<completed[0][0]]
    if completed and prior_final:return 'completed',prior_final[-1]
    return 'unknown',None


def review_correction_preview(ctx,directory,worker_log):
    """Link a saved unknown attempt to host success without changing its bytes."""
    validate_original(ctx)
    names={'request':'decision-request.json','decision':'approved-decision.json',
           'input':REVIEW+'.input.json','reservation':REVIEW+'.reservation.json',
           'attempt':REVIEW+'.attempt.json','proposal':REVIEW+'.proposal.json'}
    files={key:read(directory/name) for key,name in names.items()}
    for key,name in names.items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=REVIEW_CORRECTION_PINS[key]:
            reject('continuation-correction-pin-mismatch')
    try:raw=worker_log.read_bytes()
    except OSError:reject('continuation-correction-log-unavailable')
    if hashlib.sha256(raw).hexdigest()!=REVIEW_CORRECTION_PINS['log']:
        reject('continuation-correction-pin-mismatch')
    req=files['request'];decision=files['decision'];stage=files['input']
    reserved=files['reservation'];attempt=files['attempt'];proposal=files['proposal']
    adapted={**decision,'schema':'al-isabah.knowledge-local-trial-decision.v1'}
    original.old.check_decision(adapted,digest(adapted),req)
    if (req['codeCommit']!='358f65c3413a60811f298165eeb46da6d9c9919e'
        or req['continuationDirectory']!=str(directory.resolve())
        or req['continuationCodeLfSha256']!=hashlib.sha256(
            original.old.git('show',req['codeCommit']+':'+CODE).replace(b'\r\n',b'\n')).hexdigest()
        or stage['decisionSha256']!=digest(decision)
        or stage['continuationRequestSha256']!=digest(req)
        or reserved['stageInputSha256']!=digest(stage)
        or reserved['continuationDecisionSha256']!=digest(decision)
        or reserved['continuationDirectory']!=str(directory.resolve())
        or attempt['reservationSha256']!=digest(reserved)
        or attempt['continuationDecisionSha256']!=digest(decision)
        or attempt['status']!='unknown' or attempt['logSha256']!=REVIEW_CORRECTION_PINS['log']
        or Path(attempt['logPath']).resolve()!=worker_log.resolve()
        or attempt['stage']!=REVIEW):
        reject('continuation-correction-scope-mismatch')
    observed=attempt['worker']['observed']
    actual=original.old.host_runtime.observe_session(worker_log,observed['sessionId'],
                 observed['turnId'],expected_parent_session_id=req['failedLaunch']['taskSessionId'])
    if actual!=observed or attempt['worker']['request']!=req['workerRequest']:
        reject('continuation-correction-host-mismatch')
    status,phase=terminal_result(raw,observed['turnId'])
    if (status!='completed' or phase!='final_answer'
        or observed['sessionId']!='01a0ee75-aa6f-7401-8f09-51fa46df83d6'):
        reject('continuation-correction-not-proven')
    original.remediation.validate_proposal(proposal,stage,ctx['packet'])
    reclassified={**attempt,'status':'completed'}
    return {'schema':'al-isabah.knowledge-gated-continuation-correction-preview.v1',
            'originalCodeCommit':req['codeCommit'],'requestSha256':digest(req),
            'decisionSha256':digest(decision),'inputSha256':digest(stage),
            'reservationSha256':digest(reserved),'originalUnknownAttemptSha256':digest(attempt),
            'proposalSha256':digest(proposal),'logSha256':hashlib.sha256(raw).hexdigest(),
            'workerSessionId':observed['sessionId'],'workerTurnId':observed['turnId'],
            'hostTerminalPhase':phase,'hostTerminalStatus':status,
            'reclassifiedAttemptSha256':digest(reclassified),
            'correctionCodeLfSha256':original.old.assembly.lf_sha(ROOT/CODE),
            'correctionCodeCommit':'PENDING_REVIEWED_COMMIT',
            'authorizable':False,'newWorkerLaunches':0,'consumerAdmissionAuthorized':False,
            'publicReleaseAuthorized':False}


def repair_document(ctx,log,commit,decision,pin):
    """Construct an unreviewed engineering record from fixed historical evidence."""
    directory=Path(ctx['continuationDirectory'])
    attempt=read(directory/(REVIEW+'.attempt.json'))
    evidence=review_correction_preview(ctx,directory,Path(attempt['logPath']))
    failed=failed_launch(ctx,log)
    if (pin!=REVIEW_CORRECTION_PINS['decision'] or digest(decision)!=pin
        or decision!=read(directory/'approved-decision.json')
        or digest(decision['request'])!=REVIEW_CORRECTION_PINS['request']
        or decision['request']['failedLaunch']!=failed
        or decision['request']['remainingStages']!=[REVIEW,ADJUDICATION]
        or decision['request']['maxAdditionalWorkerLaunches']!=2
        or decision['request']['maxTotalWorkerLaunches']!=4):
        reject('continuation-repair-user-scope-mismatch')
    verify_current_code(commit)
    original_commit=decision['request']['codeCommit']
    for path,field in ((CODE,'continuationCodeLfSha256'),(RUNBOOK,'continuationRunbookLfSha256')):
        historical=original.old.git('show',original_commit+':'+path).replace(b'\r\n',b'\n')
        if hashlib.sha256(historical).hexdigest()!=decision['request'][field]:
            reject('continuation-repair-historical-code-drift')
    return {'schema':REPAIR_SCHEMA,'issue':89,'purpose':'historical_review_terminal_interpretation',
            'origin':{'kind':'trusted_coordinator_engineering_review'},'status':'pending_review',
            'originalUserRequestSha256':evidence['requestSha256'],
            'originalUserDecisionSha256':pin,'originalCodeCommit':original_commit,
            'correctedCodeCommit':commit,
            'correctedCodeLfSha256':original.old.assembly.lf_sha(ROOT/CODE),
            'correctedRunbookLfSha256':original.old.assembly.lf_sha(ROOT/RUNBOOK),
            'continuationDirectory':ctx['continuationDirectory'],
            'reviewInputSha256':evidence['inputSha256'],
            'reviewProposalSha256':evidence['proposalSha256'],
            'reviewReservationSha256':evidence['reservationSha256'],
            'reviewUnknownAttemptSha256':evidence['originalUnknownAttemptSha256'],
            'reviewLogSha256':evidence['logSha256'],
            'reviewSessionId':evidence['workerSessionId'],
            'reviewTurnId':evidence['workerTurnId'],
            'observedTerminalStatus':evidence['hostTerminalStatus'],
            'observedTerminalPhase':evidence['hostTerminalPhase'],
            'correctedInterpretationSha256':evidence['reclassifiedAttemptSha256'],
            'remainingStage':ADJUDICATION,'remainingSlotNumber':4,
            'newReviewWorkerLaunches':0,'maxTotalWorkerLaunches':4,
            'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False}


def validate_repair(ctx,log,commit,decision,pin):
    record=ctx['repair']
    if digest(record)!=ctx.get('repairPin'):
        reject('continuation-repair-pin-mismatch')
    expected=repair_document(ctx,log,commit,decision,pin)
    expected['status']='reviewed'
    if record!=expected:
        reject('continuation-repair-not-reviewed-or-drift')
    return record


def bind_attempt(name,reserved,worker_log,session,turn,ctx,log,commit,decision,pin,review=None):
    if reserved!=reservation(name,ctx,log,commit,decision,pin,review):
        reject('continuation-reservation-mismatch')
    task=ctx['first']['receipt']['task']
    worker={'request':ctx['request']['workerRequest'],
            'observed':original.old.host_runtime.observe_session(worker_log,session,turn,
                       expected_parent_session_id=task['observed']['sessionId'])}
    _,config=original.sol.configuration()
    if original.old.host_runtime.launch_errors(worker,config,'codex-worker'):
        reject('continuation-host-mismatch')
    stage=prepare(name,ctx,log,commit,decision,pin,review)
    prior=attempts(ctx,decision['request'],review)
    used={x['sessionId'] for x in prior}|set(stage['baseline']['historicalWorkerSessionIds'])
    if session in used:reject('continuation-worker-budget-or-reuse')
    try:
        raw=worker_log.read_bytes()
    except OSError:
        reject('continuation-attempt-log-drift')
    status,_=terminal_result(raw,turn)
    return {'schema':'al-isabah.knowledge-gated-continuation-attempt.v1','stage':name,
            'reservationSha256':digest(reserved),'continuationDecisionSha256':pin,
            'priorAttemptsSha256':digest(prior),'worker':worker,
            'logPath':str(worker_log.resolve()),'logSha256':hashlib.sha256(raw).hexdigest(),
            'status':status}


def bind_once(directory,name,worker_log,session,turn,ctx,log,commit,decision,pin,review=None):
    if 'repair' in ctx and name==REVIEW:reject('continuation-review-launch-already-consumed')
    require_directory(directory,ctx)
    path=directory/(name+'.attempt.json')
    if path.exists():reject('continuation-slot-already-consumed')
    value=bind_attempt(name,read(directory/(name+'.reservation.json')),worker_log,session,turn,
                       ctx,log,commit,decision,pin,review)
    write_once(path,value)
    return value


def validate_slot(item,name,ctx,log,commit,decision,pin,review=None):
    if 'repair' in ctx and name==REVIEW:
        repair=validate_repair(ctx,log,commit,decision,pin)
        if (digest(item['input'])!=repair['reviewInputSha256']
            or digest(item['proposal'])!=repair['reviewProposalSha256']
            or digest(item['reservation'])!=repair['reviewReservationSha256']
            or digest(item['attempt'])!=repair['reviewUnknownAttemptSha256']):
            reject('continuation-repair-review-evidence-drift')
        return item['attempt']['worker']
    reserved=item['reservation'];attempt=item['attempt']
    if reserved!=reservation(name,ctx,log,commit,decision,pin,review):
        reject('continuation-reservation-mismatch')
    observed=attempt['worker']['observed']
    expected=bind_attempt(name,reserved,Path(attempt['logPath']),observed['sessionId'],
                          observed['turnId'],ctx,log,commit,decision,pin,review)
    if attempt!=expected or attempt['status']!='completed':
        reject('continuation-attempt-not-completed')
    return attempt['worker']


def capture(name,item,ctx,log,commit,decision,pin,worker,review=None):
    stage=prepare(name,ctx,log,commit,decision,pin,review)
    if item['input']!=stage:reject('continuation-stage-input-drift')
    req=decision['request'];proposal=item['proposal'];prior=[ctx['first']['receipt']]
    if review is not None:prior.append(review['receipt'])
    prior_attempts=attempts(ctx,req,review)
    used={x['sessionId'] for x in prior_attempts}|set(stage['baseline']['historicalWorkerSessionIds'])
    if (worker['observed']['sessionId'] in used
        or len(prior_attempts)+1>req['maxTotalWorkerLaunches']
        or len(prior_attempts)-2+1>req['maxAdditionalWorkerLaunches']):
        reject('continuation-worker-budget-or-reuse')
    if worker!=validate_slot(item,name,ctx,log,commit,decision,pin,review):
        reject('continuation-attempt-worker-mismatch')
    if name==ADJUDICATION:
        if set(item)!={'input','proposal','ledger','gate','reservation','attempt','receipt'}:
            reject('continuation-final-evidence-required')
        evidence=final_evidence(ctx,stage,proposal,item['ledger'],req)
        if item['gate']!=evidence:reject('continuation-final-evidence-mismatch')
    elif set(item)!={'input','proposal','reservation','attempt','receipt'}:
        reject('continuation-review-shape-mismatch')
    task=ctx['first']['receipt']['task']
    base=original.sol.capture(stage,proposal,ctx['packet'],pin,task,worker,prior)
    value={**base,'schema':RECEIPT_SCHEMA,'continuationDecisionSha256':pin,
           'originalDecisionSha256':digest(ctx['decision']),
           'failedLaunchSha256':req['failedLaunchSha256'],
           'launchAttemptsSha256':digest(attempts(ctx,req,review)),
           'reservationSha256':digest(item['reservation']),
           'workerAttemptSha256':digest(item['attempt']),
           'extractionReceiptSha256':ctx['first']['receipt']['receiptSha256'],
           'finalLedgerSha256':digest(item['ledger']) if name==ADJUDICATION else '',
           'finalReconciliationSha256':digest(item['gate']) if name==ADJUDICATION else ''}
    if 'repair' in ctx:
        value.update(executionRepairSha256=ctx['repairPin'],
                     executionRepairCodeCommit=commit,originalUserScopeDecisionSha256=pin)
        if name==REVIEW:
            value.update(originalUnknownAttemptSha256=digest(item['attempt']),
                         correctedInterpretationSha256=ctx['repair']['correctedInterpretationSha256'],
                         hostTerminalPhase='final_answer')
    value['checkpointSha256']=original.old.receipt_checkpoint(value)
    value['receiptSha256']=digest({k:v for k,v in value.items() if k!='receiptSha256'})
    return value


def validate_receipt(name,item,ctx,log,commit,decision,pin,review=None):
    if not isinstance(item.get('receipt'),dict):reject('continuation-receipt-required')
    expected=capture(name,item,ctx,log,commit,decision,pin,item['receipt']['worker'],review)
    if item['receipt']!=expected:reject('continuation-receipt-mismatch')
    return expected


def report(ctx,log,commit,decision,pin,review,adjudication):
    req=authorize(ctx,log,commit,decision,pin)
    if review['input']!=prepare(REVIEW,ctx,log,commit,decision,pin):reject('continuation-review-input-drift')
    validate_receipt(REVIEW,review,ctx,log,commit,decision,pin)
    if adjudication['input']!=prepare(ADJUDICATION,ctx,log,commit,decision,pin,review):
        reject('continuation-adjudication-input-drift')
    validate_receipt(ADJUDICATION,adjudication,ctx,log,commit,decision,pin,review)
    final=final_evidence(ctx,adjudication['input'],adjudication['proposal'],adjudication['ledger'],req)
    if adjudication['gate']!=final:reject('continuation-final-evidence-mismatch')
    launches=attempts(ctx,req,review)+[{'stage':ADJUDICATION,'status':'completed',
       'sessionId':adjudication['receipt']['worker']['observed']['sessionId'],
       'turnId':adjudication['receipt']['worker']['observed']['turnId'],
       'reservationSha256':digest(adjudication['reservation']),
       'attemptSha256':digest(adjudication['attempt']),
       'receiptSha256':adjudication['receipt']['receiptSha256']}]
    if len(launches)!=4 or len({x['sessionId'] for x in launches})!=4:
        reject('continuation-worker-budget-or-reuse')
    return {'schema':'al-isabah.knowledge-gated-continuation-validation.v1','status':'partial',
            'originalRequestSha256':req['originalRequestSha256'],
            'originalDecisionSha256':req['originalDecisionSha256'],
            'continuationRequestSha256':digest(req),'continuationDecisionSha256':pin,
            'failedLaunchSha256':req['failedLaunchSha256'],'launchAttempts':launches,
            'extractionGateStatus':ctx['first']['gate']['status'],
            'finalKnownCoverageStatus':final['status'],
            'finalMaterialObligationIds':final['materialObligationIds'],
            'finalReconciliationSha256':digest(final),
            'humanReview':'unreviewed','exhaustiveCoverage':False,
            'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False,
            **({'executionRepairSha256':ctx['repairPin'],'executionRepairCodeCommit':commit,
                'originalUserScopeDecisionSha256':pin} if 'repair' in ctx else {})}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('preview','request','correction-preview','repair-preview','prepare','reserve','bind','final-gate','capture','report'))
    p.add_argument('--original-directory',type=Path,required=True)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--history',type=Path,required=True)
    p.add_argument('--seed',type=Path,required=True)
    p.add_argument('--failed-log',type=Path,required=True)
    p.add_argument('--packet',type=Path,default=original.old.assembly.DEFAULT_PACKET)
    p.add_argument('--partition',type=Path,default=original.old.assembly.DEFAULT_METADATA)
    p.add_argument('--decision',type=Path);p.add_argument('--decision-sha256')
    p.add_argument('--repair-record',type=Path);p.add_argument('--repair-sha256')
    p.add_argument('--stage',choices=(REVIEW,ADJUDICATION))
    p.add_argument('--correction-output',type=Path)
    p.add_argument('--worker-log',type=Path);p.add_argument('--worker-session');p.add_argument('--worker-turn')
    args=p.parse_args()
    try:
        original.old.require_runtime_directory(args.directory)
        if (args.directory.resolve()==args.original_directory.resolve()
            or args.directory.resolve().is_relative_to(args.original_directory.resolve())
            or args.original_directory.resolve().is_relative_to(args.directory.resolve())):
            reject('continuation-separate-directory-required')
        ctx=load_context(args.original_directory,read(args.packet),read(args.partition),
                         read(args.history),read(args.seed),args.directory)
        require_directory(args.directory,ctx)
        commit=original.old.git('rev-parse','HEAD').decode().strip()
        if args.action in ('preview','request'):
            value=request(ctx,args.failed_log,commit,args.action=='preview')
            name='request-preview.json' if args.action=='preview' else 'decision-request.json'
            original.old.write_new(args.directory/name,value);print(digest(value));return 0
        if args.action=='correction-preview':
            if not args.worker_log or not args.correction_output:
                reject('continuation-correction-paths-required')
            original.old.require_runtime_directory(args.correction_output.parent)
            if args.correction_output.parent.resolve()==args.directory.resolve():
                reject('continuation-correction-separate-output-required')
            value=review_correction_preview(ctx,args.directory,args.worker_log)
            original.old.write_new(args.correction_output,value);print(digest(value));return 0
        if not args.decision or not args.decision_sha256:reject('continuation-exact-decision-required')
        decision=read(args.decision);pin=args.decision_sha256
        if args.action=='repair-preview':
            if not args.correction_output:reject('continuation-correction-paths-required')
            original.old.require_runtime_directory(args.correction_output.parent)
            if args.correction_output.parent.resolve()==args.directory.resolve():
                reject('continuation-correction-separate-output-required')
            value=repair_document(ctx,args.failed_log,commit,decision,pin)
            original.old.write_new(args.correction_output,value);print(digest(value));return 0
        if bool(args.repair_record)!=bool(args.repair_sha256):reject('continuation-repair-pin-required')
        if args.repair_record:
            if args.repair_record.resolve().parent==args.directory.resolve():
                reject('continuation-repair-separate-record-required')
            ctx['repair']=read(args.repair_record);ctx['repairPin']=args.repair_sha256
        if args.action=='prepare':
            if not args.stage:reject('continuation-stage-required')
            review={k:read(args.directory/(REVIEW+'.'+k+'.json')) for k in ('input','proposal','reservation','attempt','receipt')} if args.stage==ADJUDICATION else None
            value=prepare(args.stage,ctx,args.failed_log,commit,decision,pin,review)
            original.old.write_new(args.directory/(args.stage+'.input.json'),value);print(digest(value));return 0
        if args.action=='report':
            review={k:read(args.directory/(REVIEW+'.'+k+'.json')) for k in ('input','proposal','reservation','attempt','receipt')}
            adjudication={k:read(args.directory/(ADJUDICATION+'.'+k+'.json')) for k in ('input','proposal','ledger','gate','reservation','attempt','receipt')}
            value=report(ctx,args.failed_log,commit,decision,pin,review,adjudication)
            original.old.write_new(args.directory/'validation-report.json',value);print(digest(value));return 0
        if args.stage!=ADJUDICATION and args.action=='final-gate':reject('continuation-stage-required')
        if not args.stage:reject('continuation-stage-required')
        review={k:read(args.directory/(REVIEW+'.'+k+'.json')) for k in ('input','proposal','reservation','attempt','receipt')} if args.stage==ADJUDICATION else None
        stage=prepare(args.stage,ctx,args.failed_log,commit,decision,pin,review)
        if read(args.directory/(args.stage+'.input.json'))!=stage:reject('continuation-stage-input-drift')
        if args.action=='reserve':
            value=reserve_once(args.directory,args.stage,ctx,args.failed_log,commit,decision,pin,review)
            print(digest(value));return 0
        if args.action=='bind':
            if not all((args.worker_log,args.worker_session,args.worker_turn)):
                reject('continuation-host-inputs-required')
            value=bind_once(args.directory,args.stage,args.worker_log,args.worker_session,args.worker_turn,
                            ctx,args.failed_log,commit,decision,pin,review)
            print(digest(value));return 0
        proposal=read(args.directory/(args.stage+'.proposal.json'))
        if args.action=='final-gate':
            value=final_evidence(ctx,stage,proposal,read(args.directory/(ADJUDICATION+'.ledger.json')),decision['request'])
            original.old.write_new(args.directory/(ADJUDICATION+'.gate.json'),value);print(digest(value));return 0
        if not all((args.worker_log,args.worker_session,args.worker_turn)):
            reject('continuation-host-inputs-required')
        task=ctx['first']['receipt']['task']
        worker={'request':ctx['request']['workerRequest'],
                'observed':original.old.host_runtime.observe_session(args.worker_log,args.worker_session,args.worker_turn,
                          expected_parent_session_id=task['observed']['sessionId'])}
        keys=('input','proposal','ledger','gate','reservation','attempt') if args.stage==ADJUDICATION else ('input','proposal','reservation','attempt')
        item={k:read(args.directory/(args.stage+'.'+k+'.json')) for k in keys}
        item['receipt']=None
        value=capture(args.stage,item,ctx,args.failed_log,commit,decision,pin,worker,review)
        original.old.write_new(args.directory/(args.stage+'.receipt.json'),value);print(value['receiptSha256']);return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError,IndexError,AttributeError):
        print('gated-continuation-operation-rejected');return 1


if __name__=='__main__':raise SystemExit(main())
