"""Replay a completed gated lineage after HEAD advances; never authorize a launch.

The historical runners remain frozen.  This adapter checks their saved inputs and
reuses their domain, host, gate, and receipt primitives without their current-HEAD
execution admission check.  Callers must supply independently reviewed pins.
"""
import copy
import hashlib
from pathlib import Path

import knowledge_gated_continuation as gated
from knowledge_export import digest,read,reject

SCHEMA='al-isabah.knowledge-local-gated-history.v1'
NORMALIZED='al-isabah.knowledge-local-gated-normalized.v1'


def committed_lf(commit,path):
    return gated.original.old.git('show',commit+':'+path).replace(b'\r\n',b'\n')


def check_code(request,repair):
    old_commit=request['codeCommit'];new_commit=repair['correctedCodeCommit']
    if (old_commit!=repair['originalCodeCommit'] or old_commit==new_commit
        or request['continuationCodeLfSha256']!=hashlib.sha256(committed_lf(old_commit,gated.CODE)).hexdigest()
        or request['continuationRunbookLfSha256']!=hashlib.sha256(committed_lf(old_commit,gated.RUNBOOK)).hexdigest()
        or repair['correctedCodeLfSha256']!=hashlib.sha256(committed_lf(new_commit,gated.CODE)).hexdigest()
        or repair['correctedRunbookLfSha256']!=hashlib.sha256(committed_lf(new_commit,gated.RUNBOOK)).hexdigest()):
        reject('gated-history-code-drift')
    # The imported primitives themselves must still be the reviewed revision.
    for path in (gated.CODE,gated.RUNBOOK):
        if (gated.ROOT/path).read_bytes().replace(b'\r\n',b'\n')!=committed_lf(new_commit,path):
            reject('gated-history-code-drift')
    gated.verify_historical_code()


def review_stage(ctx,request,decision_pin,failed,runbook):
    value=copy.deepcopy(ctx['reviewInput'])
    value.update(schema=gated.STAGE_SCHEMA,decisionSha256=decision_pin,instructions=runbook)
    value.update(continuationRequestSha256=digest(request),originalDecisionSha256=digest(ctx['decision']),
                 continuationDirectory=ctx['continuationDirectory'],failedLaunch=copy.deepcopy(failed),
                 launchAttempts=gated.attempts(ctx,request),maxAdditionalWorkerLaunches=2,maxTotalWorkerLaunches=4)
    return value


def adjudication_stage(ctx,request,decision_pin,review,failed,runbook,repair_pin,commit):
    first=ctx['first']
    value=gated.original.old.stage_input_value(gated.ADJUDICATION,ctx['request'],decision_pin,
                 ctx['packet'],ctx['partition'],[],runbook)
    value.update(schema=gated.STAGE_SCHEMA,profile=read(gated.original.remediation.PROFILE),
                 outputSchema=read(gated.original.private.SCHEMA),
                 baseline=copy.deepcopy(first['input']['baseline']),baselineSha256=first['input']['baselineSha256'],
                 baselineHistorySha256=first['input']['baselineHistorySha256'],seed=copy.deepcopy(ctx['seed']),
                 seedSha256=digest(ctx['seed']),gateBinding=copy.deepcopy(request['gateBinding']),
                 extractionEvidence=copy.deepcopy(ctx['reviewInput']['extractionEvidence']),
                 priorOutputs=[first['proposal']['output'],review['proposal']['output']],
                 priorRemediations=[first['proposal'],review['proposal']],
                 priorReceiptSha256=[first['receipt']['receiptSha256'],review['receipt']['receiptSha256']])
    value.update(continuationRequestSha256=digest(request),originalDecisionSha256=digest(ctx['decision']),
                 continuationDirectory=ctx['continuationDirectory'],failedLaunch=copy.deepcopy(failed),
                 launchAttempts=gated.attempts(ctx,request,review),maxAdditionalWorkerLaunches=2,
                 maxTotalWorkerLaunches=4,executionRepairSha256=repair_pin,
                 executionRepairCodeCommit=commit,originalUserScopeDecisionSha256=decision_pin)
    return value


def reservation(name,stage,ctx,request,pin,review=None):
    prior=gated.attempts(ctx,request,review)
    return {'schema':'al-isabah.knowledge-gated-continuation-reservation.v1',
            'stage':name,'slotNumber':len(prior)+1,'stageInputSha256':digest(stage),
            'continuationDirectory':ctx['continuationDirectory'],
            'continuationDecisionSha256':pin,'continuationRequestSha256':digest(request),
            'priorAttemptsSha256':digest(prior),'status':'reserved'}


def host_attempt(item,name,ctx,request,pin,review=None):
    attempt=item['attempt'];observed=attempt['worker']['observed'];path=Path(attempt['logPath'])
    actual=gated.original.old.host_runtime.observe_session(path,observed['sessionId'],observed['turnId'],
               expected_parent_session_id=ctx['first']['receipt']['task']['observed']['sessionId'])
    _,config=gated.original.sol.configuration()
    if (actual!=observed or attempt['worker']['request']!=request['workerRequest']
        or gated.original.old.host_runtime.launch_errors(attempt['worker'],config,'codex-worker')):
        reject('gated-history-host-mismatch')
    raw=path.read_bytes();status,phase=gated.terminal_result(raw,observed['turnId'])
    prior=gated.attempts(ctx,request,review)
    used={x['sessionId'] for x in prior}|set(item['input']['baseline']['historicalWorkerSessionIds'])
    if observed['sessionId'] in used:reject('gated-history-session-reuse')
    expected={'schema':'al-isabah.knowledge-gated-continuation-attempt.v1','stage':name,
              'reservationSha256':digest(item['reservation']),'continuationDecisionSha256':pin,
              'priorAttemptsSha256':digest(prior),'worker':attempt['worker'],
              'logPath':str(path.resolve()),'logSha256':hashlib.sha256(raw).hexdigest(),
              'status':status}
    return expected,phase


def receipt(name,item,ctx,request,pin,repair,repair_pin,prior):
    stage=item['input'];proposal=item['proposal'];task=ctx['first']['receipt']['task']
    base=gated.original.sol.capture(stage,proposal,ctx['packet'],pin,task,item['attempt']['worker'],prior)
    value={**base,'schema':gated.RECEIPT_SCHEMA,'continuationDecisionSha256':pin,
           'originalDecisionSha256':digest(ctx['decision']),'failedLaunchSha256':request['failedLaunchSha256'],
           'launchAttemptsSha256':digest(gated.attempts(ctx,request,item.get('_review'))),
           'reservationSha256':digest(item['reservation']),'workerAttemptSha256':digest(item['attempt']),
           'extractionReceiptSha256':ctx['first']['receipt']['receiptSha256'],
           'finalLedgerSha256':digest(item['ledger']) if name==gated.ADJUDICATION else '',
           'finalReconciliationSha256':digest(item['gate']) if name==gated.ADJUDICATION else '',
           'executionRepairSha256':repair_pin,'executionRepairCodeCommit':repair['correctedCodeCommit'],
           'originalUserScopeDecisionSha256':pin}
    if name==gated.REVIEW:
        value.update(originalUnknownAttemptSha256=digest(item['attempt']),
                     correctedInterpretationSha256=repair['correctedInterpretationSha256'],
                     hostTerminalPhase='final_answer')
    value['checkpointSha256']=gated.original.old.receipt_checkpoint(value)
    value['receiptSha256']=digest({k:v for k,v in value.items() if k!='receiptSha256'})
    return value


def validate_history(history,pins):
    if set(history)!={'schema','context','failedLogPath','continuationRequest','continuationDecision',
                     'repair','review','adjudication','report'} or history['schema']!=SCHEMA:
        reject('gated-history-shape')
    required={'originalRequestSha256','originalDecisionSha256','continuationRequestSha256',
              'continuationDecisionSha256','repairSha256','reviewUnknownAttemptSha256',
              'finalProposalSha256','finalLedgerSha256','finalGateSha256','finalReportSha256'}
    if set(pins)!=required:reject('gated-history-independent-pins-required')
    ctx=copy.deepcopy(history['context']);log=Path(history['failedLogPath']);req=history['continuationRequest']
    decision=history['continuationDecision'];pin=digest(decision);repair=history['repair'];repair_pin=digest(repair)
    review=history['review'];adj=history['adjudication'];report=history['report']
    if (digest(ctx['request'])!=pins['originalRequestSha256'] or digest(ctx['decision'])!=pins['originalDecisionSha256']
        or digest(req)!=pins['continuationRequestSha256'] or pin!=pins['continuationDecisionSha256']
        or repair_pin!=pins['repairSha256'] or digest(review['attempt'])!=pins['reviewUnknownAttemptSha256']
        or digest(adj['proposal'])!=pins['finalProposalSha256'] or digest(adj['ledger'])!=pins['finalLedgerSha256']
        or digest(adj['gate'])!=pins['finalGateSha256'] or digest(report)!=pins['finalReportSha256']):
        reject('gated-history-independent-pin-mismatch')
    if (ctx['continuationDirectory']!=req['continuationDirectory'] or decision['request']!=req
        or req['maxAdditionalWorkerLaunches']!=2 or req['maxTotalWorkerLaunches']!=4
        or req['remainingStages']!=[gated.REVIEW,gated.ADJUDICATION]
        or repair['status']!='reviewed' or repair['origin']!={'kind':'trusted_coordinator_engineering_review'}):
        reject('gated-history-scope-mismatch')
    check_code(req,repair)
    binding=gated.validate_original(ctx);failed=gated.failed_launch(ctx,log)
    if req['failedLaunch']!=failed or req['gateBinding']!=binding:reject('gated-history-baseline-mismatch')
    historical=committed_lf(req['codeCommit'],gated.RUNBOOK).decode('utf-8-sig')
    preview=gated.request(ctx,log,req['codeCommit'],preview=True)
    preview.update(schema=gated.REQUEST_SCHEMA,codeCommit=req['codeCommit'],
                   continuationCodeLfSha256=req['continuationCodeLfSha256'],
                   continuationRunbookLfSha256=req['continuationRunbookLfSha256'])
    if preview!=req:reject('gated-history-request-drift')
    adapted={**decision,'schema':'al-isabah.knowledge-local-trial-decision.v1'}
    gated.original.old.check_decision(adapted,digest(adapted),req)
    expected_review=review_stage(ctx,req,pin,failed,historical)
    if (set(review)!={'input','proposal','reservation','attempt','receipt'}
        or review['input']!=expected_review
        or review['reservation']!=reservation(gated.REVIEW,expected_review,ctx,req,pin)
        or review['attempt']['status']!='unknown'):
        reject('gated-history-review-drift')
    gated.original.remediation.validate_proposal(review['proposal'],review['input'],ctx['packet'])
    observed=review['attempt']['worker']['observed'];review_log=Path(review['attempt']['logPath'])
    actual=gated.original.old.host_runtime.observe_session(review_log,observed['sessionId'],observed['turnId'],
                expected_parent_session_id=req['failedLaunch']['taskSessionId'])
    _,config=gated.original.sol.configuration()
    raw=review_log.read_bytes();status,phase=gated.terminal_result(raw,observed['turnId'])
    if (actual!=observed or review['attempt']['worker']['request']!=req['workerRequest']
        or gated.original.old.host_runtime.launch_errors(review['attempt']['worker'],config,'codex-worker')
        or status!='completed' or phase!='final_answer'):
        reject('gated-history-review-host-mismatch')
    expected_unknown={'schema':'al-isabah.knowledge-gated-continuation-attempt.v1','stage':gated.REVIEW,
        'reservationSha256':digest(review['reservation']),'continuationDecisionSha256':pin,
        'priorAttemptsSha256':digest(gated.attempts(ctx,req)),'worker':review['attempt']['worker'],
        'logPath':str(review_log.resolve()),'logSha256':hashlib.sha256(raw).hexdigest(),
        'status':'unknown'}
    if review['attempt']!=expected_unknown:reject('gated-history-original-attempt-drift')
    old_attempt={**review['attempt'],'status':'completed'}
    expected_repair={'schema':gated.REPAIR_SCHEMA,'issue':89,
        'purpose':'historical_review_terminal_interpretation',
        'origin':{'kind':'trusted_coordinator_engineering_review'},'status':'reviewed',
        'originalUserRequestSha256':digest(req),'originalUserDecisionSha256':pin,
        'originalCodeCommit':req['codeCommit'],'correctedCodeCommit':repair['correctedCodeCommit'],
        'correctedCodeLfSha256':hashlib.sha256(committed_lf(repair['correctedCodeCommit'],gated.CODE)).hexdigest(),
        'correctedRunbookLfSha256':hashlib.sha256(committed_lf(repair['correctedCodeCommit'],gated.RUNBOOK)).hexdigest(),
        'continuationDirectory':ctx['continuationDirectory'],'reviewInputSha256':digest(review['input']),
        'reviewProposalSha256':digest(review['proposal']),'reviewReservationSha256':digest(review['reservation']),
        'reviewUnknownAttemptSha256':digest(review['attempt']),'reviewLogSha256':hashlib.sha256(raw).hexdigest(),
        'reviewSessionId':observed['sessionId'],'reviewTurnId':observed['turnId'],
        'observedTerminalStatus':'completed','observedTerminalPhase':'final_answer',
        'correctedInterpretationSha256':digest(old_attempt),'remainingStage':gated.ADJUDICATION,
        'remainingSlotNumber':4,'newReviewWorkerLaunches':0,'maxTotalWorkerLaunches':4,
        'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False}
    if repair!=expected_repair:
        reject('gated-history-repair-drift')
    ctx.update(repair=repair,repairPin=repair_pin)
    expected_receipt=receipt(gated.REVIEW,review,ctx,req,pin,repair,repair_pin,[ctx['first']['receipt']])
    if review['receipt']!=expected_receipt:reject('gated-history-review-receipt-drift')
    corrected_runbook=committed_lf(repair['correctedCodeCommit'],gated.RUNBOOK).decode('utf-8-sig')
    stage=adjudication_stage(ctx,req,pin,review,failed,corrected_runbook,repair_pin,repair['correctedCodeCommit'])
    if (set(adj)!={'input','proposal','ledger','gate','reservation','attempt','receipt'}
        or adj['input']!=stage or adj['reservation']!=reservation(gated.ADJUDICATION,stage,ctx,req,pin,review)
        or adj['reservation']['slotNumber']!=4):
        reject('gated-history-adjudication-drift')
    expected_attempt,_=host_attempt(adj,gated.ADJUDICATION,ctx,req,pin,review)
    if adj['attempt']!=expected_attempt or adj['attempt']['status']!='completed':
        reject('gated-history-adjudication-attempt-drift')
    final=gated.final_evidence(ctx,stage,adj['proposal'],adj['ledger'],req)
    if adj['gate']!=final:reject('gated-history-final-gate-drift')
    with_review={**adj,'_review':review}
    expected_receipt=receipt(gated.ADJUDICATION,with_review,ctx,req,pin,repair,repair_pin,
                             [ctx['first']['receipt'],review['receipt']])
    if adj['receipt']!=expected_receipt:reject('gated-history-final-receipt-drift')
    launches=gated.attempts(ctx,req,review)+[{'stage':gated.ADJUDICATION,'status':'completed',
        'sessionId':adj['receipt']['worker']['observed']['sessionId'],
        'turnId':adj['receipt']['worker']['observed']['turnId'],
        'reservationSha256':digest(adj['reservation']),'attemptSha256':digest(adj['attempt']),
        'receiptSha256':adj['receipt']['receiptSha256']}]
    if len(launches)!=4 or len({x['sessionId'] for x in launches})!=4:reject('gated-history-launch-ledger-drift')
    expected_report={'schema':'al-isabah.knowledge-gated-continuation-validation.v1','status':'partial',
        'originalRequestSha256':req['originalRequestSha256'],'originalDecisionSha256':req['originalDecisionSha256'],
        'continuationRequestSha256':digest(req),'continuationDecisionSha256':pin,
        'failedLaunchSha256':req['failedLaunchSha256'],'launchAttempts':launches,
        'extractionGateStatus':ctx['first']['gate']['status'],'finalKnownCoverageStatus':final['status'],
        'finalMaterialObligationIds':final['materialObligationIds'],'finalReconciliationSha256':digest(final),
        'humanReview':'unreviewed','exhaustiveCoverage':False,
        'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False,
        'executionRepairSha256':repair_pin,'executionRepairCodeCommit':repair['correctedCodeCommit'],
        'originalUserScopeDecisionSha256':pin}
    if report!=expected_report:reject('gated-history-report-drift')
    return {'schema':NORMALIZED,'baseline':copy.deepcopy(ctx['history']['baseline']),'partition':copy.deepcopy(ctx['partition']),
            'packet':copy.deepcopy(ctx['packet']),'stages':[copy.deepcopy(ctx['first']),copy.deepcopy(review),copy.deepcopy(adj)],
            'report':copy.deepcopy(report),'stageDecisionSha256':[digest(ctx['decision']),pin,pin],
            'lineageSha256':digest({'originalRequest':ctx['request'],'originalDecision':ctx['decision'],
                                   'failedLaunch':failed,'continuationRequest':req,'continuationDecision':decision,
                                   'repair':repair,'report':report})}
