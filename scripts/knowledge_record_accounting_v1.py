"""Byte-complete, source-anchored record accounting; semantic review is separate."""
import hashlib

from knowledge_export import digest,reject,read
import knowledge_pilot_trial as old
from schema_validation import validate_schema_instance

SCHEMA='al-isabah.knowledge-record-accounting.v1'
REVIEW_SCHEMA='al-isabah.knowledge-record-accounting-review.v1'
SCHEMA_PATH=old.ROOT/'schemas/knowledge-record-accounting.v1.schema.json'
OBJECT_KINDS={'claims','events','reports','values'}
UNRESOLVED={'not_yet_extracted','unsupported_vocabulary','missing_source_locator',
            'witness_unavailable','source_damage','mapping_unverified'}


def owned(packet,scope):
    record=next((r for r in packet['records'] if r['id']==scope['recordId']),None)
    if record is None:reject('accounting-record-not-found')
    units={u['id']:u for u in packet['units'] if u['sourceRecordVersionId']==record['id']}
    if set(units)!=set(record['sourceUnitIds']):reject('accounting-source-unit-drift')
    return record,units


def validate(accounting,packet,output,scope):
    schema=read(SCHEMA_PATH)
    if validate_schema_instance(accounting,schema['oneOf'][0],schema):reject('accounting-schema-mismatch')
    record,units=owned(packet,scope);rid=record['id']
    if (set(accounting)!={'schema','recordId','packetSha256','sourceUnitSha256','atoms','routes','recordComplete'}
        or accounting['schema']!=SCHEMA or accounting['recordId']!=rid
        or accounting['packetSha256']!=packet['packetSha256']
        or accounting['sourceUnitSha256']!={uid:u['rawSha256'] for uid,u in sorted(units.items())}
        or not isinstance(accounting['recordComplete'],bool)):
        reject('accounting-shape-or-source-drift')
    spans={s['id']:(u,s) for u in units.values() for s in u['spans']}
    objects={kind:{x['id']:x for x in output[kind]} for kind in OBJECT_KINDS}
    findings={x['id']:x for x in output['findings']}
    atoms={};by_span={sid:[] for sid in spans}
    for atom in accounting['atoms']:
        if (set(atom)!={'id','sourceSpanId','startChar','endChar','surfaceSha256','kind',
                       'disposition','objectRefs','findingIds','reasonCode','rationale'}
            or atom['id'] in atoms or atom['sourceSpanId'] not in spans
            or not isinstance(atom['rationale'],str) or not atom['rationale'].strip()):
            reject('accounting-atom-shape')
        u,s=spans[atom['sourceSpanId']];raw=s['rawOpeniti'];start=atom['startChar'];end=atom['endChar']
        if (not isinstance(start,int) or not isinstance(end,int) or not 0<=start<end<=len(raw)
            or hashlib.sha256(raw[start:end].encode('utf-8')).hexdigest()!=atom['surfaceSha256']):
            reject('accounting-anchor-drift')
        kind=atom['kind'];state=atom['disposition'];refs=atom['objectRefs'];finding_ids=atom['findingIds']
        if kind=='structural':
            if u['kind'] not in {'structural_heading','interstitial_prose'} or state!='structural' or refs or finding_ids or atom['reasonCode']!='heading':
                reject('accounting-structural-mismatch')
        elif kind=='nonsemantic':
            if state!='nonsemantic' or refs or finding_ids or atom['reasonCode'] not in {'markup','formula_only','bibliographic_format'}:
                reject('accounting-nonsemantic-mismatch')
        elif kind=='semantic':
            if u['kind']!='entry' or state not in {'represented','qualified_uncertainty','unresolved'}:
                reject('accounting-semantic-mismatch')
            if (state=='represented' and (not refs or finding_ids or atom['reasonCode'])
                or state=='qualified_uncertainty' and (not refs or not finding_ids or atom['reasonCode'])
                or state=='unresolved' and (refs or not finding_ids or atom['reasonCode'] not in UNRESOLVED)):
                reject('accounting-semantic-mismatch')
        else:reject('accounting-atom-kind')
        if len({(r.get('kind'),r.get('id')) for r in refs})!=len(refs) or len(set(finding_ids))!=len(finding_ids):
            reject('accounting-duplicate-ref')
        for ref in refs:
            if set(ref)!={'kind','id'} or ref['kind'] not in OBJECT_KINDS:reject('accounting-object-ref')
            value=objects[ref['kind']].get(ref['id'])
            if value is None or rid not in value['sourceRecordVersionIds']:
                reject('accounting-object-ref')
            if ref['kind'] in {'claims','reports'} and atom['sourceSpanId'] not in value['sourceSpanIds']:
                reject('accounting-object-anchor')
            if ref['kind']=='events' and not any(atom['sourceSpanId'] in objects['reports'][r]['sourceSpanIds']
                                               for r in value['reportIds']):
                reject('accounting-object-anchor')
        for fid in finding_ids:
            if not finding_owned(findings.get(fid),objects,output,rid):reject('accounting-finding-ref')
        atoms[atom['id']]=atom;by_span[atom['sourceSpanId']].append(atom)
    for sid,(unit,span) in spans.items():
        rows=sorted(by_span[sid],key=lambda x:x['startChar'])
        if not rows or rows[0]['startChar']!=0 or rows[-1]['endChar']!=len(span['rawOpeniti']):
            reject('accounting-source-gap')
        if any(a['endChar']!=b['startChar'] for a,b in zip(rows,rows[1:])):
            reject('accounting-source-gap')
        if unit['kind']!='entry' and any(a['kind']=='semantic' for a in rows):
            reject('accounting-structural-mismatch')
    if accounting['atoms']!=sorted(accounting['atoms'],key=lambda a:(a['sourceSpanId'],a['startChar'])):
        reject('accounting-order')
    mapped={(ref['kind'],ref['id']) for atom in atoms.values() for ref in atom['objectRefs']}
    required={(kind,value['id']) for kind in OBJECT_KINDS for value in output[kind]
              if rid in value['sourceRecordVersionIds']}
    if not required<=mapped:reject('accounting-object-coverage')
    routes={};covered_reports=[]
    for row in accounting['routes']:
        if (set(row)!={'routeKey','atomIds','reportId','findingIds','status','rationale'}
            or row['routeKey'] in routes or not row['routeKey'] or not row['atomIds']
            or len(set(row['atomIds']))!=len(row['atomIds'])
            or not isinstance(row['rationale'],str) or not row['rationale'].strip()
            or any(aid not in atoms or atoms[aid]['kind']!='semantic' for aid in row['atomIds'])):
            reject('accounting-route-shape')
        report=objects['reports'].get(row['reportId']) if row['reportId'] else None
        if row['status'] in {'represented','qualified_uncertainty'}:
            if report is None or rid not in report['sourceRecordVersionIds']:
                reject('accounting-route-report')
            if not any(atoms[aid]['sourceSpanId'] in report['sourceSpanIds'] for aid in row['atomIds']):
                reject('accounting-route-anchor')
            covered_reports.append(row['reportId'])
        elif row['status']=='unresolved':
            if row['reportId'] or not row['findingIds']:reject('accounting-route-unresolved')
        else:reject('accounting-route-status')
        if row['status']=='represented' and row['findingIds'] or row['status']!='represented' and not row['findingIds']:
            reject('accounting-route-finding')
        if any(not finding_owned(findings.get(fid),objects,output,rid) for fid in row['findingIds']):
            reject('accounting-route-finding')
        routes[row['routeKey']]=row
    expected_reports={x['id'] for x in output['reports'] if rid in x['sourceRecordVersionIds']}
    if set(covered_reports)!=expected_reports or len(covered_reports)!=len(set(covered_reports)):
        reject('accounting-route-coverage')
    if accounting['routes']!=sorted(accounting['routes'],key=lambda r:r['routeKey']):
        reject('accounting-route-order')
    return atoms,routes


def finding_owned(finding,objects,output,rid):
    if finding is None:return False
    groups={x['id']:x for x in output['ambiguityGroups']}
    for target in finding['targets']:
        kind=target['kind'];identity=target['id']
        if kind=='sourceRecords' and identity==rid:return True
        if kind in objects and identity in objects[kind] and rid in objects[kind][identity]['sourceRecordVersionIds']:
            return True
        if kind=='ambiguityGroups' and identity in groups:
            if any(m['kind'] in objects and m['id'] in objects[m['kind']]
                   and rid in objects[m['kind']][m['id']]['sourceRecordVersionIds']
                   for m in groups[identity]['members']):return True
    return False


def validate_review(review,accounting,packet,output,scope):
    schema=read(SCHEMA_PATH)
    if validate_schema_instance(review,schema['oneOf'][1],schema):reject('accounting-review-schema-mismatch')
    atoms,routes=validate(accounting,packet,output,scope)
    if (set(review)!={'schema','accountingSha256','candidateOutputSha256','atomVerdicts','routeVerdicts',
                     'completenessAssessment','rationale'} or review['schema']!=REVIEW_SCHEMA
        or review['accountingSha256']!=digest(accounting)
        or review['candidateOutputSha256']!=digest(output)
        or not isinstance(review['rationale'],str) or not review['rationale'].strip()):
        reject('accounting-review-shape')
    for key,source,identity in (('atomVerdicts',atoms,'atomId'),('routeVerdicts',routes,'routeKey')):
        rows=review[key]
        if (not isinstance(rows,list) or len(rows)!=len(source)
            or {x.get(identity) for x in rows}!=set(source)
            or len({x.get(identity) for x in rows})!=len(rows)
            or any(set(x)!={identity,'verdict','rationale'} or x['verdict'] not in
                   {'supported','qualified','missing','unsupported'} or not isinstance(x['rationale'],str)
                   or not x['rationale'].strip() for x in rows)):
            reject('accounting-review-coverage')
    residual=any(x['verdict'] in {'missing','unsupported'} for key in ('atomVerdicts','routeVerdicts') for x in review[key])
    residual|=any(x['disposition']=='unresolved' for x in atoms.values())
    residual|=any(x['status']=='unresolved' for x in routes.values())
    expected='residuals' if residual else 'no_missing_known'
    if review['completenessAssessment']!=expected:reject('accounting-review-completeness')
    return expected


def validate_final(accounting,reviewed_accounting,review,packet,review_output,output,scope):
    # A material accounting change after critique requires another independent review.
    if ({k:v for k,v in accounting.items() if k!='recordComplete'}!=
        {k:v for k,v in reviewed_accounting.items() if k!='recordComplete'}):
        reject('accounting-unreviewed-final-change')
    assessment=validate_review(review,reviewed_accounting,packet,review_output,scope)
    validate(accounting,packet,output,scope)
    if accounting['recordComplete'] and assessment!='no_missing_known':
        reject('accounting-false-completeness')
    return {'schema':'al-isabah.knowledge-record-accounting-result.v1',
            'recordId':scope['recordId'],'accountingSha256':digest(accounting),
            'reviewSha256':digest(review),'recordComplete':accounting['recordComplete'],
            'semanticExhaustivenessProvenByMachine':False}
