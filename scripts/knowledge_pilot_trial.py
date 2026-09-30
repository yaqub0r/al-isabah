#!/usr/bin/env python3
"""Fail-closed local-only trial gate; no model dispatch or production export."""
import argparse
import copy
import hashlib
import subprocess
from pathlib import Path
from schema_validation import validate_schema_instance
import host_runtime
import knowledge_export_v2_draft2 as export_contract
import knowledge_runtime_draft as method
import assemble_knowledge_pilot as assembly
from knowledge_export import canonical,digest,read,shape,reject,Rejection
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/'schemas/knowledge-pilot-stage-output.v1.schema.json'
WORKER_OBSERVATION=ROOT/'schemas/knowledge-local-trial-worker-observation.v2.schema.json'
PROFILE=ROOT/'profiles/knowledge/volume-08.local-trial.v1.json'
RUNBOOK=ROOT/'docs/translation/knowledge-pilot-local-trial.md'
COORDINATOR='01a0e484-1411-7380-bb06-ada33129c9b2'
STAGES=method.STAGES
REVIEW_AXES=('sourceIdentity','englishFidelity','structureCoverage','honorificPreservation','nameIdentity','negationNumbersTransmission','qualificationPreservation')
COLLECTIONS=('entities','mentions','names','reports','events','claims','ambiguityGroups','values','places','times','qualifications','attributions','useRestrictions','findings')
CRITICAL=('scripts/knowledge_pilot_trial.py','scripts/assemble_knowledge_pilot.py','scripts/prepare_knowledge_pilot.py','scripts/knowledge_export.py','scripts/knowledge_export_v2_draft2.py','scripts/knowledge_runtime_draft.py','scripts/host_runtime.py','scripts/execution_governance.py','scripts/schema_validation.py','scripts/public_boundary.py','scripts/translation_workflow.py','schemas/knowledge-pilot-stage-output.v1.schema.json','schemas/al-isabah-knowledge-export.v2-draft2.schema.json','profiles/knowledge/volume-08.local-trial.v1.json','profiles/knowledge/execution-methods.v1-draft.json','docs/translation/knowledge-pilot-local-trial.md','profiles/translation-source.v1.json','compliance/source-register.v1.json','compliance/policy-binding.v5.json',*assembly.POLICIES)

CRITICAL=(*CRITICAL,'schemas/knowledge-local-trial-worker-observation.v2.schema.json','schemas/knowledge-runtime-receipt.v1-draft.schema.json','scripts/knowledge_pilot_recovery.py')


def git(*args):
    try:return subprocess.run(['git',*args],cwd=ROOT,check=True,capture_output=True).stdout
    except (OSError,subprocess.CalledProcessError):reject('trial-code-state-unavailable')


def verify_checkout(commit):
    if git('rev-parse','HEAD').decode().strip()!=commit:reject('trial-code-commit-mismatch')
    for path in CRITICAL:
        committed=git('show',commit+':'+path).replace(b'\r\n',b'\n')
        if committed!=(ROOT/path).read_bytes().replace(b'\r\n',b'\n'):reject('trial-code-worktree-drift')


def validate_packet(packet,metadata):
    if digest({k:v for k,v in packet.items() if k!='packetSha256'})!=packet['packetSha256']:reject('trial-packet-digest-mismatch')
    if metadata['packetSha256']!=packet['packetSha256'] or metadata['packetFileSha256']!=digest(packet):reject('trial-packet-pin-mismatch')
    if digest({k:v for k,v in metadata.items() if k!='partitionSha256'})!=metadata['partitionSha256']:reject('trial-partition-digest-mismatch')
    if [r['sourceOrdinal'] for r in packet['records']]!=metadata['sourceOrdinals']:reject('trial-scope-mismatch')
    if metadata['sourceOrdinals']!=list(assembly.preparation.ORDINALS) and packet.get('fixtureClass')!='synthetic-conformance':reject('trial-scope-mismatch')
    if metadata['methodRegistrySha256']!=digest(read(method.REGISTRY_PATH)):reject('trial-method-mismatch')
    if packet['policyPins']!={p:assembly.lf_sha(ROOT/p) for p in assembly.POLICIES}:reject('trial-policy-drift')
    if packet['assemblerLfSha256']!=assembly.lf_sha(Path(assembly.__file__)):reject('trial-assembler-drift')
    record_ids=[r['id'] for r in packet['records']];unit_ids=[u['id'] for u in packet['units']];span_ids=[s['id'] for u in packet['units'] for s in u['spans']]
    if len(record_ids)!=len(set(record_ids)) or len(unit_ids)!=len(set(unit_ids)) or len(span_ids)!=len(set(span_ids)):reject('trial-scope-mismatch')
    owners={unit:r['id'] for r in packet['records'] for unit in r['sourceUnitIds']}
    if set(owners)!=set(unit_ids) or sum(len(r['sourceUnitIds']) for r in packet['records'])!=len(unit_ids):reject('trial-scope-mismatch')
    for unit in packet['units']:
        if owners[unit['id']]!=unit['sourceRecordVersionId'] or not unit['spans']:reject('trial-scope-mismatch')
        if [s['partIndex'] for s in unit['spans']]!=list(range(1,len(unit['spans'])+1)) or any(s['sourceUnitId']!=unit['id'] for s in unit['spans']):reject('trial-partition-loss')
        raw=''.join(s['rawOpeniti'] for s in unit['spans'])
        if assembly.sha(raw.encode('utf-8'))!=unit['rawSha256']:reject('trial-partition-loss')
        if any(assembly.sha(s['rawOpeniti'].encode('utf-8'))!=s['sha256'] for s in unit['spans']):reject('trial-partition-loss')
    contexts=packet.get('inheritedContextUnits',[])
    if len({c['id'] for c in contexts})!=len(contexts) or {c['id'] for c in contexts}&set(unit_ids):reject('trial-context-mismatch')
    if any(assembly.sha(c['rawOpeniti'].encode('utf-8'))!=c['rawSha256'] for c in contexts):reject('trial-context-mismatch')
    if [{k:v for k,v in c.items() if k!='rawOpeniti'} for c in contexts]!=metadata.get('inheritedContextUnits',[]):reject('trial-context-mismatch')
    if any(not set(r.get('inheritedContextUnitIds',[]))<=set(unit_ids)|{c['id'] for c in contexts} for r in packet['records']):reject('trial-context-mismatch')
    expected=[{'id':u['id'],'kind':u['kind'],'sourceRecordVersionId':u['sourceRecordVersionId'],'rawSha256':u['rawSha256'],'spans':[{k:v for k,v in s.items() if k!='rawOpeniti'} for s in u['spans']]} for u in packet['units']]
    if expected!=metadata['units']:reject('trial-partition-pin-mismatch')


def decision_request(packet,metadata,commit):
    validate_packet(packet,metadata)
    fixture=packet.get('fixtureClass','not-a-fixture')
    if fixture!='synthetic-conformance':verify_checkout(commit)
    return {'schema':'al-isabah.knowledge-local-trial-request.v1','fixtureClass':fixture,'issue':89,'action':'bounded_local_knowledge_trial','coordinatorThreadId':COORDINATOR,'codeCommit':commit,'packetSha256':packet['packetSha256'],'partitionSha256':metadata['partitionSha256'],'partitionFileSha256':digest(metadata),'methodRegistrySha256':digest(read(method.REGISTRY_PATH)),'methodId':read(method.REGISTRY_PATH)['methods'][0]['methodId'],'profileSha256':digest(read(PROFILE)),'outputSchemaSha256':digest(read(SCHEMA)),'runbookLfSha256':assembly.lf_sha(RUNBOOK),'sourceOrdinals':metadata['sourceOrdinals'],'stages':list(STAGES),'maxFreshWorkers':3,'taskRequest':host_runtime.launch_request('codex-task','gpt-5.6-sol','xhigh'),'workerRequest':host_runtime.launch_request('codex-worker','gpt-5.6-sol','xhigh'),'provider':'openai','publicReleaseAuthorized':False,'consumerAdmissionAuthorized':False}


def check_decision(decision,expected_digest,request):
    if digest(decision)!=expected_digest:reject('trial-decision-pin-mismatch')
    if set(decision)!={'schema','request','approval','origin'} or decision['schema']!='al-isabah.knowledge-local-trial-decision.v1' or decision['approval']!='approved':reject('trial-not-authorized')
    if decision['request']!=request:reject('trial-decision-scope-mismatch')
    origin=decision['origin']
    if set(origin)!={'kind','threadId','userTurnReference','recordedBy'} or origin['kind']!='actual_user_message' or origin['threadId']!=COORDINATOR or origin['recordedBy']!='trusted_coordinator' or not isinstance(origin['userTurnReference'],str):reject('trial-user-authorization-required')
    return request


def authorize(decision,expected_digest,packet,metadata,commit):
    # Trusted operator provenance, not independent chat authentication.
    return check_decision(decision,expected_digest,decision_request(packet,metadata,commit))


def retained_ledger(packet):
    return [{'id':r['id']+':retained-finding:'+str(n),'sourceRecordVersionId':r['id'],'evidenceSha256':digest(f),'evidence':f} for r in packet['records'] for n,f in enumerate(r['retainedFindings'],1)]


def artifact_inputs(packet):
    return [{'id':'urn:al-isabah:trial:artifact:authority','kind':'source_derivation','sha256':packet['sourceArtifactSha256']},{'id':'urn:al-isabah:trial:artifact:candidate-manifest','kind':'source_derivation','sha256':packet['candidateManifestSha256']}]


def validate_real_identities(value):
    if isinstance(value,str) and value.startswith('urn:al-isabah:synthetic:'):reject('trial-proposal-identity-mismatch')
    if isinstance(value,dict):
        for child in value.values():validate_real_identities(child)
    elif isinstance(value,list):
        for child in value:validate_real_identities(child)


def validate_output(output,stage_input,packet):
    shape(output,read(SCHEMA))
    if output['stage']!=stage_input['stage'] or output['stageInputSha256']!=digest(stage_input) or output['packetSha256']!=packet['packetSha256']:reject('trial-output-input-mismatch')
    spans={s['id']:{**s,'sourceRecordVersionId':u['sourceRecordVersionId'],'unitKind':u['kind']} for u in packet['units'] for s in u['spans']}
    records={r['id']:r for r in packet['records']}
    maps={key:export_contract.indexed(output[key]) for key in COLLECTIONS}
    maps.update(sourceRecords=records,sourceSpans=spans,sourceUnits={u['id']:u for u in packet['units']},artifacts=export_contract.indexed(artifact_inputs(packet)),assessments={},actors={},logicalRecords={})
    ids=[identity for key in COLLECTIONS for identity in maps[key]]
    if len(ids)!=len(set(ids)):reject('immutable-id-conflict')
    for key in COLLECTIONS:export_contract.validate_refs(output[key],maps)
    if stage_input['fixtureClass']!='synthetic-conformance':
        validate_real_identities(output)
        if any(not identity.startswith('urn:al-isabah:trial:') for identity in ids):reject('trial-proposal-identity-mismatch')
    for prior in stage_input.get('priorOutputs',[]):
        for kind in COLLECTIONS:
            old=export_contract.indexed(prior[kind])
            if any(v['id'] in old and old[v['id']]!=v for v in output[kind]):reject('trial-immutable-id-conflict')
    def owned(span_ids,record_ids):
        if not record_ids or any(s not in spans or spans[s]['sourceRecordVersionId'] not in record_ids for s in span_ids):reject('trial-source-binding-mismatch')
    export_contract.validate_names(maps,owned)
    for key in COLLECTIONS:
        for value in output[key]:
            if 'sourceRecordVersionIds' in value and not value['sourceRecordVersionIds']:reject('trial-source-binding-mismatch')
            if value.get('assessmentIds') or value.get('identityAssessmentIds') or value.get('criticalAssessmentIds'):reject('trial-assessment-inferred')
            if key=='names' and value['derivation']=='editorial_supply':reject('trial-editorial-supply-unbound')
    mentions=maps['mentions'];evidence={x['mentionId']:x for x in output['mentionEvidence']}
    if len(evidence)!=len(output['mentionEvidence']) or set(evidence)!=set(mentions):reject('trial-mention-evidence-mismatch')
    for identity,mention in mentions.items():
        evidence_row=evidence[identity]
        if evidence_row['sourceSpanId']!=mention['sourceSpanId']:reject('trial-mention-evidence-mismatch')
        raw=spans[mention['sourceSpanId']]['rawOpeniti'];a=evidence_row['startChar'];b=evidence_row['endChar']
        if not 0<=a<b<=len(raw) or assembly.sha(raw[a:b].encode('utf-8'))!=mention['surfaceSha256']:reject('trial-mention-evidence-mismatch')
        owned([mention['sourceSpanId']],[mention['sourceRecordVersionId']])
        if identity not in maps['entities'][mention['entityId']]['mentionIds']:reject('reference-closure-mismatch')
    logical_ids=[e['logicalEntityId'] for e in maps['entities'].values()]
    if len(logical_ids)!=len(set(logical_ids)):reject('logical-identity-conflict')
    for entity in maps['entities'].values():
        if not entity['sourceRecordVersionIds'] or any(mentions[m]['entityId']!=entity['id'] for m in entity['mentionIds']):reject('reference-closure-mismatch')
    profile=read(PROFILE);predicates=export_contract.indexed(profile['predicates'])
    for claim in maps['claims'].values():
        owned(claim['sourceSpanIds'],claim['sourceRecordVersionIds'])
        if not claim['sourceSpanIds'] or not claim['reportIds'] or not claim['qualificationIds'] or not claim['attributionIds'] or not claim['useRestrictionIds']:reject('trial-claim-evidence-missing')
        pred=predicates.get(claim['predicateId'])
        if pred is None:reject('unapproved-predicate')
        if maps['entities'][claim['subjectId']]['kind'] not in pred['subjectKinds'] or claim['objectRef']['kind'] not in pred['objectKinds']:reject('reference-kind-mismatch')
        if claim['objectRef']['kind']=='entities' and maps['entities'][claim['objectRef']['id']]['kind'] not in pred['objectEntityKinds']:reject('reference-kind-mismatch')
        if any(claim['id'] not in maps['reports'][r]['claimIds'] for r in claim['reportIds']):reject('reference-closure-mismatch')
        quals=[maps['qualifications'][q] for q in claim['qualificationIds']]
        if any({'kind':'claims','id':claim['id']} not in q['targets'] for q in quals):reject('qualification-loss')
        factual=any(maps['useRestrictions'][u]['tier']=='factual_spine' for u in claim['useRestrictionIds'])
        if factual and (claim['polarity']=='absence_of_evidence' or claim['assertionClass']!='source_attested' or claim['modality']!='asserted' or claim['ambiguityGroupIds'] or any(q['criticalStatus']!='unqualified' or q['evidentiaryStrength']!='source_supported' for q in quals)):reject('qualification-loss')
    for report in maps['reports'].values():
        owned(report['sourceSpanIds'],report['sourceRecordVersionIds'])
        if not report['sourceSpanIds'] or any(report['id'] not in maps['claims'][c]['reportIds'] for c in report['claimIds']):reject('reference-closure-mismatch')
        if [t['position'] for t in report['transmission']]!=list(range(len(report['transmission']))):reject('transmission-order-mismatch')
        if any((t['role']=='unresolved' and not t['ambiguityGroupIds']) or (t['role']!='unresolved' and not t['entityIds']) for t in report['transmission']):reject('qualification-loss')
    for event in maps['events'].values():
        if event['typeId'] not in profile['eventTypes'] or any(p['roleId'] not in profile['participantRoles'] for p in event['participantRoles']):reject('unapproved-role')
    for time in maps['times'].values():
        if time['earliest']>time['latest']:reject('time-interval-invalid')
    for group in maps['ambiguityGroups'].values():
        expected={(kind,v['id']) for kind in COLLECTIONS for v in maps[kind].values() if group['id'] in v.get('ambiguityGroupIds',[])}
        if expected!={(r['kind'],r['id']) for r in group['members']}:reject('ambiguity-incomplete')
    rows={x['sourceSpanId']:x for x in output['spanDispositions']}
    if len(rows)!=len(output['spanDispositions']) or set(rows)!=set(spans):reject('trial-span-coverage-mismatch')
    reasons={'represented':{'mapped'},'represented_uncertain':{'uncertain'},'structural_only':{'heading'},'nonclaim_form':{'formula_only','bibliographic_format'},'unsupported_semantics':{'unsupported'},'unprocessed':{'pending'},'source_or_mapping_blocked':{'source_damage','mapping_unverified'}}
    for sid,row in rows.items():
        export_contract.validate_refs(row,maps)
        if row['reasonCode'] not in reasons[row['status']]:reject('disposition-mismatch')
        if row['status']=='structural_only' and spans[sid]['unitKind']=='entry':reject('disposition-mismatch')
        if row['status'] in {'represented','represented_uncertain'} and not row['claimIds'] and not row['reportIds']:reject('disposition-mismatch')
        if row['status']=='represented_uncertain' and not row['ambiguityGroupIds']:reject('ambiguity-incomplete')
        if row['status'] in {'structural_only','nonclaim_form','unprocessed'} and (row['claimIds'] or row['reportIds']):reject('disposition-mismatch')
        for kind,field in [('claims','claimIds'),('reports','reportIds')]:
            expected={v['id'] for v in maps[kind].values() if sid in v['sourceSpanIds']}
            if set(row[field])!=expected:reject('reference-closure-mismatch')
    nonclaims={r['sourceSpanId']:r for r in output['nonclaimReviews']}
    if len(nonclaims)!=len(output['nonclaimReviews']) or set(nonclaims)!={sid for sid,r in rows.items() if r['status']=='nonclaim_form'}:reject('trial-nonclaim-review-missing')
    for row in nonclaims.values():
        if not row['rationale'].strip() or (output['stage']==STAGES[0] and row['status']!='proposed') or (output['stage']!=STAGES[0] and row['status']=='proposed'):reject('trial-nonclaim-review-missing')
    reviews={r['sourceRecordVersionId']:r for r in output['recordReviews']}
    if len(reviews)!=len(output['recordReviews']) or set(reviews)!=set(records):reject('trial-record-review-coverage-mismatch')
    for review in reviews.values():
        if not review['rationale'].strip():reject('trial-review-evidence-missing')
        export_contract.validate_refs(review,maps)
    concerns=export_contract.indexed(output['concerns'])
    for concern in concerns.values():
        if not concern['sourceSpanIds'] or not set(concern['sourceSpanIds'])<=set(spans) or not concern['rationale'].strip():reject('trial-review-evidence-missing')
    finding_rows={x['sourceFindingId']:x for x in output['retainedFindingCoverage']}
    if len(finding_rows)!=len(output['retainedFindingCoverage']) or set(finding_rows)!={f['id'] for f in retained_ledger(packet)}:reject('trial-retained-finding-loss')
    for row in finding_rows.values():
        if not row['concernIds'] or not set(row['concernIds'])<=set(concerns):reject('trial-retained-finding-loss')
        if row['status']=='resolved' and any(concerns[c]['status']!='resolved' for c in row['concernIds']):reject('trial-false-resolution')
    if output['status']=='complete' and (any(r['status'] in export_contract.BLOCKED for r in rows.values()) or any(r[k]!='checked' for r in reviews.values() for k in REVIEW_AXES) or any(c['status']=='open' for c in concerns.values()) or any(f['severity']=='blocking' and f['disposition']=='unresolved' for f in maps['findings'].values()) or any(r['status']=='unresolved' for r in nonclaims.values())):reject('trial-false-completion')
    return output


def receipt_checkpoint(receipt):return digest({k:v for k,v in receipt.items() if k not in {'checkpointSha256','receiptSha256'}})


def task_identity(launch):
    # The coordinator can continue in later turns; its independently observed
    # effective settings, identity, request, and fork state must remain exact.
    return {**launch,'observed':{k:v for k,v in launch['observed'].items() if k not in {'turnId','firstTurn'}}}


def validate_receipt(receipt,stage_input,output,decision_digest,prior_receipts):
    expected_keys={'schema','fixtureClass','stage','stageInputSha256','outputSha256','decisionSha256','methodRegistrySha256','packetSha256','sourceRecordVersionIds','upstreamReceiptSha256','task','worker','checkpointSha256','receiptSha256'}
    if set(receipt)!=expected_keys or receipt['schema']!='al-isabah.knowledge-local-trial-receipt.v2':reject('trial-receipt-shape-mismatch')
    for key,value in [('fixtureClass',stage_input['fixtureClass']),('stage',stage_input['stage']),('stageInputSha256',digest(stage_input)),('outputSha256',digest(output)),('decisionSha256',decision_digest),('methodRegistrySha256',stage_input['methodRegistrySha256']),('packetSha256',stage_input['packetSha256']),('sourceRecordVersionIds',stage_input['sourceRecordVersionIds']),('upstreamReceiptSha256',[r['receiptSha256'] for r in prior_receipts])]:
        if receipt[key]!=value:reject('trial-receipt-binding-mismatch')
    launch_schema=read(method.SCHEMA_PATH)
    launch_schema['properties']['worker']['properties']['observed']=read(WORKER_OBSERVATION)
    if any(validate_schema_instance(receipt[k],launch_schema['properties'][k]) for k in ('task','worker')):reject('trial-host-mismatch')
    config=method.configuration(read(method.REGISTRY_PATH))
    if host_runtime.launch_errors(receipt['task'],config,'codex-task') or host_runtime.launch_errors(receipt['worker'],config,'codex-worker'):reject('trial-host-mismatch')
    if receipt['task']['request']!=stage_input['taskRequest'] or receipt['worker']['request']!=stage_input['workerRequest']:reject('trial-host-mismatch')
    if receipt['worker']['observed']['parentSessionId']!=receipt['task']['observed']['sessionId']:reject('trial-worker-parent-mismatch')
    old_sessions={r['worker']['observed']['sessionId'] for r in prior_receipts}|{receipt['task']['observed']['sessionId']}
    if receipt['worker']['observed']['sessionId'] in old_sessions or any(task_identity(r['task'])!=task_identity(receipt['task']) for r in prior_receipts):reject('trial-worker-independence-mismatch')
    if receipt_checkpoint(receipt)!=receipt['checkpointSha256'] or digest({k:v for k,v in receipt.items() if k!='receiptSha256'})!=receipt['receiptSha256']:reject('trial-receipt-binding-mismatch')
    return receipt


def prepare_stage(stage,decision,expected_digest,packet,metadata,commit,prior=()):
    request=authorize(decision,expected_digest,packet,metadata,commit)
    if stage not in STAGES or len(prior)!=STAGES.index(stage):reject('trial-stage-order-mismatch')
    validated=[]
    for n,item in enumerate(prior):
        expected_input=prepare_stage(STAGES[n],decision,expected_digest,packet,metadata,commit,prior[:n])
        if item['input']!=expected_input:reject('trial-stage-input-drift')
        validate_output(item['output'],expected_input,packet)
        validate_receipt(item['receipt'],expected_input,item['output'],expected_digest,[x['receipt'] for x in validated])
        validated.append(item)
    return stage_input_value(stage,request,expected_digest,packet,metadata,validated)


def stage_input_value(stage,request,expected_digest,packet,metadata,validated,instructions=None):
    return {'schema':'al-isabah.knowledge-local-trial-stage-input.v1','fixtureClass':request['fixtureClass'],'stage':stage,'decisionSha256':expected_digest,'packetSha256':packet['packetSha256'],'partitionSha256':metadata['partitionSha256'],'methodRegistrySha256':request['methodRegistrySha256'],'profileSha256':request['profileSha256'],'outputSchemaSha256':request['outputSchemaSha256'],'taskRequest':request['taskRequest'],'workerRequest':request['workerRequest'],'sourceRecordVersionIds':sorted(r['id'] for r in packet['records']),'lockedInput':copy.deepcopy(packet),'profile':read(PROFILE),'outputSchema':read(SCHEMA),'artifacts':artifact_inputs(packet),'retainedFindingLedger':retained_ledger(packet),'instructions':RUNBOOK.read_text(encoding='utf-8-sig') if instructions is None else instructions,'priorOutputs':[x['output'] for x in validated],'priorReceiptSha256':[x['receipt']['receiptSha256'] for x in validated]}


def capture(stage_input,output,packet,decision_digest,task,worker,prior_receipts):
    validate_output(output,stage_input,packet)
    receipt={'schema':'al-isabah.knowledge-local-trial-receipt.v2','fixtureClass':stage_input['fixtureClass'],'stage':stage_input['stage'],'stageInputSha256':digest(stage_input),'outputSha256':digest(output),'decisionSha256':decision_digest,'methodRegistrySha256':stage_input['methodRegistrySha256'],'packetSha256':packet['packetSha256'],'sourceRecordVersionIds':stage_input['sourceRecordVersionIds'],'upstreamReceiptSha256':[r['receiptSha256'] for r in prior_receipts],'task':task,'worker':worker,'checkpointSha256':'','receiptSha256':''}
    receipt['checkpointSha256']=receipt_checkpoint(receipt);receipt['receiptSha256']=digest({k:v for k,v in receipt.items() if k!='receiptSha256'})
    return validate_receipt(receipt,stage_input,output,decision_digest,prior_receipts)


def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=canonical(value):reject('trial-existing-output-conflict')
    else:
        with path.open('xb') as stream:stream.write(canonical(value))


def require_runtime_directory(directory):
    base=ROOT.resolve()/'.runtime/knowledge/issue-0089'
    resolved=directory.resolve()
    if not resolved.is_relative_to(base):reject('trial-output-boundary-mismatch')
    git('check-ignore','--quiet',str(resolved.relative_to(ROOT.resolve())))


def final_report(decision,decision_digest,packet,metadata,commit,stages):
    if len(stages)!=len(STAGES):reject('trial-stage-order-mismatch')
    prior=[]
    for stage,item in zip(STAGES,stages):
        expected=prepare_stage(stage,decision,decision_digest,packet,metadata,commit,prior)
        if item['input']!=expected:reject('trial-stage-input-drift')
        validate_output(item['output'],expected,packet)
        validate_receipt(item['receipt'],expected,item['output'],decision_digest,[x['receipt'] for x in prior])
        prior.append(item)
    output=stages[-1]['output']
    return {'schema':'al-isabah.knowledge-local-trial-validation.v1','fixtureClass':stages[0]['input']['fixtureClass'],'status':output['status'],'decisionSha256':decision_digest,'codeCommit':commit,'packetSha256':packet['packetSha256'],'partitionSha256':metadata['partitionSha256'],'stageOutputSha256':[digest(x['output']) for x in stages],'stageReceiptSha256':[x['receipt']['receiptSha256'] for x in stages],'counts':{'records':len(packet['records']),'sourceSpans':sum(len(u['spans']) for u in packet['units']),'representedSpans':sum(r['status'] not in export_contract.BLOCKED for r in output['spanDispositions']),'blockedSpans':sum(r['status'] in export_contract.BLOCKED for r in output['spanDispositions']),'retainedFindings':len(retained_ledger(packet)),'openConcerns':sum(c['status']=='open' for c in output['concerns']),'claims':len(output['claims']),'names':len(output['names'])},'humanReview':'unreviewed','publicReleaseAuthorized':False,'consumerAdmissionAuthorized':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['request','prepare','capture','report']);p.add_argument('--packet',type=Path,default=assembly.DEFAULT_PACKET);p.add_argument('--partition',type=Path,default=assembly.DEFAULT_METADATA);p.add_argument('--decision',type=Path);p.add_argument('--decision-sha256');p.add_argument('--stage',choices=STAGES);p.add_argument('--directory',type=Path,default=ROOT/'.runtime/knowledge/issue-0089/trial')
    for key in ('task-log','worker-log','task-request','worker-request'):p.add_argument('--'+key,type=Path)
    for key in ('task-session','worker-session','task-turn','worker-turn'):p.add_argument('--'+key)
    args=p.parse_args()
    try:
        require_runtime_directory(args.directory)
        packet=read(args.packet);metadata=read(args.partition);commit=git('rev-parse','HEAD').decode().strip()
        if args.action=='request':
            value=decision_request(packet,metadata,commit);write_new(args.directory/'decision-request.json',value);print(digest(value));return 0
        if not args.decision or not args.decision_sha256:reject('trial-authorization-inputs-required')
        decision=read(args.decision)
        if args.action=='report':
            stages=[{key:read(args.directory/(stage+'.'+key+'.json')) for key in ('input','output','receipt')} for stage in STAGES]
            value=final_report(decision,args.decision_sha256,packet,metadata,commit,stages);write_new(args.directory/'validation-report.json',value);print(value['status']);print(digest(value));return 0
        if not args.stage:reject('trial-stage-required')
        prior=[]
        for stage in STAGES[:STAGES.index(args.stage)]:
            prior.append({key:read(args.directory/(stage+'.'+key+'.json')) for key in ('input','output','receipt')})
        stage_input=prepare_stage(args.stage,decision,args.decision_sha256,packet,metadata,commit,prior)
        input_path=args.directory/(args.stage+'.input.json')
        if args.action=='prepare':write_new(input_path,stage_input);print(digest(stage_input));return 0
        if read(input_path)!=stage_input:reject('trial-stage-input-drift')
        if not all([args.task_log,args.worker_log,args.task_request,args.worker_request,args.task_session,args.worker_session,args.task_turn,args.worker_turn]):reject('trial-host-inputs-required')
        task={'request':read(args.task_request),'observed':host_runtime.observe_session(args.task_log,args.task_session,args.task_turn)}
        worker={'request':read(args.worker_request),'observed':host_runtime.observe_session(args.worker_log,args.worker_session,args.worker_turn,expected_parent_session_id=task['observed']['sessionId'])}
        output=read(args.directory/(args.stage+'.output.json'))
        receipt=capture(stage_input,output,packet,args.decision_sha256,task,worker,[x['receipt'] for x in prior]);write_new(args.directory/(args.stage+'.receipt.json'),receipt);print(receipt['receiptSha256']);return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError):print('local-trial-operation-rejected');return 1

if __name__=='__main__':raise SystemExit(main())
