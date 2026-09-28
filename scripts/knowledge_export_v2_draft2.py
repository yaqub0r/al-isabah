#!/usr/bin/env python3
"""Executable draft v2 conformance only. Real semantic execution/intake disabled."""
from __future__ import annotations
import argparse
import copy
import datetime
import unicodedata
import knowledge_runtime_draft as runtime
from pathlib import Path
from knowledge_export import canonical, digest, read, shape, schema_vocabulary, Rejection, reject
from public_boundary import boundary_errors

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / 'schemas/al-isabah-knowledge-export.v2-draft2.schema.json'
COLLECTIONS = ('sourceRecords','assessments','actors','artifacts','entities','mentions','reports','events','claims','ambiguityGroups','spanDispositions','lifecycleEvents','values','places','times','qualifications','attributions','useRestrictions','findings','names')
BLOCKED = {'unsupported_semantics','unprocessed','source_or_mapping_blocked'}
LIST_REFS = {'nameIds':'names','receiptArtifactIds':'artifacts','authorityUnitIds':'sourceUnits','sourceRecordVersionIds':'sourceRecords','mentionIds':'mentions','identityAssessmentIds':'assessments','ambiguityGroupIds':'ambiguityGroups','sourceSpanIds':'sourceSpans','attributorEntityIds':'entities','entityIds':'entities','claimIds':'claims','criticalAssessmentIds':'assessments','placeIds':'places','timeIds':'times','reportIds':'reports','qualificationIds':'qualifications','assessmentIds':'assessments','attributionIds':'attributions','useRestrictionIds':'useRestrictions','predecessorIds':'assessments','findingIds':'findings','artifactIds':'artifacts','evidenceArtifactIds':'artifacts','evaluatorEntityIds':'entities','dependencyIds':'lifecycleEvents'}
SINGLE_REFS = {'spanDispositionId':'spanDispositions','logicalRecordId':'logicalRecords','sourceArtifactId':'artifacts','actorId':'actors','methodArtifactId':'artifacts','authorityArtifactId':'artifacts','entityId':'entities','sourceRecordVersionId':'sourceRecords','sourceSpanId':'sourceSpans','subjectId':'entities','decisionArtifactId':'artifacts','extractionAssessmentId':'assessments','humanReviewAssessmentId':'assessments'}

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
            if key=='nameId' and child and child not in maps['names']: reject('missing-reference')
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


def validate_names(maps, span_sources):
    for name in maps['names'].values():
        form=name['form']
        if unicodedata.normalize('NFC',form)!=form or form.strip()!=form or '  ' in form:
            reject('name-form-invalid')
        letters=[c for c in form if unicodedata.category(c).startswith('L')]
        if not letters: reject('name-form-invalid')
        for char in letters:
            script=unicodedata.name(char,'')
            if char in '\u02be\u02bf': continue
            if ('ARABIC' if name['language']=='ar' else 'LATIN') not in script:
                reject('name-language-mismatch')
        span_sources([name['sourceSpanId']],[name['sourceRecordVersionId']])
        entity=maps['entities'][name['entityId']]
        if name['id'] not in entity['nameIds'] or name['sourceRecordVersionId'] not in entity['sourceRecordVersionIds']:
            reject('name-binding-mismatch')
        if name['derivation']=='editorial_supply':
            required=[{'kind':'names','id':name['id']},{'kind':'sourceRecords','id':name['sourceRecordVersionId']}]
            if not any(a['kind'] in {'independent_review','adjudication'} and a['status']=='complete' and all(t in a['targets'] for t in required) for a in (maps['assessments'][i] for i in name['assessmentIds'])):
                reject('name-review-required')
    for entity in maps['entities'].values():
        if any(maps['names'][i]['entityId']!=entity['id'] for i in entity['nameIds']): reject('name-binding-mismatch')
    for mention in maps['mentions'].values():
        if mention['nameRole']=='unnamed_reference':
            if mention['nameId']: reject('name-binding-mismatch')
            continue
        name=maps['names'].get(mention['nameId'])
        if not name or any(mention[k]!=name[k] for k in ('entityId','sourceSpanId','sourceRecordVersionId')) or mention['surfaceSha256']!=name['sourceSurfaceSha256'] or mention['nameRole']!=name['formRole']:
            reject('name-binding-mismatch')


def semantic_projection(snapshot, requested=None, dependencies=()):
    """A text-free checkpoint of exact active semantic objects, without receipt cycles."""
    retired={(r['kind'],r['id']) for e in snapshot['lifecycleEvents'] for r in e['targets']}
    current_sources={r['sourceRecordVersionId'] for r in snapshot['currentSourceSelection']}
    current_rows={r['spanDispositionId'] for r in snapshot['currentSpanDispositionSelection']}
    result=[]
    for kind in COLLECTIONS:
        if kind in {'assessments','actors','artifacts','lifecycleEvents'}: continue
        for value in snapshot[kind]:
            if (kind,value['id']) in retired: continue
            if kind=='sourceRecords' and value['id'] not in current_sources: continue
            if kind=='spanDispositions' and value['id'] not in current_rows: continue
            result.append({'ref':{'kind':kind,'id':value['id']},'sha256':digest(value)})
    if requested is not None:
        allowed=set(requested)|set(dependencies)
        if not set(requested) or not allowed<=current_sources:reject('knowledge-output-scope-mismatch')
        objects={(kind,v['id']):v for kind in COLLECTIONS for v in snapshot[kind]}
        available={(r['ref']['kind'],r['ref']['id']):r for r in result}
        def source_ids(value):
            return set(value.get('sourceRecordVersionIds',[]))|({value['sourceRecordVersionId']} if 'sourceRecordVersionId' in value else set())|{r['id'] for r in value.get('targets',[]) if r['kind']=='sourceRecords'}
        selected={key for key in available if (key[0]=='sourceRecords' and key[1] in requested) or source_ids(objects[key])&set(requested)}
        pending=list(selected)
        def references(value):
            found=set()
            if isinstance(value,list):
                for child in value:found|=references(child)
            elif isinstance(value,dict):
                if set(value)=={'kind','id'}:found.add((value['kind'],value['id']))
                for key,child in value.items():
                    if key in LIST_REFS:found|={(LIST_REFS[key],i) for i in child}
                    if key in SINGLE_REFS:found.add((SINGLE_REFS[key],child))
                    if key=='nameId' and child:found.add(('names',child))
                    found|=references(child)
            return found
        while pending:
            key=pending.pop();value=objects[key]
            owners=source_ids(value)|({key[1]} if key[0]=='sourceRecords' else set())
            if not owners<=allowed:reject('knowledge-output-scope-mismatch')
            for ref in references(value):
                if ref in available and ref not in selected:selected.add(ref);pending.append(ref)
        used_sources=set()
        for key in selected: used_sources |= source_ids(objects[key])|({key[1]} if key[0]=='sourceRecords' else set())
        if used_sources-set(requested)!=set(dependencies):reject('knowledge-output-scope-mismatch')
        result=[available[key] for key in selected]
    return {'schema':'al-isabah.knowledge-semantic-checkpoint.v1-draft','objects':sorted(result,key=lambda x:(x['ref']['kind'],x['ref']['id']))}


def validate_receipt_projection(snapshot,inventory,profile,bundle,receipts,maps,selections):
    bindings={x['receiptId']:x for x in bundle['bindings']}
    artifact_receipts={a['id'] for a in maps['artifacts'].values() if a['kind']=='knowledge_receipt'}
    if artifact_receipts!=set(receipts): reject('knowledge-receipt-coverage-mismatch')
    for identity,receipt in receipts.items():
        if maps['artifacts'][identity]['sha256']!=digest(receipt): reject('knowledge-receipt-binding-mismatch')
        binding=bindings[identity]
        inputs=binding['inputs'];outputs=binding['outputs']
        expected_sources=[{'id':rid,'sha256':digest(maps['sourceRecords'][rid])} for rid in receipt['sourceRecordVersionIds'] if rid in maps['sourceRecords']]
        previous=receipt['upstreamReceiptIds']
        requested=inputs.get('requestedSourceRecordVersionIds',[]);dependencies=inputs.get('dependencySourceRecordVersionIds',[])
        if not requested or requested!=sorted(set(requested)) or dependencies!=sorted(set(dependencies)) or set(requested)&set(dependencies) or sorted(requested+dependencies)!=receipt['sourceRecordVersionIds']:reject('knowledge-output-scope-mismatch')
        expected_inputs={'inventorySha256':digest(inventory),'profileSha256':digest(profile),'sourceRecords':expected_sources,'requestedSourceRecordVersionIds':requested,'dependencySourceRecordVersionIds':dependencies,'upstreamOutputSha256':receipts[previous[0]]['outputSha256'] if previous else ''}
        if len(expected_sources)!=len(receipt['sourceRecordVersionIds']) or inputs!=expected_inputs: reject('knowledge-receipt-binding-mismatch')
        if previous and any(inputs[key]!=bindings[previous[0]]['inputs'][key] for key in ('requestedSourceRecordVersionIds','dependencySourceRecordVersionIds')):reject('knowledge-stage-chain-mismatch')
        if set(outputs)!={'schema','objects'} or outputs['schema']!='al-isabah.knowledge-semantic-checkpoint.v1-draft': reject('knowledge-receipt-binding-mismatch')
        seen=set()
        for item in outputs['objects']:
            if set(item)!={'ref','sha256'} or set(item['ref'])!={'kind','id'}: reject('knowledge-receipt-binding-mismatch')
            key=(item['ref']['kind'],item['ref']['id'])
            if key[0] in {'assessments','actors','artifacts','lifecycleEvents','sourceUnits','sourceSpans','logicalRecords'}:reject('knowledge-output-scope-mismatch')
            if key in seen or key[0] not in maps or key[1] not in maps[key[0]] or digest(maps[key[0]][key[1]])!=item['sha256']: reject('knowledge-receipt-binding-mismatch')
            value=maps[key[0]][key[1]]
            owners={r['id'] for r in value.get('targets',[]) if r['kind']=='sourceRecords'}|set(value.get('sourceRecordVersionIds',[]))|({value['sourceRecordVersionId']} if 'sourceRecordVersionId' in value else set())|({key[1]} if key[0]=='sourceRecords' else set())
            if not owners<=set(receipt['sourceRecordVersionIds']):reject('knowledge-output-scope-mismatch')
            seen.add(key)
    expected_output=semantic_projection(snapshot)
    covered={}
    unprocessed_metadata=set()
    for assessment in maps['assessments'].values():
        if any(i not in receipts for i in assessment['receiptArtifactIds']): reject('knowledge-receipt-coverage-mismatch')
        if assessment['kind']=='human_review' and assessment['receiptArtifactIds']: reject('human-review-inferred')
    for rid,selection in selections.items():
        assessment=maps['assessments'][selection['extractionAssessmentId']]
        ids=assessment['receiptArtifactIds']
        if assessment['status']=='not_started':
            if ids: reject('knowledge-receipt-coverage-mismatch')
            unprocessed_metadata.add(('sourceRecords',rid))
            unprocessed_metadata|={('spanDispositions',r['spanDispositionId']) for r in snapshot['currentSpanDispositionSelection'] if r['sourceRecordVersionId']==rid}
            unprocessed_metadata|={('findings',f['id']) for f in maps['findings'].values() if f['targets']==[{'kind':'sourceRecords','id':rid}]}
            continue
        if len(ids)!=3: reject('knowledge-receipt-coverage-mismatch')
        chain=[receipts[i] for i in ids]
        if [r['stage'] for r in chain]!=list(runtime.STAGES) or any(rid not in r['sourceRecordVersionIds'] for r in chain): reject('knowledge-stage-chain-mismatch')
        if chain[1]['upstreamReceiptIds']!=[ids[0]] or chain[2]['upstreamReceiptIds']!=[ids[1]]: reject('knowledge-stage-chain-mismatch')
        inputs=bindings[ids[2]]['inputs']
        if rid not in inputs['requestedSourceRecordVersionIds']:reject('knowledge-output-scope-mismatch')
        output=bindings[ids[2]]['outputs']
        scoped=semantic_projection(snapshot,inputs['requestedSourceRecordVersionIds'],inputs['dependencySourceRecordVersionIds'])
        if output!=scoped: reject('knowledge-current-output-mismatch')
        for item in output['objects']:
            key=(item['ref']['kind'],item['ref']['id'])
            if key in covered and covered[key]!=item:reject('knowledge-output-conflict')
            covered[key]=item
    expected={(x['ref']['kind'],x['ref']['id']):x for x in expected_output['objects']}
    if set(expected)-set(covered)-unprocessed_metadata or set(covered)-set(expected):reject('knowledge-output-coverage-mismatch')


def validate_snapshot(snapshot, inventory, profile, trust, receipt_bundle, registry):
    schema = read(SCHEMA_PATH)
    schema_vocabulary(schema)
    for name, value in [('snapshot',snapshot),('inventory',inventory),('profile',profile),('trust',trust)]:
        shape(value, schema['$defs'][name], schema)
        if boundary_errors(value): reject('prohibited-payload')
    if snapshot['mode'] != 'synthetic' or profile['mode'] != 'synthetic': reject('real-mode-disabled')
    if snapshot['fixtureClass'] != 'synthetic-conformance': reject('real-mode-disabled')
    expected = {'schemaId':'al-isabah.knowledge-draft2-trust.v2','fixtureClass':'synthetic-conformance','snapshotSha256':digest(snapshot),'inventorySha256':digest(inventory),'profileSha256':digest(profile),'schemaSha256':digest(schema),'receiptBundleSha256':digest(receipt_bundle)}
    if trust != expected: reject('external-pin-mismatch')
    if snapshot['receiptBundleSha256']!=digest(receipt_bundle) or profile['methodRegistrySha256']!=digest(registry): reject('external-pin-mismatch')
    receipts=runtime.validate_bundle(receipt_bundle,registry,trust['receiptBundleSha256'])
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
    if any(a['status'] != 'synthetic_only' for a in maps['artifacts'].values()): reject('real-mode-disabled')

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


def coverage(snapshot, inventory):
    logical={r['id']:r for r in inventory['logicalRecords']}
    selected_units={u['id'] for u in inventory['sourceUnits'] if u['inScope']}
    selected_spans={s['id'] for s in inventory['sourceSpans'] if s['sourceUnitId'] in selected_units}
    selected_ids={s['spanDispositionId'] for s in snapshot['currentSpanDispositionSelection']}
    dispositions=[s for s in snapshot['spanDispositions'] if s['id'] in selected_ids and s['sourceSpanId'] in selected_spans]
    amap=indexed(snapshot['assessments']); rmap=indexed(snapshot['sourceRecords'])
    complete=sum(amap[s['extractionAssessmentId']]['status']=='complete' for s in snapshot['assessmentSelection'] if logical[rmap[s['sourceRecordVersionId']]['logicalRecordId']]['inScope'])
    return {'requestedLogicalRecords':sum(x['inScope'] for x in logical.values()),'dependencyLogicalRecords':sum(not x['inScope'] for x in logical.values()),'sourceUnits':len(selected_units),'entries':sum(u['inScope'] and u['kind']=='entry' for u in inventory['sourceUnits']),'structuralUnits':sum(u['inScope'] and u['kind']!='entry' for u in inventory['sourceUnits']),'expectedSpans':len(selected_spans),'representedSpans':sum(x['status'] not in BLOCKED for x in dispositions),'uncertainSpans':sum(x['status']=='represented_uncertain' for x in dispositions),'blockedSpans':sum(x['status'] in BLOCKED for x in dispositions),'extractionCompleteRecords':complete,'assessmentVersions':len(snapshot['assessments']),'claims':len(snapshot['claims']),'scopeExtractionComplete':complete==sum(x['inScope'] for x in logical.values()) and not any(x['status'] in BLOCKED for x in dispositions)}


def build(snapshot, inventory, profile, trust, batch_id, receipt_bundle, registry):
    validate_snapshot(snapshot, inventory, profile, trust, receipt_bundle, registry)
    batch=snapshot['batch']
    if batch_id != batch['id']: reject('undeclared-batch')
    payload={'schemaId':'al-isabah.knowledge-export.v2','exportId':batch['exportId'],'batchId':batch_id,'snapshotId':snapshot['id'],'snapshotSha256':digest(snapshot),'selection':copy.deepcopy(batch),'coverage':coverage(snapshot,inventory)}
    for key in ('schemaVersion','mode','fixtureClass','profileSha256','inventorySha256','authority','assessmentSelection','currentSourceSelection','currentSpanDispositionSelection','receiptBundleSha256',*COLLECTIONS): payload[key]=copy.deepcopy(snapshot[key])
    payload['payloadSha256']=digest(payload)
    shape(payload,read(SCHEMA_PATH))
    return payload


def validate_payload(payload, snapshot, inventory, profile, trust, receipt_bundle, registry):
    shape(payload,read(SCHEMA_PATH))
    if payload['mode'] != 'synthetic': reject('real-mode-disabled')
    expected=build(snapshot,inventory,profile,trust,payload['batchId'],receipt_bundle,registry)
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
    for name in ('snapshot','inventory','profile','trust','output','receipts','registry'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--batch',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
    try:
        data=build(read(a.snapshot),read(a.inventory),read(a.profile),read(a.trust),a.batch,read(a.receipts),read(a.registry)); encoded=canonical(data)
        if a.check:
            if a.output.read_bytes()!=encoded: reject('noncanonical-output')
        else:
            a.output.parent.mkdir(parents=True,exist_ok=True)
            with a.output.open('xb') as f:f.write(encoded)
        print(data['payloadSha256']);return 0
    except Rejection as e: print(str(e));return 1
    except (OSError,ValueError,KeyError,TypeError,RecursionError):print('input-output-error');return 1

if __name__=='__main__': raise SystemExit(main())
