#!/usr/bin/env python3
"""Plan explicit semantic successors; never infer edits, approval, or resolution."""
import argparse
import copy
from pathlib import Path
import knowledge_export_v2_draft3 as contract
from knowledge_export import canonical,digest,read,reject,shape,Rejection
from host_runtime import write_runtime

MUTABLE=('entities','mentions','names','reports','events','claims','ambiguityGroups','values','places','times','qualifications','attributions','useRestrictions','findings')
EXTERNAL={'sourceRecords','sourceSpans','assessments','actors','artifacts'}


def references(value):
    found=set()
    if isinstance(value,list):
        for child in value:found|=references(child)
    elif isinstance(value,dict):
        if set(value)=={'kind','id'}:found.add((value['kind'],value['id']))
        for field,child in value.items():
            if field in contract.LIST_REFS:found|={(contract.LIST_REFS[field],v) for v in child}
            if field in contract.SINGLE_REFS:found.add((contract.SINGLE_REFS[field],child))
            if field=='nameId' and child:found.add(('names',child))
            found|=references(child)
    return found


def rewire(value,mapping):
    if isinstance(value,list):return [rewire(v,mapping) for v in value]
    if not isinstance(value,dict):return value
    if set(value)=={'kind','id'}:return {'kind':value['kind'],'id':mapping.get((value['kind'],value['id']),value['id'])}
    result={}
    for field,child in value.items():
        if field in contract.LIST_REFS:result[field]=[mapping.get((contract.LIST_REFS[field],v),v) for v in child]
        elif field in contract.SINGLE_REFS:result[field]=mapping.get((contract.SINGLE_REFS[field],child),child)
        elif field=='nameId' and child:result[field]=mapping.get(('names',child),child)
        else:result[field]=rewire(child,mapping)
    return result


def reciprocal_consistency(objects):
    """Check mechanical bidirectional links, without creating missing links."""
    def get(kind,identity):
        if (kind,identity) not in objects:reject('missing-reference')
        return objects[(kind,identity)]
    def require(condition):
        if not condition:reject('successor-reciprocal-mismatch')
    for (kind,identity),value in objects.items():
        if kind=='reports':
            for cid in value['claimIds']:require(identity in get('claims',cid)['reportIds'])
        elif kind=='claims':
            for rid in value['reportIds']:require(identity in get('reports',rid)['claimIds'])
            for qid in value['qualificationIds']:require({'kind':'claims','id':identity} in get('qualifications',qid)['targets'])
        elif kind=='qualifications':
            for ref in value['targets']:
                if ref['kind']=='claims':require(identity in get('claims',ref['id'])['qualificationIds'])
        elif kind=='entities':
            for mid in value['mentionIds']:require(get('mentions',mid)['entityId']==identity)
            for nid in value['nameIds']:require(get('names',nid)['entityId']==identity)
        elif kind=='mentions':
            require(identity in get('entities',value['entityId'])['mentionIds'])
            if value['nameRole']=='unnamed_reference':require(not value['nameId'])
            else:
                name=get('names',value['nameId'])
                require(all(value[f]==name[f] for f in ('entityId','sourceSpanId','sourceRecordVersionId')))
                require(value['surfaceSha256']==name['sourceSurfaceSha256'] and value['nameRole']==name['formRole'])
        elif kind=='names':require(identity in get('entities',value['entityId'])['nameIds'])
        for gid in value.get('ambiguityGroupIds',[]):require({'kind':kind,'id':identity} in get('ambiguityGroups',gid)['members'])
        if kind=='ambiguityGroups':
            for ref in value['members']:require(identity in get(ref['kind'],ref['id']).get('ambiguityGroupIds',[]))


def plan(source,expected_digest,patches,namespace):
    if digest(source)!=expected_digest:reject('successor-base-drift')
    if set(source)!={'schema','objects','externalRefs'} or source['schema']!='al-isabah.knowledge-edit-input.v1':reject('successor-input-shape')
    schema=read(contract.SCHEMA_PATH)
    shape(namespace+':claims:'+('0'*20),schema['$defs']['id'],schema)
    objects={}
    for item in source['objects']:
        if set(item)!={'kind','value'} or item['kind'] not in MUTABLE:reject('successor-input-shape')
        shape(item['value'],schema['$defs'][item['kind']],schema)
        key=(item['kind'],item['value']['id'])
        if key in objects:reject('immutable-id-conflict')
        objects[key]=copy.deepcopy(item['value'])
    if len({key[1] for key in objects})!=len(objects):reject('immutable-id-conflict')
    external=set()
    for ref in source['externalRefs']:
        if set(ref)!={'kind','id'} or ref['kind'] not in EXTERNAL:reject('successor-input-shape')
        shape(ref['id'],schema['$defs']['id'],schema);external.add((ref['kind'],ref['id']))
    if len(external)!=len(source['externalRefs']):reject('successor-input-shape')
    available=set(objects)|external
    if len({key[1] for key in available})!=len(available):reject('immutable-id-conflict')
    if any(references(v)-available for v in objects.values()):reject('missing-reference')
    reciprocal_consistency(objects)
    effective=copy.deepcopy(objects);seen=set();seeds=set()
    for patch in patches:
        if set(patch)!={'ref','beforeSha256','replacement'} or set(patch['ref'])!={'kind','id'}:reject('successor-patch-shape')
        key=(patch['ref']['kind'],patch['ref']['id'])
        if key not in objects or key in seen:reject('successor-patch-shape')
        seen.add(key)
        if digest(objects[key])!=patch['beforeSha256']:reject('successor-base-drift')
        replacement=copy.deepcopy(patch['replacement'])
        if replacement.get('id')!=key[1]:reject('successor-patch-identity')
        if key[0]=='entities' and replacement['logicalEntityId']!=objects[key]['logicalEntityId']:reject('successor-logical-identity-change')
        shape(replacement,schema['$defs'][key[0]],schema)
        if references(replacement)-available:reject('missing-reference')
        effective[key]=replacement
        if replacement!=objects[key]:seeds.add(key)
    reciprocal_consistency(effective)
    affected=set(seeds)
    # Reverse dependency fixed point terminates even across reciprocal cycles.
    while True:
        more={key for key,value in effective.items() if references(value)&affected}-affected
        if not more:break
        affected|=more
    changes=sorted(patches,key=lambda p:(p['ref']['kind'],p['ref']['id']))
    change_digest=digest(changes)
    mapping={key:namespace+':'+key[0].lower()+':'+digest([expected_digest,change_digest,list(key)])[:20] for key in sorted(affected)}
    for identity in mapping.values():shape(identity,schema['$defs']['id'],schema)
    if len(set(mapping.values()))!=len(mapping) or set(mapping.values())&{v[1] for v in available}:reject('immutable-id-conflict')
    candidate=[];replacements=[]
    for key,value in sorted(effective.items()):
        updated=rewire(value,mapping)
        if key in mapping:updated['id']=mapping[key]
        shape(updated,schema['$defs'][key[0]],schema)
        candidate.append({'kind':key[0],'value':updated})
        if key in mapping:replacements.append({'from':{'kind':key[0],'id':key[1]},'to':{'kind':key[0],'id':mapping[key]},'beforeSha256':digest(objects[key]),'afterSha256':digest(updated),'value':updated})
    final_refs={(o['kind'],o['value']['id']) for o in candidate}|external
    if any(references(o['value'])-final_refs for o in candidate):reject('missing-reference')
    reciprocal_consistency({(o['kind'],o['value']['id']):o['value'] for o in candidate})
    output={'schema':source['schema'],'objects':candidate,'externalRefs':copy.deepcopy(source['externalRefs'])}
    return {'schema':'al-isabah.knowledge-successor-plan.v1','baseSha256':expected_digest,'patchSha256':change_digest,'namespace':namespace,'replacements':replacements,'candidate':output,'candidateSha256':digest(output),'semanticApprovalCreated':False,'receiptCreated':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--base-sha256',required=True)
    parser.add_argument('--patches',type=Path,required=True);parser.add_argument('--namespace',required=True)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        if args.apply!=bool(args.output):reject('successor-explicit-new-output-required')
        value=plan(read(args.input),args.base_sha256,read(args.patches),args.namespace)
        if args.apply:write_runtime(args.output,value)
        print(digest(value));print('successors='+str(len(value['replacements'])))
        return 0
    except (Rejection,ValueError,OSError,KeyError,TypeError):print('successor-operation-rejected');return 1


if __name__=='__main__':raise SystemExit(main())
