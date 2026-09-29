#!/usr/bin/env python3
"""Deterministic metadata-only companion to the frozen draft3 semantic contract."""
import argparse
import copy
from pathlib import Path
from knowledge_export import read,canonical,digest,reject
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'schemas/al-isabah-knowledge-export.v2-draft3.schema.json'
SCHEMA=ROOT/'schemas/al-isabah-knowledge-export.v2-local1.schema.json'
VERSION='2.0.0-local.1'
MODIFIED_DEFS={'snapshot','inventory','profile','rights','trust'}
USES=['local_noncommercial_reading','local_noncommercial_narrative']
TIERS=['factual_spine','qualified_context','attributed_disputed_report','not_for_narrative']


def closed(properties):return {'type':'object','additionalProperties':False,'required':list(properties),'properties':properties}
def strings(values=None):
    value={'type':'string','pattern':'^.+$'}
    if values is not None:value['enum']=values
    return {'type':'array','items':value,'minItems':1,'uniqueItems':True}


def schema():
    value=copy.deepcopy(read(BASE));defs=value['$defs'];value['$id']='urn:al-isabah:knowledge-export:v2-local1'
    for target,name in [(value,'export'),(defs['snapshot'],'snapshot')]:
        target['properties']['schemaId']={'const':'al-isabah.knowledge-'+name+'.v2-local1'}
        target['properties']['schemaVersion']={'const':VERSION}
        target['properties']['mode']={'const':'real'};target['properties']['fixtureClass']={'const':'not-a-fixture'}
        target['properties']['admissionClass']={'const':'local_provisional'};target['required'].append('admissionClass')
    profile=defs['profile']['properties']
    profile.update(schemaId={'const':'al-isabah.knowledge-profile.v2-local1'},version={'const':VERSION},status={'const':'local_provisional'},
                   mode={'const':'real'},realExecutionEnabled={'const':False},realAdmissionEnabled={'const':True})
    defs['inventory']['properties']['schemaId']={'const':'al-isabah.knowledge-inventory.v2-local1'}
    defs['rights']['properties']['basis']={'const':'cc_by_nc_sa_4_0'}
    defs['rights']['properties']['approvalStatus']={'const':'requires_exact_local_authorization'}
    trust=defs['trust']['properties'];trust['schemaId']={'const':'al-isabah.knowledge-local-trust.v1'};trust['fixtureClass']={'const':'not-a-fixture'}
    for key in ['exportFileSha256','payloadSha256','methodRegistrySha256','sourceRegisterSha256','rightsMatrixSha256','policyBindingSha256','selectedScopeSha256','upstreamAuthorizationSha256']:
        trust[key]={'$ref':'#/$defs/hash'};defs['trust']['required'].append(key)
    text={'type':'string','pattern':'^.+$'};timestamp={'type':'string','pattern':r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$'}
    defs['localValidity']=closed({'policy':{'enum':['until_revoked','bounded']},'notBefore':timestamp,'notAfter':{'type':'string'}})
    defs['localAuthorization']=closed({'schema':{'const':'al-isabah.knowledge-local-authorization.v1'},'id':text,'authorityId':text,
        'subjectSha256':{'$ref':'#/$defs/hash'},'allowedUses':strings(USES),'allowedUseTiers':strings(TIERS),'acceptPartial':{'type':'boolean'},
        'requestedLogicalRecordIds':{'$ref':'#/$defs/ids'},'dependencyLogicalRecordIds':{'$ref':'#/$defs/ids'},
        'effectiveAt':timestamp,'observedAt':timestamp,'validity':{'$ref':'#/$defs/localValidity'},
        'origin':closed({'kind':{'const':'actual_user_message'},'threadId':text,'userTurnReference':{'type':'string'},'recordedBy':{'const':'trusted_coordinator'}})})
    return value


def check_semantic_identity(value):
    base=read(BASE)
    if value!=schema():reject('local-schema-overlay-mismatch')
    for name,definition in base['$defs'].items():
        if name not in MODIFIED_DEFS and value['$defs'][name]!=definition:reject('local-semantic-definition-drift')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    value=schema();check_semantic_identity(value)
    if args.check:
        if SCHEMA.read_bytes()!=canonical(value):reject('local-schema-overlay-mismatch')
    else:
        with SCHEMA.open('xb') as stream:stream.write(canonical(value))
    print(digest(value));return 0


if __name__=='__main__':raise SystemExit(main())
