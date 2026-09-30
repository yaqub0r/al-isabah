"""Frozen draft3 graph validation with only the real artifact-status guard changed.

This body is deliberately copied, not imported through a synthetic-mode bypass.
A regression test compares it to the frozen body, allowing only that guard.
Receipt arguments are validated exporter-derived projections, not worker receipts.
"""
from knowledge_export_v2_draft3 import *


def validate_semantics(snapshot,inventory,profile,receipt_bundle,receipts):
    maps = {key:indexed(snapshot[key]) for key in COLLECTIONS}
    for key in ('sourceUnits','logicalRecords','sourceSpans'): maps[key] = indexed(inventory[key])
    all_ids = [x for m in maps.values() for x in m]
    if len(all_ids) != len(set(all_ids)): reject('immutable-id-conflict')
    for key in COLLECTIONS:
        # Deterministic order is contract-level; transmission has its own order.
        if snapshot[key] != sorted(snapshot[key], key=lambda x:x['id']): reject('noncanonical-order')
        validate_refs(snapshot[key], maps)
    for key in ('assessmentSelection','currentSourceSelection','currentSpanDispositionSelection'): validate_refs(snapshot[key], maps)
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
    current={x['logicalRecordId']:x['sourceRecordVersionId'] for x in snapshot['currentSourceSelection']}
    if len(current)!=len(snapshot['currentSourceSelection']) or set(current)!=set(logical): reject('coverage-mismatch')
    if any(records[r]['logicalRecordId']!=l for l,r in current.items()): reject('source-identity-mismatch')
    if {r['logicalRecordId'] for r in records.values()}!=set(logical): reject('coverage-mismatch')
    for record in records.values():
        if set(record['authorityUnitIds']) != set(logical[record['logicalRecordId']]['sourceUnitIds']): reject('source-identity-mismatch')
        if maps['artifacts'][record['sourceArtifactId']]['kind'] not in {'source_derivation','source_release'}: reject('reference-kind-mismatch')
    if any(x['sourceUnitId'] not in units for x in spans.values()) or {x['sourceUnitId'] for x in spans.values()} != set(units): reject('coverage-mismatch')
    batch = snapshot['batch']
    requested = sorted(r['id'] for r in logical.values() if r['inScope'])
    dependencies = sorted(r['id'] for r in logical.values() if not r['inScope'])
    if batch['requestedLogicalRecordIds'] != requested or batch['dependencyLogicalRecordIds'] != dependencies: reject('batch-declaration-mismatch')
    if any(a['status'] not in {'proposed','approved'} for a in maps['artifacts'].values()): reject('local-artifact-status-mismatch')

    def span_sources(span_ids, record_ids):
        owned = {u for r in record_ids for u in records[r]['authorityUnitIds']}
        if not set(span_ids) <= spans.keys() or any(spans[s]['sourceUnitId'] not in owned for s in span_ids): reject('source-identity-mismatch')
    for mention in maps['mentions'].values():
        span_sources([mention['sourceSpanId']],[mention['sourceRecordVersionId']])
        if mention['id'] not in maps['entities'][mention['entityId']]['mentionIds']: reject('reference-closure-mismatch')
    validate_names(maps,span_sources)
    for entity in maps['entities'].values():
        if not entity['sourceRecordVersionIds']: reject('source-identity-mismatch')
        if any(maps['mentions'][m]['entityId'] != entity['id'] for m in entity['mentionIds']): reject('reference-closure-mismatch')
    validate_profile_domains(profile)
    validate_value_place_domains(maps,profile)
    predicates = indexed(profile['predicates'])
    for claim in maps['claims'].values():
        if not claim['sourceRecordVersionIds'] or not claim['sourceSpanIds'] or not claim['reportIds']: reject('source-identity-mismatch')
        span_sources(claim['sourceSpanIds'],claim['sourceRecordVersionIds'])
        pred = predicates.get(claim['predicateId'])
        if pred is None: reject('unapproved-predicate')
        validate_claim_domain(claim,pred,maps)
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
    selected_rows={}
    expected_pairs={(rid,s['id']) for rid in current.values() for s in spans.values() if s['sourceUnitId'] in records[rid]['authorityUnitIds']}
    for selection in snapshot['currentSpanDispositionSelection']:
        pair=(selection['sourceRecordVersionId'],selection['sourceSpanId'])
        row=maps['spanDispositions'][selection['spanDispositionId']]
        if pair in selected_rows: reject('coverage-mismatch')
        if (row['sourceRecordVersionId'],row['sourceSpanId'])!=pair: reject('source-identity-mismatch')
        selected_rows[pair]=row
    if set(selected_rows)!=expected_pairs: reject('coverage-mismatch')
    reasons={'represented':{'mapped'},'represented_uncertain':{'uncertain'},'structural_only':{'heading'},'nonclaim_form':{'formula_only','bibliographic_format'},'unsupported_semantics':{'unsupported'},'unprocessed':{'pending'},'source_or_mapping_blocked':{'source_damage','mapping_unverified'}}
    for disposition in maps['spanDispositions'].values():
        sid=disposition['sourceSpanId']
        owner_record=records[disposition['sourceRecordVersionId']]
        span_sources([sid],[owner_record['id']])
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
            if any(sid not in maps[key][i]['sourceSpanIds'] or owner_record['id'] not in maps[key][i]['sourceRecordVersionIds'] for i in ids): reject('source-identity-mismatch')
    for key in ('claims','reports'):
        for value in maps[key].values():
            for sid in value['sourceSpanIds']:
                for rid in value['sourceRecordVersionIds']:
                    if spans[sid]['sourceUnitId'] not in records[rid]['authorityUnitIds']: continue
                    if not any(d['sourceSpanId']==sid and d['sourceRecordVersionId']==rid and value['id'] in d['claimIds' if key=='claims' else 'reportIds'] for d in maps['spanDispositions'].values()): reject('reference-closure-mismatch')
    selections={s['sourceRecordVersionId']:s for s in snapshot['assessmentSelection']}
    if len(selections)!=len(snapshot['assessmentSelection']) or set(selections)!=set(current.values()): reject('coverage-mismatch')
    for rid, selection in selections.items():
        for field, kind in [('extractionAssessmentId','extraction'),('humanReviewAssessmentId','human_review')]:
            a=maps['assessments'][selection[field]]
            if a['id'] in retired_assessments: reject('stale-assessment-selection')
            if a['kind'] != kind or {'kind':'sourceRecords','id':rid} not in a['targets']: reject('assessment-binding-mismatch')
        a=maps['assessments'][selection['extractionAssessmentId']]
        if a['status'] not in {'complete','partial','not_started'}: reject('assessment-binding-mismatch')
        rows=[row for (owner,_),row in selected_rows.items() if owner==rid]
        if any({'kind':'spanDispositions','id':row['id']} not in a['targets'] for row in rows): reject('assessment-binding-mismatch')
        states=[row['status'] for row in rows]
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
                if key=='nameId' and child: found.add(('names',child))
                found |= active_refs(child)
        return found
    for key in COLLECTIONS:
        if key in audit_collections: continue
        for item in maps[key].values():
            if (key,item['id']) in retired: continue
            if active_refs(item, {'claimIds'} if key=='reports' else set()) & retired: reject('active-reference-retired')
    for selection in snapshot['currentSourceSelection']+snapshot['currentSpanDispositionSelection']:
        if active_refs(selection) & retired: reject('active-reference-retired')
    if any(r not in current.values() and ('sourceRecords',r) not in retired for r in records): reject('stale-source-selection')
    active_entities=[e['logicalEntityId'] for e in maps['entities'].values() if ('entities',e['id']) not in retired]
    if len(active_entities)!=len(set(active_entities)): reject('logical-identity-conflict')
    for pair,row in selected_rows.items():
        if active_refs(row,{'assessmentIds'}) & retired: reject('active-reference-retired')
    for key in ('claims','reports'):
        for value in maps[key].values():
            if (key,value['id']) in retired: continue
            for rid in value['sourceRecordVersionIds']:
                if rid not in current.values(): reject('stale-source-selection')
                for sid in value['sourceSpanIds']:
                    if spans[sid]['sourceUnitId'] not in records[rid]['authorityUnitIds']: continue
                    if value['id'] not in selected_rows[(rid,sid)]['claimIds' if key=='claims' else 'reportIds']: reject('reference-closure-mismatch')
    for selection in snapshot['assessmentSelection']:
        if active_refs(selection) & retired: reject('active-reference-retired')
        for key in ('extractionAssessmentId','humanReviewAssessmentId'):
            current=maps['assessments'][selection[key]]
            if active_refs(current,{'targets','inputs','predecessorIds'}) & retired: reject('active-reference-retired')
    validate_receipt_projection(snapshot,inventory,profile,receipt_bundle,receipts,maps,selections)
    return maps
