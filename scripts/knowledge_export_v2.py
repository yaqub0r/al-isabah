#!/usr/bin/env python3
"""Executable draft v2 conformance only. Real semantic execution/intake disabled."""
from __future__ import annotations
import argparse
import copy
import datetime
from pathlib import Path
from knowledge_export import canonical, digest, read, shape, schema_vocabulary, Rejection, reject
from public_boundary import boundary_errors

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / 'schemas/al-isabah-knowledge-export.v2-draft.schema.json'
COLLECTIONS = ('sourceRecords','assessments','actors','artifacts','entities','mentions','reports','events','claims','ambiguityGroups','spanDispositions','lifecycleEvents','values','places','times','qualifications','attributions','useRestrictions','findings')
BLOCKED = {'unsupported_semantics','unprocessed','source_or_mapping_blocked'}
LIST_REFS = {'authorityUnitIds':'sourceUnits','sourceRecordVersionIds':'sourceRecords','mentionIds':'mentions','identityAssessmentIds':'assessments','ambiguityGroupIds':'ambiguityGroups','sourceSpanIds':'sourceSpans','attributorEntityIds':'entities','entityIds':'entities','claimIds':'claims','criticalAssessmentIds':'assessments','placeIds':'places','timeIds':'times','reportIds':'reports','qualificationIds':'qualifications','assessmentIds':'assessments','attributionIds':'attributions','useRestrictionIds':'useRestrictions','predecessorIds':'assessments','findingIds':'findings','artifactIds':'artifacts','evidenceArtifactIds':'artifacts','evaluatorEntityIds':'entities','dependencyIds':'lifecycleEvents'}
SINGLE_REFS = {'logicalRecordId':'logicalRecords','sourceArtifactId':'artifacts','actorId':'actors','methodArtifactId':'artifacts','authorityArtifactId':'artifacts','entityId':'entities','sourceRecordVersionId':'sourceRecords','sourceSpanId':'sourceSpans','subjectId':'entities','decisionArtifactId':'artifacts','extractionAssessmentId':'assessments','humanReviewAssessmentId':'assessments'}

def indexed(items):
    result = {x['id']: x for x in items}
    if len(result) != len(items): reject('immutable-id-conflict')
    return result


def validate_date(value):
    if value['status'] == 'unknown':
        if value['timestamp'] or value['reasonCode'] == 'none': reject('assessment-time-invalid')
    else:
        if not value['timestamp'] or value['reasonCode'] != 'none': reject('assessment-time-invalid')
        try: datetime.datetime.strptime(value['timestamp'], '%Y-%m-%dT%H:%M:%SZ')
        except ValueError: reject('assessment-time-invalid')


def validate_refs(value, maps):
    if isinstance(value, list):
        for child in value: validate_refs(child, maps)
    elif isinstance(value, dict):
        if set(value) == {'kind','id'}:
            if value['kind'] not in maps or value['id'] not in maps[value['kind']]: reject('missing-reference')
        for key, child in value.items():
            if key in LIST_REFS and not set(child) <= maps[LIST_REFS[key]].keys(): reject('missing-reference')
            if key in SINGLE_REFS and child not in maps[SINGLE_REFS[key]]: reject('missing-reference')
            validate_refs(child, maps)


def no_cycles(edges):
    active, done = set(), set()
    def visit(node):
        if node in active: reject('lifecycle-conflict')
        if node in done: return
        active.add(node)
        for nxt in edges.get(node, []): visit(nxt)
        active.remove(node); done.add(node)
    for node in edges: visit(node)


def validate_snapshot(snapshot, inventory, profile, trust):
    schema = read(SCHEMA_PATH)
    schema_vocabulary(schema)
    for name, value in [('snapshot',snapshot),('inventory',inventory),('profile',profile),('trust',trust)]:
        shape(value, schema['$defs'][name], schema)
        if boundary_errors(value): reject('prohibited-payload')
    if snapshot['mode'] != 'synthetic' or profile['mode'] != 'synthetic': reject('real-mode-disabled')
    if snapshot['fixtureClass'] != 'synthetic-conformance': reject('real-mode-disabled')
    expected = {'schemaId':'al-isabah.knowledge-draft-trust.v2','fixtureClass':'synthetic-conformance','snapshotSha256':digest(snapshot),'inventorySha256':digest(inventory),'profileSha256':digest(profile),'schemaSha256':digest(schema)}
    if trust != expected: reject('external-pin-mismatch')
    if snapshot['profileSha256'] != digest(profile) or snapshot['inventorySha256'] != digest(inventory): reject('external-pin-mismatch')
    if snapshot['authority'] != inventory['authority'] or profile['authority'] != inventory['authority'] or profile['selectedScopeSha256'] != inventory['selectedScopeSha256']: reject('source-identity-mismatch')
    if inventory['authority']['verificationBasis'] != 'synthetic' or inventory['reconciliationStatus'] != 'synthetic' or profile['rights']['basis'] != 'synthetic_testing_only': reject('real-mode-disabled')
    def synthetic_ids(value):
        if isinstance(value, str) and value.startswith('urn:al-isabah:') and not value.startswith('urn:al-isabah:synthetic:'): reject('real-mode-disabled')
        if isinstance(value, dict):
            for child in value.values(): synthetic_ids(child)
        elif isinstance(value, list):
            for child in value: synthetic_ids(child)
    for value in (snapshot, inventory, profile): synthetic_ids(value)
    maps = {key:indexed(snapshot[key]) for key in COLLECTIONS}
    for key in ('sourceUnits','logicalRecords','sourceSpans'): maps[key] = indexed(inventory[key])
    all_ids = [x for m in maps.values() for x in m]
    if len(all_ids) != len(set(all_ids)): reject('immutable-id-conflict')
    for key in COLLECTIONS:
        # Deterministic order is contract-level; transmission has its own order.
        if snapshot[key] != sorted(snapshot[key], key=lambda x:x['id']): reject('noncanonical-order')
        validate_refs(snapshot[key], maps)
    validate_refs(snapshot['assessmentSelection'], maps)
    records, units, logical, spans = (maps[k] for k in ('sourceRecords','sourceUnits','logicalRecords','sourceSpans'))
    owners = {}
    for item in logical.values():
        if not item['sourceUnitIds'] or not set(item['sourceUnitIds']) <= units.keys(): reject('coverage-mismatch')
        for unit_id in item['sourceUnitIds']:
            if unit_id in owners or units[unit_id]['inScope'] != item['inScope']: reject('coverage-mismatch')
            owners[unit_id] = item['id']
    if set(owners) != set(units): reject('coverage-mismatch')
    for unit in units.values():
        if unit['ownerEntryId'] not in units or units[unit['ownerEntryId']]['kind'] != 'entry': reject('missing-reference')
        if unit['kind'] == 'entry' and unit['ownerEntryId'] != unit['id']: reject('source-identity-mismatch')
        if owners[unit['ownerEntryId']] != owners[unit['id']]: reject('source-identity-mismatch')
    if {r['logicalRecordId'] for r in records.values()} != set(logical) or len(records) != len(logical): reject('coverage-mismatch')
    for record in records.values():
        if set(record['authorityUnitIds']) != set(logical[record['logicalRecordId']]['sourceUnitIds']): reject('source-identity-mismatch')
        if maps['artifacts'][record['sourceArtifactId']]['kind'] not in {'source_derivation','source_release'}: reject('reference-kind-mismatch')
    if any(x['sourceUnitId'] not in units for x in spans.values()) or {x['sourceUnitId'] for x in spans.values()} != set(units): reject('coverage-mismatch')
    batch = snapshot['batch']
    requested = sorted(r['id'] for r in logical.values() if r['inScope'])
    dependencies = sorted(r['id'] for r in logical.values() if not r['inScope'])
    if batch['requestedLogicalRecordIds'] != requested or batch['dependencyLogicalRecordIds'] != dependencies: reject('batch-declaration-mismatch')
    if any(a['status'] != 'synthetic_only' for a in maps['artifacts'].values()): reject('real-mode-disabled')

    def span_sources(span_ids, record_ids):
        owned = {u for r in record_ids for u in records[r]['authorityUnitIds']}
        if not set(span_ids) <= spans.keys() or any(spans[s]['sourceUnitId'] not in owned for s in span_ids): reject('source-identity-mismatch')
    for mention in maps['mentions'].values():
        span_sources([mention['sourceSpanId']],[mention['sourceRecordVersionId']])
        if mention['id'] not in maps['entities'][mention['entityId']]['mentionIds']: reject('reference-closure-mismatch')
    for entity in maps['entities'].values():
        if not entity['sourceRecordVersionIds']: reject('source-identity-mismatch')
        if any(maps['mentions'][m]['entityId'] != entity['id'] for m in entity['mentionIds']): reject('reference-closure-mismatch')
    predicates = indexed(profile['predicates'])
    for claim in maps['claims'].values():
        if not claim['sourceRecordVersionIds'] or not claim['sourceSpanIds'] or not claim['reportIds']: reject('source-identity-mismatch')
        span_sources(claim['sourceSpanIds'],claim['sourceRecordVersionIds'])
        pred = predicates.get(claim['predicateId'])
        if pred is None: reject('unapproved-predicate')
        if maps['entities'][claim['subjectId']]['kind'] not in pred['subjectKinds'] or claim['objectRef']['kind'] not in pred['objectKinds']: reject('reference-kind-mismatch')
        if claim['objectRef']['kind'] == 'entities' and maps['entities'][claim['objectRef']['id']]['kind'] not in pred['objectEntityKinds']: reject('reference-kind-mismatch')
        for report_id in claim['reportIds']:
            if claim['id'] not in maps['reports'][report_id]['claimIds']: reject('reference-closure-mismatch')
        quals = [maps['qualifications'][i] for i in claim['qualificationIds']]
        for q in quals:
            if {'kind':'claims','id':claim['id']} not in q['targets']: reject('qualification-loss')
        factual = any(maps['useRestrictions'][i]['tier']=='factual_spine' for i in claim['useRestrictionIds'])
        if factual and (claim['polarity'] == 'absence_of_evidence' or claim['assertionClass'] != 'source_attested' or claim['modality'] != 'asserted' or claim['ambiguityGroupIds'] or any(q['criticalStatus'] != 'unqualified' or q['evidentiaryStrength'] != 'source_supported' for q in quals)): reject('qualification-loss')
    for report in maps['reports'].values():
        if not report['sourceRecordVersionIds'] or not report['sourceSpanIds']: reject('source-identity-mismatch')
        span_sources(report['sourceSpanIds'],report['sourceRecordVersionIds'])
        if any(report['id'] not in maps['claims'][c]['reportIds'] for c in report['claimIds']): reject('reference-closure-mismatch')
        if [x['position'] for x in report['transmission']] != list(range(len(report['transmission']))): reject('transmission-order-mismatch')
        for t in report['transmission']:
            if (t['role']=='unresolved' and not t['ambiguityGroupIds']) or (t['role']!='unresolved' and not t['entityIds']): reject('qualification-loss')
    for event in maps['events'].values():
        if event['typeId'] not in profile['eventTypes'] or any(p['roleId'] not in profile['participantRoles'] for p in event['participantRoles']): reject('unapproved-role')
    for time in maps['times'].values():
        if time['earliest'] > time['latest']: reject('time-interval-invalid')
    for group in maps['ambiguityGroups'].values():
        for member in group['members']:
            value = maps[member['kind']][member['id']]
            if 'ambiguityGroupIds' not in value or group['id'] not in value['ambiguityGroupIds']: reject('ambiguity-incomplete')
        expected_members = {(key,x['id']) for key in COLLECTIONS for x in maps[key].values() if group['id'] in x.get('ambiguityGroupIds',[]) and key != 'spanDispositions'}
        if expected_members != {(r['kind'],r['id']) for r in group['members']}: reject('ambiguity-incomplete')
    assessment_edges = {}
    for assessment in maps['assessments'].values():
        if not assessment['targets']: reject('assessment-binding-mismatch')
        for inp in assessment['inputs']:
            target=maps[inp['ref']['kind']][inp['ref']['id']]
            if digest(target) != inp['sha256']: reject('assessment-binding-mismatch')
        if not all(target in [i['ref'] for i in assessment['inputs']] for target in assessment['targets']): reject('assessment-binding-mismatch')
        validate_date(assessment['effectiveAt']); validate_date(assessment['observedAt'])
        if maps['artifacts'][assessment['methodArtifactId']]['kind'] != 'method': reject('reference-kind-mismatch')
        if assessment['kind']=='human_review' and assessment['status']=='reviewed':
            if maps['actors'][assessment['actorId']]['kind'] != 'human' or assessment['observedAt']['status'] != 'recorded': reject('human-review-inferred')
        if assessment['kind']=='human_review' and assessment['status'] not in {'reviewed','unreviewed'}: reject('human-review-inferred')
        for predecessor in assessment['predecessorIds']:
            old=maps['assessments'][predecessor]
            if old['kind'] != assessment['kind'] or old['targets'] != assessment['targets']: reject('assessment-binding-mismatch')
        assessment_edges[assessment['id']] = assessment['predecessorIds']
    no_cycles(assessment_edges)
    retired_assessments = {p for a in maps['assessments'].values() for p in a['predecessorIds']}
    by_span={}
    reasons={'represented':{'mapped'},'represented_uncertain':{'uncertain'},'structural_only':{'heading'},'nonclaim_form':{'formula_only','bibliographic_format'},'unsupported_semantics':{'unsupported'},'unprocessed':{'pending'},'source_or_mapping_blocked':{'source_damage','mapping_unverified'}}
    for disposition in maps['spanDispositions'].values():
        sid=disposition['sourceSpanId']
        if sid in by_span: reject('coverage-mismatch')
        by_span[sid]=disposition
        owner_record = next(r for r in records.values() if spans[sid]['sourceUnitId'] in r['authorityUnitIds'])
        if not any({'kind':'sourceRecords','id':owner_record['id']} in maps['assessments'][a]['targets'] for a in disposition['assessmentIds']): reject('assessment-binding-mismatch')
        if disposition['status']=='nonclaim_form':
            positive = [maps['assessments'][a] for a in disposition['assessmentIds']]
            if not any(a['kind'] in {'independent_review','adjudication'} and a['status']=='complete' and {'kind':'spanDispositions','id':disposition['id']} in a['targets'] and {'kind':'sourceRecords','id':owner_record['id']} in a['targets'] for a in positive): reject('nonclaim-review-required')
        if disposition['reasonCode'] not in reasons[disposition['status']] or disposition['reasonCode'] not in profile['reasonCodes']: reject('disposition-mismatch')
        if disposition['status']=='structural_only' and units[spans[sid]['sourceUnitId']]['kind']=='entry': reject('disposition-mismatch')
        if disposition['status'] in {'represented','represented_uncertain'} and not disposition['claimIds'] and not disposition['reportIds']: reject('disposition-mismatch')
        if disposition['status']=='represented_uncertain' and not disposition['ambiguityGroupIds']: reject('ambiguity-incomplete')
        if disposition['status'] in {'structural_only','nonclaim_form','unprocessed'} and (disposition['claimIds'] or disposition['reportIds']): reject('disposition-mismatch')
        for key in ('claims','reports'):
            ids=disposition['claimIds' if key=='claims' else 'reportIds']
            if any(sid not in maps[key][i]['sourceSpanIds'] for i in ids): reject('source-identity-mismatch')
    if set(by_span) != set(spans): reject('coverage-mismatch')
    for key in ('claims','reports'):
        for value in maps[key].values():
            for sid in value['sourceSpanIds']:
                if value['id'] not in by_span[sid]['claimIds' if key=='claims' else 'reportIds']: reject('reference-closure-mismatch')
    selections={s['sourceRecordVersionId']:s for s in snapshot['assessmentSelection']}
    if len(selections)!=len(snapshot['assessmentSelection']) or set(selections)!=set(records): reject('coverage-mismatch')
    for rid, selection in selections.items():
        for field, kind in [('extractionAssessmentId','extraction'),('humanReviewAssessmentId','human_review')]:
            a=maps['assessments'][selection[field]]
            if a['id'] in retired_assessments: reject('stale-assessment-selection')
            if a['kind'] != kind or {'kind':'sourceRecords','id':rid} not in a['targets']: reject('assessment-binding-mismatch')
        a=maps['assessments'][selection['extractionAssessmentId']]
        if a['status'] not in {'complete','partial','not_started'}: reject('assessment-binding-mismatch')
        states=[by_span[s['id']]['status'] for s in spans.values() if s['sourceUnitId'] in records[rid]['authorityUnitIds']]
        if a['status']=='complete' and any(x in BLOCKED for x in states): reject('false-extraction-completion')
        if a['status']=='not_started' and any(x!='unprocessed' for x in states): reject('false-extraction-completion')
    retired, edges = set(), {}
    for event in maps['lifecycleEvents'].values():
        validate_date(event['effectiveAt'])
        if maps['artifacts'][event['decisionArtifactId']]['kind'] != 'review_decision': reject('reference-kind-mismatch')
        targets={(x['kind'],x['id']) for x in event['targets']}; replacements={(x['kind'],x['id']) for x in event['replacements']}
        if event['kind'] in {'entity_split','entity_merge'}:
            if any(kind!='entities' for kind,_ in targets | replacements): reject('reference-kind-mismatch')
            if event['kind']=='entity_split' and (len(targets)!=1 or len(replacements)<2): reject('lifecycle-conflict')
            if event['kind']=='entity_merge' and (len(targets)<2 or len(replacements)!=1): reject('lifecycle-conflict')
        elif event['kind'] != 'withdraws' and {kind for kind,_ in targets} != {kind for kind,_ in replacements}: reject('reference-kind-mismatch')
        if targets & replacements or targets & retired: reject('lifecycle-conflict')
        if event['kind']=='withdraws' and replacements: reject('lifecycle-conflict')
        if event['kind']!='withdraws' and not replacements: reject('lifecycle-conflict')
        retired |= targets
        for target in targets: edges[target]=list(replacements)
    no_cycles(edges)
    no_cycles({e['id']:e['dependencyIds'] for e in maps['lifecycleEvents'].values()})
    # Historical evidence retains retired references; current-use objects do not.
    audit_collections = {'assessments','spanDispositions','ambiguityGroups','lifecycleEvents','findings','qualifications'}
    def active_refs(value, skip=frozenset()):
        found=set()
        if isinstance(value,list):
            for child in value: found |= active_refs(child)
        elif isinstance(value,dict):
            if set(value)=={'kind','id'}: found.add((value['kind'],value['id']))
            for key,child in value.items():
                if key in skip: continue
                if key in LIST_REFS: found |= {(LIST_REFS[key],i) for i in child}
                if key in SINGLE_REFS: found.add((SINGLE_REFS[key],child))
                found |= active_refs(child)
        return found
    for key in COLLECTIONS:
        if key in audit_collections: continue
        for item in maps[key].values():
            if (key,item['id']) in retired: continue
            if active_refs(item, {'claimIds'} if key=='reports' else set()) & retired: reject('active-reference-retired')
    for selection in snapshot['assessmentSelection']:
        if active_refs(selection) & retired: reject('active-reference-retired')
        for key in ('extractionAssessmentId','humanReviewAssessmentId'):
            current=maps['assessments'][selection[key]]
            if active_refs(current,{'targets','inputs','predecessorIds'}) & retired: reject('active-reference-retired')
    return maps


def coverage(snapshot, inventory):
    logical={r['id']:r for r in inventory['logicalRecords']}
    selected_units={u['id'] for u in inventory['sourceUnits'] if u['inScope']}
    selected_spans={s['id'] for s in inventory['sourceSpans'] if s['sourceUnitId'] in selected_units}
    dispositions=[s for s in snapshot['spanDispositions'] if s['sourceSpanId'] in selected_spans]
    amap=indexed(snapshot['assessments']); rmap=indexed(snapshot['sourceRecords'])
    complete=sum(amap[s['extractionAssessmentId']]['status']=='complete' for s in snapshot['assessmentSelection'] if logical[rmap[s['sourceRecordVersionId']]['logicalRecordId']]['inScope'])
    return {'requestedLogicalRecords':sum(x['inScope'] for x in logical.values()),'dependencyLogicalRecords':sum(not x['inScope'] for x in logical.values()),'sourceUnits':len(selected_units),'entries':sum(u['inScope'] and u['kind']=='entry' for u in inventory['sourceUnits']),'structuralUnits':sum(u['inScope'] and u['kind']!='entry' for u in inventory['sourceUnits']),'expectedSpans':len(selected_spans),'representedSpans':sum(x['status'] not in BLOCKED for x in dispositions),'uncertainSpans':sum(x['status']=='represented_uncertain' for x in dispositions),'blockedSpans':sum(x['status'] in BLOCKED for x in dispositions),'extractionCompleteRecords':complete,'assessmentVersions':len(snapshot['assessments']),'claims':len(snapshot['claims']),'scopeExtractionComplete':complete==sum(x['inScope'] for x in logical.values()) and not any(x['status'] in BLOCKED for x in dispositions)}


def build(snapshot, inventory, profile, trust, batch_id):
    validate_snapshot(snapshot, inventory, profile, trust)
    batch=snapshot['batch']
    if batch_id != batch['id']: reject('undeclared-batch')
    payload={'schemaId':'al-isabah.knowledge-export.v2','exportId':batch['exportId'],'batchId':batch_id,'snapshotId':snapshot['id'],'snapshotSha256':digest(snapshot),'selection':copy.deepcopy(batch),'coverage':coverage(snapshot,inventory)}
    for key in ('schemaVersion','mode','fixtureClass','profileSha256','inventorySha256','authority','assessmentSelection',*COLLECTIONS): payload[key]=copy.deepcopy(snapshot[key])
    payload['payloadSha256']=digest(payload)
    shape(payload,read(SCHEMA_PATH))
    return payload


def validate_payload(payload, snapshot, inventory, profile, trust):
    shape(payload,read(SCHEMA_PATH))
    if payload['mode'] != 'synthetic': reject('real-mode-disabled')
    expected=build(snapshot,inventory,profile,trust,payload['batchId'])
    if payload != expected: reject('batch-content-mismatch')
    return payload


def replay_identity(payloads):
    """Draft immutable-ID audit only, not consumer admission/current validity."""
    bindings={}; seen=set()
    for payload in payloads:
        shape(payload,read(SCHEMA_PATH))
        if payload['mode']!='synthetic': reject('real-mode-disabled')
        if digest({k:v for k,v in payload.items() if k!='payloadSha256'})!=payload['payloadSha256']: reject('payload-digest-mismatch')
        for kind, identity, value in [('export',payload['exportId'],payload),('batch',payload['batchId'],payload)]+[(key,x['id'],x) for key in COLLECTIONS for x in payload[key]]:
            key=(kind,identity); pin=digest(value)
            if key in bindings and bindings[key]!=pin: reject('immutable-id-conflict')
            bindings[key]=pin
        seen.add(payload['exportId'])
    return {'uniqueExports':len(seen),'bindings':bindings}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot','inventory','profile','trust','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--batch',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
    try:
        data=build(read(a.snapshot),read(a.inventory),read(a.profile),read(a.trust),a.batch); encoded=canonical(data)
        if a.check:
            if a.output.read_bytes()!=encoded: reject('noncanonical-output')
        else:
            a.output.parent.mkdir(parents=True,exist_ok=True)
            with a.output.open('xb') as f:f.write(encoded)
        print(data['payloadSha256']);return 0
    except Rejection as e: print(str(e));return 1
    except (OSError,ValueError,KeyError,TypeError,RecursionError):print('input-output-error');return 1

if __name__=='__main__': raise SystemExit(main())
