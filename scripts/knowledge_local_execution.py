"""Replay preserved remediation evidence without changing historical receipts."""
import copy
import hashlib
import knowledge_pilot_trial as old
import knowledge_pilot_remediation as remediation
import knowledge_pilot_remediation_sol_high as sol_high
import knowledge_pilot_validation_v2 as private
from knowledge_export import read,digest,reject

# Supported verifier revision, not an execution authorization.
EXECUTION_COMMIT='e2a898553e41185098f5fbcc30ed60e8a8816231'
SOL_HIGH_COMMIT='dbb54fab19d8e0d7a84d6420e70dc397f6ca1847'
SOL_HIGH_ADAPTER_LF_SHA256='2e2c5da88ea9452a572297338aeebea8148ad228e60d7d7dfe17dc5e9cac7ba1'
SOL_HIGH_METHOD_LF_SHA256='b084811636ad9dfd3608e1c80992dda091f745e0aacc51375d50d143f6a60c0e'
SOL_HIGH_METHOD_SHA256='00f894ae6af96234ddb6c128eea451fbb8c8e24feb56dc746361ec9cd4dcfa41'
HISTORY_SCHEMA='al-isabah.knowledge-local-execution-history.v1'
VERIFIER_PINS=old.ROOT/'profiles/knowledge/local-execution-verifier.v1.json'
VERIFIER_PINS_SHA256='41ef4994a7a1ca7b47c3779653f45eeb7ab95cfad4b32cecfb806d9c57d75e29'


def verify_historical_dependencies():
    pins=read(VERIFIER_PINS)
    if digest(pins)!=VERIFIER_PINS_SHA256 or pins['executionCodeCommit']!=EXECUTION_COMMIT:reject('local-historical-verifier-drift')
    for row in pins['dependencies']:
        raw=(old.ROOT/row['path']).read_bytes().replace(b'\r\n',b'\n')
        if hashlib.sha256(raw).hexdigest()!=row['lfSha256']:reject('local-historical-verifier-drift')


def verify_sol_high_dependencies():
    for path,pin in ((sol_high.CODE,SOL_HIGH_ADAPTER_LF_SHA256),
                     (sol_high.METHOD_NAME,SOL_HIGH_METHOD_LF_SHA256)):
        raw=(old.ROOT/path).read_bytes().replace(b'\r\n',b'\n')
        if hashlib.sha256(raw).hexdigest()!=pin:reject('local-sol-high-verifier-drift')
    if digest(read(sol_high.METHOD))!=SOL_HIGH_METHOD_SHA256:reject('local-sol-high-verifier-drift')


def expected_request(packet,partition,baseline,commit=EXECUTION_COMMIT):
    verify_historical_dependencies()
    if commit not in (EXECUTION_COMMIT,SOL_HIGH_COMMIT):reject('local-execution-code-unsupported')
    if commit==SOL_HIGH_COMMIT:verify_sol_high_dependencies()
    old.validate_packet(packet,partition)
    remediation.baseline_value(baseline['stages'],baseline['report'],baseline['reportSha256'],packet)
    registry=read(old.method.REGISTRY_PATH)
    value={'schema':'al-isabah.knowledge-remediation-request.v1','fixtureClass':packet.get('fixtureClass','not-a-fixture'),
        'issue':89,'action':'bounded_local_knowledge_remediation','coordinatorThreadId':old.COORDINATOR,'codeCommit':commit,
        'packetSha256':packet['packetSha256'],'partitionSha256':partition['partitionSha256'],'partitionFileSha256':digest(partition),
        'methodRegistrySha256':digest(registry),'methodId':registry['methods'][0]['methodId'],
        'profileSha256':digest(read(remediation.PROFILE)),'outputSchemaSha256':digest(read(private.SCHEMA)),
        'runbookLfSha256':old.assembly.lf_sha(remediation.RUNBOOK),'sourceOrdinals':partition['sourceOrdinals'],
        'stages':list(old.STAGES),'maxFreshWorkers':3,'taskRequest':old.host_runtime.launch_request('codex-task','gpt-5.6-sol','xhigh'),
        'workerRequest':old.host_runtime.launch_request('codex-worker','gpt-5.6-sol','xhigh'),'provider':'openai',
        'publicReleaseAuthorized':False,'consumerAdmissionAuthorized':False,'baselineSha256':digest(baseline),
        'baselineReportSha256':baseline['reportSha256'],'baselineOutputSha256':digest(remediation.baseline_output(baseline)),
        'baselineConcernIds':sorted(c['id'] for c in remediation.baseline_output(baseline)['concerns'])}
    if commit==SOL_HIGH_COMMIT:
        method,config=sol_high.configuration()
        value.update(schema=sol_high.REQUEST_SCHEMA,methodRegistrySha256=digest(method),
                     methodId=method['methods'][0]['methodId'],
                     taskRequest=old.host_runtime.launch_request('codex-task',config['model'],config['reasoning']),
                     workerRequest=old.host_runtime.launch_request('codex-worker',config['model'],config['reasoning']))
    return value


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
    commit=decision.get('request',{}).get('codeCommit')
    request=expected_request(packet,partition,baseline,commit)
    decision_schema=sol_high.DECISION_SCHEMA if commit==SOL_HIGH_COMMIT else 'al-isabah.knowledge-remediation-decision.v1'
    if decision.get('schema')!=decision_schema:reject('remediation-new-decision-required')
    adapted={**decision,'schema':'al-isabah.knowledge-local-trial-decision.v1'}
    old.check_decision(adapted,digest(adapted),request)
    prior=[]
    for name,item in zip(old.STAGES,stages):
        if set(item)!={'input','proposal','receipt'}:reject('local-execution-history-shape')
        expected=expected_input(name,request,digest(decision),packet,partition,baseline,prior)
        if item['input']!=expected:reject('trial-stage-input-drift')
        remediation.validate_proposal(item['proposal'],expected,packet)
        remediation.validate_fresh_worker(item['receipt']['worker'],baseline)
        receipt_verifier=sol_high.validate_receipt if commit==SOL_HIGH_COMMIT else old.validate_receipt
        receipt_verifier(item['receipt'],expected,item['proposal'],digest(decision),[x['receipt'] for x in prior])
        prior.append(item)
    if history['report']!=expected_report(decision,packet,partition,baseline,stages):reject('local-execution-report-mismatch')
    return packet
