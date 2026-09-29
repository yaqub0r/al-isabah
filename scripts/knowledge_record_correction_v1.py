#!/usr/bin/env python3
"""Input-driven, bounded record correction; no worker is dispatched by this file."""
import copy
import hashlib
import json
from pathlib import Path

import knowledge_local_gated_history_v1 as replay
import knowledge_gated_continuation as prior
import knowledge_coverage_gate as coverage
import knowledge_record_accounting_v1 as accounting
import knowledge_export_v2_draft3 as export_contract
import knowledge_local_projection as prior_projection
from knowledge_export import canonical,digest,read,reject,Rejection

ROOT=prior.ROOT
CODE='scripts/knowledge_record_correction_v1.py'
RUNBOOK='docs/translation/knowledge-record-correction.md'
SCHEMA='al-isabah.knowledge-record-correction-request.v1'
DECISION_SCHEMA='al-isabah.knowledge-record-correction-decision.v1'
STAGE_SCHEMA='al-isabah.knowledge-record-correction-stage-input.v1'
RECEIPT_SCHEMA='al-isabah.knowledge-record-correction-receipt.v1'
SCOPE_SCHEMA='al-isabah.knowledge-record-correction-scope.v1'
STAGES=tuple(prior.original.old.STAGES)


def check_scope(scope,packet,seed,baseline_ledger,baseline_output):
    keys={'schema','recordId','sourceOrdinal','legacyRecordId','ownedSourceUnitIds',
          'ownedStructuralUnitIds','inheritedContextUnitIds','targetObligationIds','allowedCrossRecordRefs'}
    if set(scope)!=keys or scope['schema']!=SCOPE_SCHEMA:reject('correction-scope-shape')
    record=next((r for r in packet['records'] if r['id']==scope['recordId']),None)
    if record is None:reject('correction-scope-record')
    units={u['id']:u for u in packet['units'] if u['sourceRecordVersionId']==record['id']}
    if (scope['sourceOrdinal']!=record['sourceOrdinal'] or scope['legacyRecordId']!=record.get('legacyRecordId',record['id'])
        or scope['ownedSourceUnitIds']!=sorted(record['sourceUnitIds'])
        or scope['ownedStructuralUnitIds']!=sorted(uid for uid,u in units.items() if u['kind']!='entry')
        or scope['inheritedContextUnitIds']!=sorted(record.get('inheritedContextUnitIds',[]))):
        reject('correction-scope-source-drift')
    rows={x['obligationId']:x for x in baseline_ledger['outcomes']}
    expected=sorted(o['id'] for o in seed['obligations'] if o['recordId']==record['id']
                    and o['kind']=='semantic_gap' and rows[o['id']]['status']=='unresolved')
    if not expected or scope['targetObligationIds']!=expected:reject('correction-scope-obligation-drift')
    allowed=scope['allowedCrossRecordRefs']
    if not isinstance(allowed,list) or allowed!=sorted(allowed,key=canonical):
        reject('correction-cross-record-declaration')
    seen=set()
    for ref in allowed:
        if set(ref)!={'kind','id'} or ref['kind'] not in prior.original.old.COLLECTIONS:
            reject('correction-cross-record-declaration')
        value=next((x for x in baseline_output[ref['kind']] if x['id']==ref['id']),None)
        owner=object_owners(ref['kind'],value,baseline_output,packet) if value is not None else set()
        if value is None or ref['id'] in seen or not owner or record['id'] in owner:
            reject('correction-cross-record-declaration')
        seen.add(ref['id'])
    return record


def seed_candidate(seed,normalized):
    value=copy.deepcopy(seed)
    value.update(status='pending_review',baselineOutputSha256=digest(normalized['stages'][-1]['proposal']['output']),
                 originReportSha256=digest(normalized['report']))
    return value


def validate_rebased_seed(seed,original_seed,normalized):
    expected=seed_candidate(original_seed,normalized);expected['status']='reviewed_for_gate'
    if seed!=expected:reject('correction-rebased-seed-not-reviewed-or-drift')
    return seed


def context(history,pins,scope,seed,directory):
    normalized=replay.validate_history(history,pins)
    original_seed=history['context']['seed']
    validate_rebased_seed(seed,original_seed,normalized)
    check_scope(scope,normalized['packet'],seed,history['adjudication']['ledger'],
                normalized['stages'][-1]['proposal']['output'])
    resolved=directory.resolve();prior.original.old.require_runtime_directory(resolved)
    classes=prior_projection.baseline_classifications(normalized['baseline'],normalized['packet'],
        read(prior_projection.BASELINE_CLASSIFICATIONS),prior_projection.BASELINE_CLASSIFICATIONS_SHA256)
    return {'history':history,'pins':pins,'normalized':normalized,'scope':copy.deepcopy(scope),
            'seed':copy.deepcopy(seed),'directory':str(resolved),'baselineClassifications':classes}


def preview_context(history,pins,scope,directory):
    normalized=replay.validate_history(history,pins)
    seed=seed_candidate(history['context']['seed'],normalized)
    check_scope(scope,normalized['packet'],seed,history['adjudication']['ledger'],
                normalized['stages'][-1]['proposal']['output'])
    resolved=directory.resolve();prior.original.old.require_runtime_directory(resolved)
    classes=prior_projection.baseline_classifications(normalized['baseline'],normalized['packet'],
        read(prior_projection.BASELINE_CLASSIFICATIONS),prior_projection.BASELINE_CLASSIFICATIONS_SHA256)
    return {'history':history,'pins':pins,'normalized':normalized,'scope':copy.deepcopy(scope),
            'seed':seed,'directory':str(resolved),'baselineClassifications':classes}


def code_identity(commit,preview=False):
    paths=(CODE,RUNBOOK,'scripts/knowledge_record_accounting_v1.py',
           'schemas/knowledge-record-accounting.v1.schema.json',
           'scripts/knowledge_local_gated_history_v1.py',
           'scripts/knowledge_local_projection.py',
           'scripts/knowledge_export_v2_draft3.py',
           'profiles/knowledge/local-baseline-provenance.v1.json')
    if not preview:
        if prior.original.old.git('rev-parse','HEAD').decode().strip()!=commit:
            reject('correction-code-commit-mismatch')
        for path in paths:
            if prior.original.old.git('show',commit+':'+path).replace(b'\r\n',b'\n')!=(ROOT/path).read_bytes().replace(b'\r\n',b'\n'):
                reject('correction-code-drift')
    return {path:prior.original.old.assembly.lf_sha(ROOT/path) for path in paths}


def request(ctx,commit,preview=False):
    normalized=ctx['normalized'];scope=ctx['scope'];packet=normalized['packet'];seed=ctx['seed']
    code=code_identity(commit,preview)
    registry,config=prior.original.sol.configuration()
    baseline=ctx['history']['adjudication'];report=normalized['report']
    earlier=normalized['baseline']['stages']
    historical_sessions={x['worker']['observed']['sessionId'] for x in (s['receipt'] for s in earlier)}
    historical_sessions|={x['sessionId'] for x in report['launchAttempts']}
    return {'schema':SCHEMA if not preview else 'al-isabah.knowledge-record-correction-preview.v1',
            'issue':89,'action':'bounded_source_record_correction',
            'codeCommit':commit if not preview else 'PENDING_REVIEWED_COMMIT',
            'codeLfSha256':code,'directory':ctx['directory'],'fixtureClass':packet.get('fixtureClass','not-a-fixture'),
            'sourceArtifactSha256':packet['sourceArtifactSha256'],'packetSha256':packet['packetSha256'],
            'partitionFileSha256':digest(normalized['partition']),
            'profileSha256':digest(read(prior.original.remediation.PROFILE)),
            'outputSchemaSha256':digest(read(prior.original.private.SCHEMA)),
            'baselineLineageSha256':normalized['lineageSha256'],
            'baselineProposalSha256':digest(baseline['proposal']),
            'baselineOutputSha256':digest(baseline['proposal']['output']),
            'baselineLedgerSha256':digest(baseline['ledger']),'baselineGateSha256':digest(baseline['gate']),
            'baselineReportSha256':digest(report),'baselineRepairSha256':digest(ctx['history']['repair']),
            'baselineClassificationsSha256':digest(ctx['baselineClassifications']),
            'scope':copy.deepcopy(scope),'scopeSha256':digest(scope),'rebasedSeedSha256':digest(seed),
            'originalSeedSha256':digest(ctx['history']['context']['seed']),
            'accountingSchemaSha256':digest(read(accounting.SCHEMA_PATH)),
            'methodRegistrySha256':digest(registry),'methodId':registry['methods'][0]['methodId'],
            'taskRequest':prior.original.old.host_runtime.launch_request('codex-task',config['model'],config['reasoning']),
            'workerRequest':prior.original.old.host_runtime.launch_request('codex-worker',config['model'],config['reasoning']),
            'provider':config['provider'],'stages':list(STAGES),'maxFreshWorkers':3,
            'priorWorkerSessionIds':sorted(historical_sessions),
            'noAutomaticRetry':True,'humanReview':'unreviewed',
            'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False,
            **({'authorizable':False} if preview else {})}


def authorize(ctx,commit,decision,pin):
    if digest(decision)!=pin or decision.get('schema')!=DECISION_SCHEMA:
        reject('correction-exact-decision-required')
    req=request(ctx,commit)
    adapted={**decision,'schema':'al-isabah.knowledge-local-trial-decision.v1'}
    prior.original.old.check_decision(adapted,digest(adapted),req)
    return req


def baseline_value(ctx):
    normalized=ctx['normalized'];output=normalized['stages'][-1]['proposal']['output']
    return {'schema':'al-isabah.knowledge-record-correction-baseline.v1',
            'stages':[{'output':copy.deepcopy(x['proposal']['output']),
                       'receipt':copy.deepcopy(x['receipt'])} for x in normalized['stages']],
            'reportSha256':digest(normalized['report']),
            'lineageSha256':normalized['lineageSha256'],
            'historicalWorkerSessionIds':request_sessions(ctx)}


def request_sessions(ctx):
    normalized=ctx['normalized'];sessions={x['sessionId'] for x in normalized['report']['launchAttempts']}
    sessions|={x['receipt']['worker']['observed']['sessionId'] for x in normalized['baseline']['stages']}
    return sorted(sessions)


def stage_input(name,ctx,commit,decision,pin,prior_items=()):
    req=authorize(ctx,commit,decision,pin)
    if name not in STAGES or len(prior_items)!=STAGES.index(name):reject('correction-stage-order')
    for n,item in enumerate(prior_items):validate_item(STAGES[n],item,ctx,commit,decision,pin,prior_items[:n])
    packet=ctx['normalized']['packet'];partition=ctx['normalized']['partition'];base=baseline_value(ctx)
    value=prior_module_stage(name,req,pin,packet,partition)
    value.update(schema=STAGE_SCHEMA,profile=read(prior.original.remediation.PROFILE),
                 outputSchema=read(prior.original.private.SCHEMA),
                 baseline=base,baselineSha256=digest(base),scope=copy.deepcopy(ctx['scope']),
                 rebasedSeed=copy.deepcopy(ctx['seed']),rebasedSeedSha256=digest(ctx['seed']),
                 baselineLedger=copy.deepcopy(ctx['history']['adjudication']['ledger']),
                 baselineGate=copy.deepcopy(ctx['history']['adjudication']['gate']),
                 baselineLineageSha256=req['baselineLineageSha256'],
                 accountingSchema=read(accounting.SCHEMA_PATH),
                 accountingSchemaSha256=req['accountingSchemaSha256'],
                 priorOutputs=[x['proposal']['output'] for x in prior_items],
                 priorRemediations=[x['proposal'] for x in prior_items],
                 priorReceiptSha256=[x['receipt']['receiptSha256'] for x in prior_items],
                 priorAccounting=[x['accounting'] for x in prior_items],
                 priorReview=[x['critique'] for x in prior_items if 'critique' in x],
                 correctionRequestSha256=digest(req))
    return value


def prior_module_stage(name,req,pin,packet,partition):
    return prior.original.old.stage_input_value(name,req,pin,packet,partition,[],
             (ROOT/RUNBOOK).read_text(encoding='utf-8-sig'))


def object_owners(kind,value,output,packet):
    """Resolve one graph object's complete source-record ownership conservatively."""
    if value is None:return set()
    if 'sourceRecordVersionIds' in value:return set(value['sourceRecordVersionIds'])
    if 'sourceRecordVersionId' in value:return {value['sourceRecordVersionId']}
    spans={s['id']:u['sourceRecordVersionId'] for u in packet['units'] for s in u['spans']}
    if 'sourceSpanId' in value:return {spans[value['sourceSpanId']]}
    maps={name:{row['id']:row for row in output[name]}
          for name in prior.original.old.COLLECTIONS}
    if kind=='findings':
        owners=set()
        if not value['targets']:return owners
        for ref in value['targets']:
            if ref['kind']=='sourceRecords':owners.add(ref['id']);continue
            if ref['kind']=='sourceSpans':
                if ref['id'] not in spans:return set()
                owners.add(spans[ref['id']]);continue
            if ref['kind']=='findings':return set()
            target=maps.get(ref['kind'],{}).get(ref['id'])
            if target is None:return set()
            resolved=object_owners(ref['kind'],target,output,packet)
            if not resolved:return set()
            owners.update(resolved)
        return owners
    if kind=='attributions':
        if not value['entityIds']:return set()
        owners=set()
        for eid in value['entityIds']:
            entity=maps['entities'].get(eid)
            if entity is None:return set()
            owners.update(entity['sourceRecordVersionIds'])
        return owners
    if kind=='useRestrictions':
        claims=[claim for claim in output['claims'] if value['id'] in claim['useRestrictionIds']]
        return {rid for claim in claims for rid in claim['sourceRecordVersionIds']}
    return set()


def validate_record_edits(before,after,packet,scope):
    rid=scope['recordId'];allowed={(x['kind'],x['id']) for x in scope['allowedCrossRecordRefs']}
    spans={s['id']:u['sourceRecordVersionId'] for u in packet['units'] for s in u['spans']}
    for kind in prior.original.old.COLLECTIONS:
        old={x['id']:x for x in before[kind]};new={x['id']:x for x in after[kind]}
        for identity in set(old)|set(new):
            left=old.get(identity);right=new.get(identity)
            if left==right:continue
            owners=[object_owners(kind,value,graph,packet)
                    for value,graph in ((left,before),(right,after)) if value is not None]
            if all(owner=={rid} for owner in owners):continue
            if (kind,identity) in allowed and all(owner and rid not in owner for owner in owners):
                continue
            reject('correction-nontarget-object-change')
    for key,identity,owner in (
        ('spanDispositions','sourceSpanId',lambda x:spans[x['sourceSpanId']]),
        ('recordReviews','sourceRecordVersionId',lambda x:x['sourceRecordVersionId']),
        ('concerns','id',lambda x:next((spans[s] for s in x['sourceSpanIds'] if spans[s]!=rid),rid)),
        ('nonclaimReviews','sourceSpanId',lambda x:spans[x['sourceSpanId']])):
        old={x[identity]:x for x in before[key]};new={x[identity]:x for x in after[key]}
        for name in set(old)|set(new):
            value=new.get(name) or old.get(name)
            if owner(value)!=rid and old.get(name)!=new.get(name):reject('correction-nontarget-metadata-change')
    before_mentions={x['id']:x['sourceRecordVersionId'] for x in before['mentions']}
    after_mentions={x['id']:x['sourceRecordVersionId'] for x in after['mentions']}
    for key in ('mentionEvidence','retainedFindingCoverage'):
        identity='mentionId' if key=='mentionEvidence' else 'sourceFindingId'
        old={x[identity]:x for x in before[key]};new={x[identity]:x for x in after[key]}
        for name in set(old)|set(new):
            owner=(before_mentions|after_mentions).get(name) if key=='mentionEvidence' else name.split(':retained-finding:',1)[0]
            if owner!=rid and old.get(name)!=new.get(name):reject('correction-nontarget-metadata-change')


def check_ledger(ctx,ledger,proposal):
    seed=ctx['seed'];baseline=ctx['history']['adjudication']['ledger']
    if (ledger['baselineOutputSha256']!=digest(ctx['normalized']['stages'][-1]['proposal']['output'])
        or ledger['seedSha256']!=digest(seed) or ledger['candidateOutputSha256']!=digest(proposal['output'])):
        reject('correction-ledger-binding')
    before={r['obligationId']:r for r in baseline['outcomes']}
    after={r['obligationId']:r for r in ledger['outcomes']}
    if set(before)!=set(after):reject('correction-known-obligation-loss')
    for oid in set(before)-set(ctx['scope']['targetObligationIds']):
        if before[oid]!=after[oid]:reject('correction-nontarget-obligation-change')
    target=ctx['scope']['recordId']
    old_anchors=[x for x in baseline['sourceAnchors'] if x['recordId']!=target]
    new_anchors=[x for x in ledger['sourceAnchors'] if x['recordId']!=target]
    if old_anchors!=new_anchors:reject('correction-nontarget-anchor-change')


def gate_result(ctx,stage,proposal,ledger):
    check_ledger(ctx,ledger,proposal)
    baseline=ctx['normalized']['stages'][-1]
    req=ctx['history']['continuationRequest']
    pins={'sourceArtifactSha256':req['sourceArtifactSha256'],
          'packetSha256':req['packetSha256'],
          'baselineOutputSha256':digest(baseline['proposal']['output']),
          'profileSha256':digest(read(prior.original.remediation.PROFILE)),
          'seedSha256':digest(ctx['seed']),
          'originReportSha256':digest(ctx['normalized']['report'])}
    return coverage.validate(ctx['normalized']['packet'],ctx['normalized']['partition'],
        read(prior.original.remediation.PROFILE),baseline['input'],baseline['proposal']['output'],
        stage,proposal,ctx['seed'],ledger,pins)


def record_completion_blockers(output,packet,scope,ledger,classifications=None):
    """Apply the established trial completion conditions to this owned record."""
    rid=scope['recordId']
    owned={s['id'] for u in packet['units'] if u['sourceRecordVersionId']==rid for s in u['spans']}
    rows=[row for row in output['spanDispositions'] if row['sourceSpanId'] in owned]
    evidence=prior_projection.completion_evidence(output,packet,rid,rows,classifications)
    review=next(x for x in output['recordReviews'] if x['sourceRecordVersionId']==rid)
    blockers=[]
    if any(review[axis]!='checked' for axis in prior.original.old.REVIEW_AXES):
        blockers.append('review_axes')
    if any(row['status'] in export_contract.BLOCKED for row in rows):blockers.append('owned_spans')
    if evidence['substantiveOpenConcernIds']:blockers.append('open_concerns')
    if any(row['sourceSpanId'] in owned and row['status']=='unresolved'
           for row in output['nonclaimReviews']):blockers.append('nonclaim_review')
    if evidence['blockingFindingIds']:blockers.append('blocking_findings')
    outcomes={row['obligationId']:row for row in ledger['outcomes']}
    if any(outcomes[oid]['status']=='unresolved' for oid in scope['targetObligationIds']):
        blockers.append('known_obligations')
    return blockers


def final_gate(ctx,stage,proposal,ledger,review_result):
    try:
        checked=gate_result(ctx,stage,proposal,ledger)
        status='retained_partial_progress'
    except Rejection as error:
        if str(error)!='coverage-no-material-progress':raise
        checked=None;status='not_established'
    blockers=record_completion_blockers(proposal['output'],ctx['normalized']['packet'],ctx['scope'],ledger,
                                        ctx['baselineClassifications'])
    complete=review_result['recordComplete'] and checked is not None and not blockers
    if review_result['recordComplete'] and not complete:reject('correction-false-record-completeness')
    return {'schema':'al-isabah.knowledge-record-correction-final-gate.v1','status':status,
            'baselineGateSha256':digest(ctx['history']['adjudication']['gate']),
            'finalProposalSha256':digest(proposal),'finalLedgerSha256':digest(ledger),
            'materialObligationIds':checked['materialObligationIds'] if checked else [],
            'reviewedAccountingSha256':review_result['accountingSha256'],
            'accountingReviewSha256':review_result['reviewSha256'],
            'recordComplete':complete,'recordCompletionBlockers':blockers,
            'exhaustiveVolumeCoverage':False,'humanReview':'unreviewed',
            'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False}


def validate_content(name,item,ctx,stage,prior_items):
    packet=ctx['normalized']['packet'];baseline=ctx['normalized']['stages'][-1]['proposal']['output']
    proposal=item['proposal']
    prior.original.remediation.validate_proposal(proposal,stage,packet)
    validate_record_edits(baseline,proposal['output'],packet,ctx['scope'])
    accounting.validate(item['accounting'],packet,proposal['output'],ctx['scope'])
    if name==STAGES[0]:
        if item['accounting']['recordComplete']:reject('correction-premature-completeness')
        expected=gate_result(ctx,stage,proposal,item['ledger'])
        if item['gate']!=expected:reject('correction-extraction-gate-drift')
    elif name==STAGES[1]:
        if item['accounting']['recordComplete']:reject('correction-premature-completeness')
        accounting.validate_review(item['critique'],item['accounting'],packet,proposal['output'],ctx['scope'])
    else:
        review=prior_items[1]
        evidence=accounting.validate_final(item['accounting'],review['accounting'],review['critique'],
            packet,review['proposal']['output'],proposal['output'],ctx['scope'])
        expected=final_gate(ctx,stage,proposal,item['ledger'],evidence)
        if item['gate']!=expected:reject('correction-final-gate-drift')


def reservation(name,ctx,commit,decision,pin,prior_items):
    stage=stage_input(name,ctx,commit,decision,pin,prior_items)
    return {'schema':'al-isabah.knowledge-record-correction-reservation.v1',
            'stage':name,'slotNumber':STAGES.index(name)+1,'stageInputSha256':digest(stage),
            'requestSha256':stage['correctionRequestSha256'],'decisionSha256':pin,
            'directory':ctx['directory'],'priorReceiptSha256':stage['priorReceiptSha256'],
            'status':'reserved'}


def write_once(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('xb') as stream:stream.write(canonical(value))
    except FileExistsError:reject('correction-slot-already-consumed')


def reserve_once(name,ctx,commit,decision,pin,prior_items):
    directory=Path(ctx['directory']);stage=stage_input(name,ctx,commit,decision,pin,prior_items)
    if read(directory/(name+'.input.json'))!=stage:reject('correction-stage-input-drift')
    value=reservation(name,ctx,commit,decision,pin,prior_items)
    write_once(directory/(name+'.reservation.json'),value)
    return value


def bind_attempt(name,reserved,worker_log,session,turn,task,ctx,commit,decision,pin,prior_items):
    if reserved!=reservation(name,ctx,commit,decision,pin,prior_items):
        reject('correction-reservation-drift')
    req=authorize(ctx,commit,decision,pin)
    _,config=prior.original.sol.configuration()
    if (task['request']!=req['taskRequest'] or
        prior.original.old.host_runtime.launch_errors(task,config,'codex-task')):
        reject('correction-task-host-mismatch')
    observed=prior.original.old.host_runtime.observe_session(worker_log,session,turn,
                 expected_parent_session_id=task['observed']['sessionId'])
    worker={'request':req['workerRequest'],'observed':observed}
    if prior.original.old.host_runtime.launch_errors(worker,config,'codex-worker'):
        reject('correction-worker-host-mismatch')
    used=set(request_sessions(ctx))|{x['attempt']['worker']['observed']['sessionId'] for x in prior_items}
    if session in used or session==task['observed']['sessionId']:
        reject('correction-worker-reuse')
    raw=worker_log.read_bytes();status,phase=prior.terminal_result(raw,turn)
    return {'schema':'al-isabah.knowledge-record-correction-attempt.v1','stage':name,
            'reservationSha256':digest(reserved),'requestSha256':digest(req),
            'decisionSha256':pin,'task':copy.deepcopy(task),'worker':worker,
            'logPath':str(worker_log.resolve()),'logSha256':hashlib.sha256(raw).hexdigest(),
            'status':status,'terminalPhase':phase or ''}


def bind_once(name,worker_log,session,turn,task,ctx,commit,decision,pin,prior_items):
    directory=Path(ctx['directory']);path=directory/(name+'.attempt.json')
    if path.exists():reject('correction-slot-already-consumed')
    reserved=read(directory/(name+'.reservation.json'))
    value=bind_attempt(name,reserved,worker_log,session,turn,task,ctx,commit,decision,pin,prior_items)
    write_once(path,value)
    return value


def capture(name,item,ctx,commit,decision,pin,prior_items):
    stage=stage_input(name,ctx,commit,decision,pin,prior_items)
    required={'input','proposal','accounting','reservation','attempt','receipt'}
    required|=({'ledger','gate'} if name!=STAGES[1] else {'critique'})
    if set(item)!=required or item['input']!=stage:reject('correction-stage-shape-or-drift')
    reserved=reservation(name,ctx,commit,decision,pin,prior_items)
    if item['reservation']!=reserved:reject('correction-reservation-drift')
    attempt=item['attempt'];observed=attempt['worker']['observed']
    expected=bind_attempt(name,reserved,Path(attempt['logPath']),observed['sessionId'],
                          observed['turnId'],attempt['task'],ctx,commit,decision,pin,prior_items)
    if attempt!=expected or attempt['status']!='completed' or attempt['terminalPhase'] not in {'final','final_answer'}:
        reject('correction-attempt-not-completed')
    if prior_items and attempt['task']!=prior_items[0]['attempt']['task']:
        reject('correction-task-reuse-required')
    validate_content(name,item,ctx,stage,prior_items)
    base=prior.original.sol.capture(stage,item['proposal'],ctx['normalized']['packet'],pin,
                                    attempt['task'],attempt['worker'],[x['receipt'] for x in prior_items])
    value={**base,'schema':RECEIPT_SCHEMA,'requestSha256':stage['correctionRequestSha256'],
           'baselineLineageSha256':ctx['normalized']['lineageSha256'],
           'rebasedSeedSha256':digest(ctx['seed']),'scopeSha256':digest(ctx['scope']),
           'reservationSha256':digest(reserved),'attemptSha256':digest(attempt),
           'accountingSha256':digest(item['accounting']),
           'critiqueSha256':digest(item['critique']) if name==STAGES[1] else '',
           'ledgerSha256':digest(item['ledger']) if 'ledger' in item else '',
           'gateSha256':digest(item['gate']) if 'gate' in item else ''}
    value['checkpointSha256']=prior.original.old.receipt_checkpoint(value)
    value['receiptSha256']=digest({k:v for k,v in value.items() if k!='receiptSha256'})
    return value


def validate_item(name,item,ctx,commit,decision,pin,prior_items):
    expected=capture(name,item,ctx,commit,decision,pin,prior_items)
    if item['receipt']!=expected:reject('correction-receipt-drift')
    return item


def report(ctx,commit,decision,pin,items):
    if len(items)!=3:reject('correction-three-stages-required')
    req=authorize(ctx,commit,decision,pin)
    for n,item in enumerate(items):validate_item(STAGES[n],item,ctx,commit,decision,pin,items[:n])
    launches=copy.deepcopy(ctx['normalized']['report']['launchAttempts'])
    launches += [{'stage':STAGES[n],'status':'completed',
                  'sessionId':x['attempt']['worker']['observed']['sessionId'],
                  'turnId':x['attempt']['worker']['observed']['turnId'],
                  'reservationSha256':digest(x['reservation']),
                  'attemptSha256':digest(x['attempt']),
                  'receiptSha256':x['receipt']['receiptSha256']} for n,x in enumerate(items)]
    if len(launches)!=7 or len({x['sessionId'] for x in launches})!=7:
        reject('correction-launch-count')
    final=items[-1]
    return {'schema':'al-isabah.knowledge-record-correction-validation.v1','status':'partial',
            'requestSha256':digest(req),'decisionSha256':pin,
            'baselineLineageSha256':ctx['normalized']['lineageSha256'],
            'baselineReportSha256':digest(ctx['normalized']['report']),
            'launchAttempts':launches,'finalProposalSha256':digest(final['proposal']),
            'finalLedgerSha256':digest(final['ledger']),'finalGateSha256':digest(final['gate']),
            'finalAccountingSha256':digest(final['accounting']),
            'independentReviewSha256':digest(items[1]['critique']),
            'recordComplete':final['gate']['recordComplete'],'exhaustiveVolumeCoverage':False,
            'humanReview':'unreviewed','consumerAdmissionAuthorized':False,
            'publicReleaseAuthorized':False}
