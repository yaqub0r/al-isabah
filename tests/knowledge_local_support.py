"""Authored conformance history only: no real source content, approval, or host run."""
import copy
import sys
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from test_knowledge_pilot_trial import launch
from knowledge_export_v2_draft3_support import capabilities,helper_input
import knowledge_successors as successors
import knowledge_local_execution as execution
import knowledge_local_projection as projection
import knowledge_export_local as local
import knowledge_pilot_trial as old
import knowledge_pilot_remediation as remediation
from knowledge_export import digest,read,canonical


def packet_fixture():
    packet={'schema':'al-isabah.knowledge-pilot-input.v1','issue':89,'sourceArtifactSha256':projection.profile_value()['authority']['sourceArtifactSha256'],
            'candidateManifestSha256':'2'*64,'records':[],'units':[],'policyPins':{p:old.assembly.lf_sha(ROOT/p) for p in old.assembly.POLICIES},
            'assemblerLfSha256':old.assembly.lf_sha(Path(old.assembly.__file__)),'packetSha256':''}
    for n,ordinal in enumerate(old.assembly.preparation.ORDINALS):
        rid='urn:al-isabah:trial:source-record:conformance-'+str(n);uid='conformance-unit-'+str(n)
        raw='### $ '+str(ordinal)+' Synthetic Alpha Synthetic Beta\n~~ Authored conformance text only.\n'
        packet['records'].append({'id':rid,'sourceOrdinal':ordinal,'sourceUnitIds':[uid],'retainedFindings':[{'category':'synthetic','priority':'review'}],
                                  'candidateEnglish':{'title':'Synthetic English'},'candidateRecordSha256':'3'*64})
        packet['units'].append({'id':uid,'kind':'entry','sourceRecordVersionId':rid,'rawSha256':old.assembly.sha(raw.encode()),'spans':old.assembly.partition_unit(uid,raw)})
    packet['packetSha256']=digest({k:v for k,v in packet.items() if k!='packetSha256'})
    partition={'packetSha256':packet['packetSha256'],'packetFileSha256':digest(packet),'sourceOrdinals':list(old.assembly.preparation.ORDINALS),
        'methodRegistrySha256':digest(read(old.method.REGISTRY_PATH)),
        'units':[{**{k:u[k] for k in ('id','kind','sourceRecordVersionId','rawSha256')},'spans':[{k:v for k,v in s.items() if k!='rawOpeniti'} for s in u['spans']]} for u in packet['units']]}
    partition['partitionSha256']=digest(partition)
    return packet,partition


def empty_output(stage,packet):
    output={'schema':'al-isabah.knowledge-pilot-stage-output.v1','stage':stage['stage'],'stageInputSha256':digest(stage),'packetSha256':packet['packetSha256'],
            'status':'partial','spanDispositions':[],'recordReviews':[],'concerns':[],'retainedFindingCoverage':[],'mentionEvidence':[],'nonclaimReviews':[],**{k:[] for k in old.COLLECTIONS}}
    for record,unit in zip(packet['records'],packet['units']):
        rid=record['id'];cid='urn:al-isabah:trial:concern:conformance-'+str(record['sourceOrdinal'])
        for span in unit['spans']:output['spanDispositions'].append({'sourceSpanId':span['id'],'status':'unsupported_semantics','reasonCode':'unsupported','claimIds':[],'reportIds':[],'ambiguityGroupIds':[],'findingIds':[]})
        output['recordReviews'].append({'sourceRecordVersionId':rid,**{k:'unresolved' for k in old.REVIEW_AXES},'findingIds':[],'rationale':'Synthetic unresolved fixture only.'})
        output['concerns'].append({'id':cid,'sourceSpanIds':[s['id'] for s in unit['spans']],'category':'vocabulary','status':'open','rationale':'Synthetic unprocessed fixture concern.'})
        output['retainedFindingCoverage'].append({'sourceFindingId':rid+':retained-finding:1','concernIds':[cid],'status':'retained'})
    return output


def rich_output(stage,packet):
    seed,inventory,*_=capabilities()
    oldrecords=sorted(seed['sourceRecords'],key=lambda x:x['id']);mapping={r['id']:packet['records'][n]['id'] for n,r in enumerate(oldrecords)}
    mapping.update({'urn:al-isabah:synthetic:'+key:'urn:al-isabah:'+value for key,value in {'predicate:1':'predicate:spouse-of','predicate:2':'predicate:participated-in','predicate:3':'predicate:has-quantity','event-type:1':'event-type:encounter','role:1':'role:actor'}.items()})
    for span in inventory['sourceSpans']:
        owner=next(r for r in oldrecords if span['sourceUnitId'] in r['authorityUnitIds'])
        mapping[span['id']]=packet['units'][oldrecords.index(owner)]['spans'][0]['id']
    def convert(value):
        if isinstance(value,str):
            if value in mapping:return mapping[value]
            for domain in ('predicate','event-type','role'):
                prefix='urn:al-isabah:synthetic:'+domain+':'
                if value.startswith(prefix):return 'urn:al-isabah:'+domain+':'+value[len(prefix):]
            return value.replace('urn:al-isabah:synthetic:','urn:al-isabah:trial:conformance:')
        if isinstance(value,list):return [convert(v) for v in value]
        if isinstance(value,dict):
            result={k:convert(v) for k,v in value.items()}
            for k in ('assessmentIds','identityAssessmentIds','criticalAssessmentIds'):
                if k in result:result[k]=[]
            for k in ('artifactIds','evidenceArtifactIds'):
                if result.get(k):result[k]=['urn:al-isabah:trial:artifact:authority']
            return result
        return value
    output=empty_output(stage,packet);output['schema']='al-isabah.knowledge-pilot-stage-output.v2'
    for key in old.COLLECTIONS:output[key]=convert(seed[key])
    spans={s['id']:s for u in packet['units'] for s in u['spans']};names={n['id']:n for n in output['names']}
    for mention in output['mentions']:
        form=names[mention['nameId']]['form'];raw=spans[mention['sourceSpanId']]['rawOpeniti'];a=raw.index(form)
        mention['surfaceSha256']=old.assembly.sha(form.encode('utf-8'));names[mention['nameId']]['sourceSurfaceSha256']=mention['surfaceSha256']
        output['mentionEvidence'].append({'mentionId':mention['id'],'sourceSpanId':mention['sourceSpanId'],'startChar':a,'endChar':a+len(form)})
    for n,row in enumerate(output['spanDispositions']):
        sid=row['sourceSpanId'];claims=[v for v in output['claims'] if sid in v['sourceSpanIds']];reports=[v for v in output['reports'] if sid in v['sourceSpanIds']]
        if claims or reports:
            groups=sorted({g for v in claims+reports for g in v['ambiguityGroupIds']})
            row.update(status='represented_uncertain' if groups else 'represented',reasonCode='uncertain' if groups else 'mapped',
                       claimIds=[v['id'] for v in claims],reportIds=[v['id'] for v in reports],ambiguityGroupIds=groups)
            output['recordReviews'][n].update({k:'checked' for k in old.REVIEW_AXES});output['concerns'][n]['status']='resolved';output['retainedFindingCoverage'][n]['status']='resolved'
    return output


def corrected_output(output):
    source=helper_input(output)
    oldq=next(x['value'] for x in source['objects'] if x['kind']=='qualifications' and x['value']['id'].endswith(':pledged-quantity'))
    replacement={**oldq,'criticalStatus':'disputed'}
    plan=successors.plan(source,digest(source),[{'ref':{'kind':'qualifications','id':oldq['id']},'beforeSha256':digest(oldq),'replacement':replacement}],
                         'urn:al-isabah:trial:conformance:successor:local-correction')
    mapping={(x['from']['kind'],x['from']['id']):x['to']['id'] for x in plan['replacements']}
    value=successors.rewire(copy.deepcopy(output),mapping)
    for row in value['mentionEvidence']:row['mentionId']=mapping.get(('mentions',row['mentionId']),row['mentionId'])
    for key in old.COLLECTIONS:value[key]=[x['value'] for x in plan['candidate']['objects'] if x['kind']==key]
    return value


def history_fixture(label='initial',correction=False):
    packet,partition=packet_fixture();prior=[]
    with mock.patch.object(old,'verify_checkout'):
        req=old.decision_request(packet,partition,execution.EXECUTION_COMMIT)
        decision={'schema':'al-isabah.knowledge-local-trial-decision.v1','request':req,'approval':'approved',
                  'origin':{'kind':'actual_user_message','threadId':old.COORDINATOR,'userTurnReference':'SYNTHETIC-CONFORMANCE-ONLY','recordedBy':'trusted_coordinator'}}
        task=launch('codex-task','synthetic-baseline-task')
        for n,name in enumerate(old.STAGES):
            stage=old.prepare_stage(name,decision,digest(decision),packet,partition,execution.EXECUTION_COMMIT,prior);output=empty_output(stage,packet)
            receipt=old.capture(stage,output,packet,digest(decision),task,launch('codex-worker','synthetic-baseline-worker-'+str(n),'synthetic-baseline-task'),[x['receipt'] for x in prior])
            prior.append({'input':stage,'output':output,'receipt':receipt})
        report=old.final_report(decision,digest(decision),packet,partition,execution.EXECUTION_COMMIT,prior)
    baseline=remediation.baseline_value(prior,report,digest(report),packet)
    decision={**decision,'schema':'al-isabah.knowledge-remediation-decision.v1','request':execution.expected_request(packet,partition,baseline)}
    stages=[];task=launch('codex-task','synthetic-local-'+label)
    for n,name in enumerate(old.STAGES):
        stage=execution.expected_input(name,decision['request'],digest(decision),packet,partition,baseline,stages)
        output=rich_output(stage,packet)
        if correction and n==2:output=corrected_output(output)
        proposal={'schema':'al-isabah.knowledge-remediation-proposal.v1','output':output,'baselineSha256':digest(baseline),'objectSuccessors':[],
                  'concernOutcomes':[{'baselineConcernId':c['id'],'baselineConcernSha256':digest(c),'outcome':'resolved' if output['concerns'][i]['status']=='resolved' else 'residual','rationale':'Synthetic conformance outcome only.'} for i,c in enumerate(remediation.baseline_output(baseline)['concerns'])]}
        receipt=remediation.capture(stage,proposal,packet,digest(decision),task,launch('codex-worker','synthetic-local-'+label+'-'+str(n),'synthetic-local-'+label),[x['receipt'] for x in stages])
        stages.append({'input':stage,'proposal':proposal,'receipt':receipt})
    return {'schema':execution.HISTORY_SCHEMA,'decision':decision,'partition':partition,'baseline':baseline,'stages':stages,
            'report':execution.expected_report(decision,packet,partition,baseline,stages)}


def artifact_fixture(label='initial',correction=False):
    history=history_fixture(label,correction);requested=sorted(r['id'] for r in history['stages'][0]['input']['lockedInput']['records'])
    prior=None
    if correction:
        previous=history_fixture('initial');prior=projection.project_history(previous,requested)[3]
    snapshot,inventory,profile,bundle=projection.project_history(history,requested,prior)
    local.validate_candidate(snapshot,inventory,profile,bundle);payload=local.payload_value(snapshot,inventory)
    bindings=local.bindings_value(snapshot,inventory,profile,bundle,payload)
    authorization={'schema':'al-isabah.knowledge-local-authorization.v1','id':'synthetic-conformance-authorization-'+label,
        'authorityId':'synthetic-conformance-owner','subjectSha256':local.subject(bindings),
        'allowedUses':['local_noncommercial_reading','local_noncommercial_narrative'],
        'allowedUseTiers':['factual_spine','qualified_context','attributed_disputed_report','not_for_narrative'],'acceptPartial':True,
        'requestedLogicalRecordIds':copy.deepcopy(payload['selection']['requestedLogicalRecordIds']),'dependencyLogicalRecordIds':copy.deepcopy(payload['selection']['dependencyLogicalRecordIds']),
        'effectiveAt':'2026-01-01T00:00:00Z','observedAt':'2026-01-01T00:00:00Z',
        'validity':{'policy':'until_revoked','notBefore':'2026-01-01T00:00:00Z','notAfter':''},
        'origin':{'kind':'actual_user_message','threadId':'synthetic-conformance-owner-task','userTurnReference':'SYNTHETIC-ONLY-NO-ACTUAL-APPROVAL','recordedBy':'trusted_coordinator'}}
    trust={**bindings,'upstreamAuthorizationSha256':local.authorization_digest(authorization)}
    return {'snapshot':snapshot,'inventory':inventory,'profile':profile,'receipts':bundle,'export':payload,'authorization':authorization,'trust':trust}


def corpus(write=False):
    root=ROOT/'tests/fixtures/knowledge-export-v2-local1'
    manifest={'schema':'al-isabah.local-conformance-corpus.v1','fixtureClass':'synthetic-conformance','actualApproval':False,'actualExecution':False,
              'schemaSha256':digest(read(local.SCHEMA)),'artifacts':[]}
    for label,correction in [('initial',False),('correction',True)]:
        for name,value in artifact_fixture(label,correction).items():
            path=root/label/(name+'.json');encoded=canonical(value)
            if write:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encoded)
            elif path.read_bytes()!=encoded:raise AssertionError(str(path)+' does not reproduce')
            manifest['artifacts'].append({'path':path.relative_to(ROOT).as_posix(),'canonicalSha256':digest(value),'fileSha256':old.assembly.sha(encoded),'bytes':len(encoded)})
    path=root/'adversarial-cases.json';value=read(path)
    manifest['artifacts'].append({'path':path.relative_to(ROOT).as_posix(),'canonicalSha256':digest(value),'fileSha256':old.assembly.sha(path.read_bytes()),'bytes':path.stat().st_size})
    if write:(root/'manifest.json').write_bytes(canonical(manifest))
    elif read(root/'manifest.json')!=manifest:raise AssertionError('local corpus manifest differs')
    return manifest


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');args=parser.parse_args()
    print(digest(corpus(args.write)))
