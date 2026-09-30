#!/usr/bin/env python3
"""Prepare and verify immutable local provisional artifacts; never admit or publish."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import knowledge_export_v2_draft3 as graph
import knowledge_pilot_trial as old
from knowledge_export import read,digest,canonical,shape,reject,Rejection,schema_vocabulary
from public_boundary import boundary_errors
from knowledge_local_schema import SCHEMA,check_semantic_identity
from knowledge_local_projection import project_history,validate_projection,profile_value
from knowledge_local_semantics import validate_semantics
from knowledge_local_authorization import subject,authorization_digest,validate_authorization,forbid_authorization_cycle

EVIDENCE={'sourceRegisterSha256':'compliance/source-register.v1.json','rightsMatrixSha256':'compliance/rights-matrix.al-isabah.v1.json',
          'policyBindingSha256':'compliance/policy-binding.v5.json','selectedScopeSha256':'evidence/inventories/issue-0089-selected-scope.v1.json'}


def validate_candidate(snapshot,inventory,profile,bundle):
    schema=read(SCHEMA);check_semantic_identity(schema);schema_vocabulary(schema)
    for name,value in [('snapshot',snapshot),('inventory',inventory),('profile',profile)]:
        shape(value,schema['$defs'][name],schema)
        if boundary_errors(value):reject('prohibited-payload')
    if profile!=profile_value():reject('local-profile-not-registered')
    if snapshot['authority']!=profile['authority'] or inventory['authority']!=profile['authority']:reject('source-identity-mismatch')
    if inventory['reconciliationStatus'] not in {'verified','fresh_derivation_legacy_mapping_unverified'}:reject('source-identity-mismatch')
    if snapshot['profileSha256']!=digest(profile) or snapshot['inventorySha256']!=digest(inventory) or snapshot['receiptBundleSha256']!=digest(bundle):reject('external-pin-mismatch')
    receipts=validate_projection(snapshot,inventory,profile,bundle)
    return validate_semantics(snapshot,inventory,profile,bundle,receipts)


def payload_value(snapshot,inventory):
    batch=snapshot['batch']
    value={'schemaId':'al-isabah.knowledge-export.v2-local1','exportId':batch['exportId'],'batchId':batch['id'],
           'snapshotId':snapshot['id'],'snapshotSha256':digest(snapshot),'selection':copy.deepcopy(batch),'coverage':graph.coverage(snapshot,inventory)}
    for key in ('schemaVersion','mode','fixtureClass','admissionClass','profileSha256','inventorySha256','authority','assessmentSelection',
                'currentSourceSelection','currentSpanDispositionSelection','receiptBundleSha256',*graph.COLLECTIONS):value[key]=copy.deepcopy(snapshot[key])
    value['payloadSha256']=digest(value);shape(value,read(SCHEMA));return value


def bindings_value(snapshot,inventory,profile,bundle,payload,raw_export=None):
    return {'schemaId':'al-isabah.knowledge-local-trust.v1','fixtureClass':'not-a-fixture',
        'snapshotSha256':digest(snapshot),'inventorySha256':digest(inventory),'profileSha256':digest(profile),
        'schemaSha256':digest(read(SCHEMA)),'receiptBundleSha256':digest(bundle),'methodRegistrySha256':profile['methodRegistrySha256'],
        'exportFileSha256':hashlib.sha256(canonical(payload) if raw_export is None else raw_export).hexdigest(),'payloadSha256':payload['payloadSha256'],
        **{key:digest(read(old.ROOT/path)) for key,path in EVIDENCE.items()}}


def verify(snapshot,inventory,profile,bundle,payload,trust,authorization,expected_pin,authority_id,as_of,revoked,requested_use,raw_export):
    schema=read(SCHEMA);shape(trust,schema['$defs']['trust'],schema)
    def unique_pairs(pairs):
        value={}
        for key,item in pairs:
            if key in value:reject('batch-content-mismatch')
            value[key]=item
        return value
    try:decoded=json.loads(raw_export.decode('utf-8'),object_pairs_hook=unique_pairs,parse_constant=lambda _:reject('batch-content-mismatch'))
    except (UnicodeError,ValueError):reject('batch-content-mismatch')
    if decoded!=payload:reject('batch-content-mismatch')
    validate_candidate(snapshot,inventory,profile,bundle)
    if payload!=payload_value(snapshot,inventory):reject('batch-content-mismatch')
    expected={**bindings_value(snapshot,inventory,profile,bundle,payload,raw_export),'upstreamAuthorizationSha256':expected_pin}
    if trust!=expected:reject('external-pin-mismatch')
    for value in (snapshot,inventory,profile,bundle,payload):forbid_authorization_cycle(value,expected_pin)
    validate_authorization(authorization,expected_pin,authority_id,as_of,revoked,payload,trust,requested_use)
    return {'schema':'al-isabah.knowledge-local-export-verification.v1','exportFileSha256':trust['exportFileSha256'],
            'payloadSha256':payload['payloadSha256'],'trustSha256':digest(trust),'authorizationSha256':expected_pin,
            'asOf':as_of,'requestedUse':requested_use,'status':'authorized_local_provisional',
            'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False}


def replay_identity(payloads):
    bindings={};seen=set()
    for payload in payloads:
        shape(payload,read(SCHEMA))
        if digest({k:v for k,v in payload.items() if k!='payloadSha256'})!=payload['payloadSha256']:reject('payload-digest-mismatch')
        for kind,identity,value in [('export',payload['exportId'],payload),('batch',payload['batchId'],payload)]+[(key,x['id'],x) for key in graph.COLLECTIONS for x in payload[key]]:
            key=(kind,identity);pin=digest(value)
            if key in bindings and bindings[key]!=pin:reject('immutable-id-conflict')
            bindings[key]=pin
        seen.add(payload['exportId'])
    return {'uniqueExports':len(seen),'bindings':bindings}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','verify']);parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--prior-bundle',type=Path);parser.add_argument('--history',type=Path);parser.add_argument('--requested-records',type=Path);parser.add_argument('--authorization',type=Path)
    for name in ('authorization-sha256','authority-id','as-of','requested-use'):parser.add_argument('--'+name)
    parser.add_argument('--revoked-authorization-sha256',action='append',default=[]);args=parser.parse_args()
    try:
        old.require_runtime_directory(args.directory)
        if args.action=='prepare':
            if args.directory.exists():reject('local-new-output-directory-required')
            if not args.history or not args.requested_records:reject('local-projection-input-required')
            snapshot,inventory,profile,bundle=project_history(read(args.history),read(args.requested_records),read(args.prior_bundle) if args.prior_bundle else None);validate_candidate(snapshot,inventory,profile,bundle)
            payload=payload_value(snapshot,inventory);bindings=bindings_value(snapshot,inventory,profile,bundle,payload)
            for name,value in [('snapshot',snapshot),('inventory',inventory),('profile',profile),('receipts',bundle),('export',payload),('bindings',bindings)]:old.write_new(args.directory/(name+'.json'),value)
            request={'schema':'al-isabah.knowledge-local-authorization-request.v1','subjectSha256':subject(bindings),'bindings':bindings,
                     'requestedLogicalRecordIds':payload['selection']['requestedLogicalRecordIds'],'dependencyLogicalRecordIds':payload['selection']['dependencyLogicalRecordIds'],
                     'coverage':payload['coverage'],'consumerAdmissionAuthorized':False,'publicReleaseAuthorized':False}
            old.write_new(args.directory/'authorization-request.json',request);print(digest(request));return 0
        if not all([args.authorization,args.authorization_sha256,args.authority_id,args.as_of,args.requested_use]):reject('local-external-authorization-required')
        values={name:read(args.directory/(name+'.json')) for name in ('snapshot','inventory','profile','receipts','export','bindings')}
        trust={**values['bindings'],'upstreamAuthorizationSha256':args.authorization_sha256}
        report=verify(values['snapshot'],values['inventory'],values['profile'],values['receipts'],values['export'],trust,read(args.authorization),
                      args.authorization_sha256,args.authority_id,args.as_of,args.revoked_authorization_sha256,args.requested_use,(args.directory/'export.json').read_bytes())
        old.write_new(args.directory/'trust.json',trust);old.write_new(args.directory/('verification-'+digest(report)[:16]+'.json'),report)
        print(digest(report));return 0
    except (Rejection,OSError,ValueError,KeyError,TypeError,RecursionError):print('local-export-operation-rejected');return 1


if __name__=='__main__':raise SystemExit(main())
