"""Replay preserved remediation evidence without changing historical receipts."""
import copy
import hashlib
import knowledge_pilot_trial as old
import knowledge_pilot_remediation as remediation
import knowledge_pilot_validation_v2 as private
from knowledge_export import read,digest,reject

# Supported verifier revision, not an execution authorization.
EXECUTION_COMMIT='e2a898553e41185098f5fbcc30ed60e8a8816231'
HISTORY_SCHEMA='al-isabah.knowledge-local-execution-history.v1'
VERIFIER_PINS=old.ROOT/'profiles/knowledge/local-execution-verifier.v1.json'
VERIFIER_PINS_SHA256='41ef4994a7a1ca7b47c3779653f45eeb7ab95cfad4b32cecfb806d9c57d75e29'


def verify_historical_dependencies():
    pins=read(VERIFIER_PINS)
    if digest(pins)!=VERIFIER_PINS_SHA256 or pins['executionCodeCommit']!=EXECUTION_COMMIT:reject('local-historical-verifier-drift')
    for row in pins['dependencies']:
        raw=(old.ROOT/row['path']).read_bytes().replace(b'\r\n',b'\n')
        if hashlib.sha256(raw).hexdigest()!=row['lfSha256']:reject('local-historical-verifier-drift')


def expected_request(packet,partition,baseline):
    verify_historical_dependencies()
    old.validate_packet(packet,partition)
    remediation.baseline_value(baseline['stages'],baseline['report'],baseline['reportSha256'],packet)
    registry=read(old.method.REGISTRY_PATH)
    return {'schema':'al-isabah.knowledge-remediation-request.v1','fixtureClass':packet.get('fixtureClass','not-a-fixture'),
        'issue':89,'action':'bounded_local_knowledge_remediation','coordinatorThreadId':old.COORDINATOR,'codeCommit':EXECUTION_COMMIT,
        'packetSha256':packet['packetSha256'],'partitionSha256':partition['partitionSha256'],'partitionFileSha256':digest(partition),
        'methodRegistrySha256':digest(registry),'methodId':registry['methods'][0]['methodId'],
        'profileSha256':digest(read(remediation.PROFILE)),'outputSchemaSha256':digest(read(private.SCHEMA)),
        'runbookLfSha256':old.assembly.lf_sha(remediation.RUNBOOK),'sourceOrdinals':partition['sourceOrdinals'],
        'stages':list(old.STAGES),'maxFreshWorkers':3,'taskRequest':old.host_runtime.launch_request('codex-task','gpt-5.6-sol','xhigh'),
        'workerRequest':old.host_runtime.launch_request('codex-worker','gpt-5.6-sol','xhigh'),'provider':'openai',
        'publicReleaseAuthorized':False,'consumerAdmissionAuthorized':False,'baselineSha256':digest(baseline),
        'baselineReportSha256':baseline['reportSha256'],'baselineOutputSha256':digest(remediation.baseline_output(baseline)),
        'baselineConcernIds':sorted(c['id'] for c in remediation.baseline_output(baseline)['concerns'])}


def expected_input(name,request,pin,packet,partition,baseline,prior):
    value=old.stage_input_value(name,request,pin,packet,partition,[],remediation.RUNBOOK.read_text(encoding='utf-8-sig'))
    value.update(schema='al-isabah.knowledge-remediation-stage-input.v1',profile=read(remediation.PROFILE),outputSchema=read(private.SCHEMA),
                 baseline=copy.deepcopy(baseline),baselineSha256=digest(baseline),priorOutputs=[x['proposal']['output'] for x in prior],
                 priorRemediations=[x['proposal'] for x in prior],priorReceiptSha256=[x['receipt']['receiptSha256'] for x in prior])
    return value


def expected_report(decision,packet,partition,baseline,stages):
    req=decision['request']
    return {'schema':'al-isabah.knowledge-remediation-validation.v1','status':stages[-1]['proposal']['output']['status'],
            'fixtureClass':req['fixtureClass'],'codeCommit':req['codeCommit'],'decisionSha256':digest(decision),
            **{k:req[k] for k in ('baselineSha256','baselineReportSha256','baselineOutputSha256','profileSha256','outputSchemaSha256','packetSha256','partitionSha256')},
            'stageProposalSha256':[digest(x['proposal']) for x in stages],'stageReceiptSha256':[x['receipt']['receiptSha256'] for x in stages],
            'concernOutcomes':stages[-1]['proposal']['concernOutcomes'],'humanReview':'unreviewed',
            'publicReleaseAuthorized':False,'consumerAdmissionAuthorized':False}


def validate_history(history):
    if set(history)!={'schema','decision','partition','baseline','stages','report'} or history['schema']!=HISTORY_SCHEMA:reject('local-execution-history-shape')
    stages=history['stages']
    if len(stages)!=3:reject('trial-stage-order-mismatch')
    packet=stages[0]['input']['lockedInput'];partition=history['partition'];baseline=history['baseline'];decision=history['decision']
    if packet.get('fixtureClass','not-a-fixture')!='not-a-fixture':reject('local-execution-fixture-rejected')
    profile=read(remediation.PROFILE)
    if packet['sourceArtifactSha256']!=profile['authority']['sourceArtifactSha256']:reject('source-identity-mismatch')
    request=expected_request(packet,partition,baseline)
    if decision.get('schema')!='al-isabah.knowledge-remediation-decision.v1':reject('remediation-new-decision-required')
    adapted={**decision,'schema':'al-isabah.knowledge-local-trial-decision.v1'}
    old.check_decision(adapted,digest(adapted),request)
    prior=[]
    for name,item in zip(old.STAGES,stages):
        if set(item)!={'input','proposal','receipt'}:reject('local-execution-history-shape')
        expected=expected_input(name,request,digest(decision),packet,partition,baseline,prior)
        if item['input']!=expected:reject('trial-stage-input-drift')
        remediation.validate_proposal(item['proposal'],expected,packet)
        remediation.validate_fresh_worker(item['receipt']['worker'],baseline)
        old.validate_receipt(item['receipt'],expected,item['proposal'],digest(decision),[x['receipt'] for x in prior])
        prior.append(item)
    if history['report']!=expected_report(decision,packet,partition,baseline,stages):reject('local-execution-report-mismatch')
    return packet
