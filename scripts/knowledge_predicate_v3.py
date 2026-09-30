"""Draft3 predicate constraints shared by export and private stage validation."""
from knowledge_export import reject


def validate_profile_domains(profile):
    events=set(profile['eventTypes'])
    units={u['id']:u for u in profile['valueUnits']}
    if len(units)!=len(profile['valueUnits']):reject('value-domain-mismatch')
    if len({p['id'] for p in profile['predicates']})!=len(profile['predicates']):reject('predicate-domain-mismatch')
    for p in profile['predicates']:
        for kind,field,domain in [('event','subjectEventTypes',p['subjectKinds']),('events','objectEventTypes',p['objectKinds'])]:
            if bool(p[field])!=(kind in domain) or not set(p[field])<=events:reject('predicate-domain-mismatch')
        if bool(p['objectValueKinds'])!=('values' in p['objectKinds']) or bool(p['objectUnits'])!=('values' in p['objectKinds']):reject('predicate-domain-mismatch')
        if bool(p['objectEntityKinds'])!=('entities' in p['objectKinds']):reject('predicate-domain-mismatch')
        if not set(p['objectUnits'])<=units.keys():reject('predicate-domain-mismatch')
        if p['sourceEvidenceRule']=='exact_notice_source_author':
            e=p['epistemicPolicy']
            if (p['subjectKinds']!=['person'] or p['objectKinds']!=['sourceRecords']
                    or e['allowedAssertionClasses']!=['source_attested']
                    or 'factual_spine' in e['allowedUseTiers']):reject('predicate-domain-mismatch')


def validate_value_place_domains(maps,profile):
    units={u['id']:u for u in profile['valueUnits']}
    for value in maps['values'].values():
        if value['unit'] not in units or value['kind'] not in units[value['unit']]['valueKinds']:reject('value-domain-mismatch')
    for place in maps['places'].values():
        if maps['entities'][place['entityId']]['kind']!='place':reject('place-domain-mismatch')
    for event in maps['events'].values():
        if not event['sourceRecordVersionIds'] or not event['reportIds']:reject('event-evidence-missing')
        evidence={r for i in event['reportIds'] for r in maps['reports'][i]['sourceRecordVersionIds']}
        if not set(event['sourceRecordVersionIds'])<=evidence:reject('event-evidence-mismatch')


def validate_claim_domain(claim,pred,maps):
    subject=claim['subjectRef'];obj=claim['objectRef']
    value=maps[subject['kind']][subject['id']]
    kind='event' if subject['kind']=='events' else value['kind']
    if kind not in pred['subjectKinds'] or obj['kind'] not in pred['objectKinds']:reject('reference-kind-mismatch')
    if subject['kind']=='events':
        if value['typeId'] not in pred['subjectEventTypes']:reject('predicate-domain-mismatch')
        if not set(value['sourceRecordVersionIds'])<=set(claim['sourceRecordVersionIds']):reject('event-evidence-mismatch')
    target=maps[obj['kind']][obj['id']]
    if obj['kind']=='entities' and target['kind'] not in pred['objectEntityKinds']:reject('reference-kind-mismatch')
    if obj['kind']=='events':
        if target['typeId'] not in pred['objectEventTypes']:reject('predicate-domain-mismatch')
        if not set(target['sourceRecordVersionIds'])<=set(claim['sourceRecordVersionIds']):reject('event-evidence-mismatch')
    if obj['kind']=='values' and (target['kind'] not in pred['objectValueKinds'] or target['unit'] not in pred['objectUnits']):reject('value-domain-mismatch')
    policy=pred['epistemicPolicy']
    for field,allowed in [('assertionClass','allowedAssertionClasses'),('polarity','allowedPolarities'),('modality','allowedModalities')]:
        if claim[field] not in policy[allowed]:reject('predicate-epistemic-mismatch')
    if any(maps['useRestrictions'][i]['tier'] not in policy['allowedUseTiers'] for i in claim['useRestrictionIds']):reject('predicate-epistemic-mismatch')
    if pred['sourceEvidenceRule']=='exact_notice_source_author':validate_notice_evidence(claim,maps)


def validate_notice_evidence(claim,maps):
    # The attesting record and the target notice can differ. Both immutable
    # versions must enter the exact declared source/dependency closure.
    target=claim['objectRef']
    if target['kind']!='sourceRecords' or target['id'] not in claim['sourceRecordVersionIds']:reject('notice-evidence-mismatch')
    owners=set()
    for sid in claim['sourceSpanIds']:
        span=maps['sourceSpans'][sid]
        matching={rid for rid in claim['sourceRecordVersionIds'] if span['sourceUnitId'] in maps['sourceRecords'][rid]['authorityUnitIds']}
        if not matching:reject('notice-evidence-mismatch')
        owners|=matching
    if not owners:reject('notice-evidence-mismatch')
    for rid in owners:
        record=maps['sourceRecords'][rid];artifact=record['sourceArtifactId']
        attesting=[sid for sid in claim['sourceSpanIds'] if maps['sourceSpans'][sid]['sourceUnitId'] in record['authorityUnitIds']]
        evaluators={e for qid in claim['qualificationIds'] for e in maps['qualifications'][qid]['evaluatorEntityIds']
                    if rid in maps['qualifications'][qid]['sourceRecordVersionIds']
                    and {'kind':'claims','id':claim['id']} in maps['qualifications'][qid]['targets']}
        for sid in attesting:
            report_authors={e for report_id in claim['reportIds'] for e in maps['reports'][report_id]['attributorEntityIds']
                            if rid in maps['reports'][report_id]['sourceRecordVersionIds']
                            and sid in maps['reports'][report_id]['sourceSpanIds']}
            candidates=[maps['attributions'][a] for a in claim['attributionIds']]
            if not any(a['kind']=='source_author' and artifact in a['artifactIds'] and a['entityIds']
                       and all(maps['entities'][e]['kind']=='person' for e in a['entityIds'])
                       and set(a['entityIds'])<=report_authors and set(a['entityIds'])<=evaluators for a in candidates):
                reject('source-author-attribution-mismatch')
