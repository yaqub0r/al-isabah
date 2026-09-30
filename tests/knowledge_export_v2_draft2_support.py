"""Deterministic synthetic draft2 checkpoints, including immutable corrections."""
import copy
import json
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import knowledge_export_v2_draft2 as k
import knowledge_runtime_draft as runtime
import host_runtime
from knowledge_export_v2_support import fixture as draft1_fixture,uid,date


def launch(kind,identity):
    # Exercise actual metadata parsing using authored SYNTHETIC host logs only.
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'synthetic.jsonl'
        path.write_text('\n'.join(json.dumps(x) for x in [
            {'type':'session_meta','payload':{'id':identity,'model_provider':'openai'}},
            {'type':'turn_context','payload':{'turn_id':'turn','model':'gpt-5.6-sol','effort':'xhigh'}}
        ])+'\n',encoding='utf-8')
        observed=host_runtime.observe_session(path,identity,'turn')
    return {'request':host_runtime.launch_request(kind,'gpt-5.6-sol','xhigh'),'observed':observed}


def seal(s,i,p,b):
    for collection in k.COLLECTIONS:s[collection].sort(key=lambda x:x['id'])
    for key in ('currentSourceSelection','assessmentSelection','currentSpanDispositionSelection'):
        s[key].sort(key=lambda x:k.canonical(x))
    s['inventorySha256']=k.digest(i);s['profileSha256']=k.digest(p);s['receiptBundleSha256']=k.digest(b)
    return {'schemaId':'al-isabah.knowledge-draft2-trust.v2','fixtureClass':'synthetic-conformance','snapshotSha256':k.digest(s),'inventorySha256':k.digest(i),'profileSha256':k.digest(p),'schemaSha256':k.digest(k.read(k.SCHEMA_PATH)),'receiptBundleSha256':k.digest(b)}


def bind_assessments(s):
    maps={key:k.indexed(s[key]) for key in k.COLLECTIONS}
    for assessment in s['assessments']:
        assessment['inputs']=[{'ref':copy.deepcopy(r),'sha256':k.digest(maps[r['kind']][r['id']])} for r in assessment['targets']]


def attach_chain(s,i,p,b,registry,label,requested=None,dependencies=()):
    if requested is None:
        current={x['logicalRecordId']:x['sourceRecordVersionId'] for x in s['currentSourceSelection']}
        attach_chain(s,i,p,b,registry,label+'-a',[current[uid('logical',1)],current[uid('logical',3)]])
        attach_chain(s,i,p,b,registry,label+'-b',[current[uid('logical',2)]])
        return
    task=launch('codex-task','synthetic-task-'+label)
    requested=sorted(requested);dependencies=sorted(dependencies)
    record_ids=sorted(requested+dependencies)
    records=k.indexed(s['sourceRecords']);outputs=k.semantic_projection(s,requested,dependencies)
    chain=[]
    for n,stage in enumerate(runtime.STAGES):
        inputs={'inventorySha256':k.digest(i),'profileSha256':k.digest(p),'sourceRecords':[{'id':rid,'sha256':k.digest(records[rid])} for rid in record_ids],'requestedSourceRecordVersionIds':requested,'dependencySourceRecordVersionIds':dependencies,'upstreamOutputSha256':chain[-1]['outputSha256'] if chain else ''}
        receipt=runtime.make_receipt(uid('receipt',label+'-'+str(n)),stage,record_ids,inputs,outputs,task,launch('codex-worker','synthetic-worker-'+label+'-'+str(n)),chain[-1:],registry,'synthetic-conformance')
        b['receipts'].append(receipt);b['bindings'].append({'receiptId':receipt['id'],'inputs':inputs,'outputs':copy.deepcopy(outputs)})
        s['artifacts'].append({'id':receipt['id'],'kind':'knowledge_receipt','sha256':k.digest(receipt),'status':'synthetic_only'})
        chain.append(receipt)
    assessments=k.indexed(s['assessments'])
    for selection in s['assessmentSelection']:
        if selection['sourceRecordVersionId'] not in requested:continue
        assessments[selection['extractionAssessmentId']]['receiptArtifactIds']=[r['id'] for r in chain]


def fixture():
    s,i,p,_=draft1_fixture();registry=k.read(runtime.REGISTRY_PATH)
    s['schemaVersion']='2.0.0-draft.2';i['schemaId']='al-isabah.knowledge-inventory.v2-draft2'
    p.update(schemaId='al-isabah.knowledge-profile.v2-draft2',version='2.0.0-draft.2',methodRegistrySha256=k.digest(registry))
    s['currentSourceSelection']=[{'logicalRecordId':r['logicalRecordId'],'sourceRecordVersionId':r['id']} for r in s['sourceRecords']]
    s['names']=[];s['currentSpanDispositionSelection']=[]
    for entity in s['entities']:
        entity['logicalEntityId']=entity['id'].replace(':entities:',':logical-entity:');entity['nameIds']=[]
    for n,mention in enumerate(s['mentions'],1):
        identity=uid('names',n);mention['nameId']=identity
        name={'id':identity,'entityId':mention['entityId'],'language':'en','form':'Synthetic Alpha' if n==1 else 'Synthetic Beta','formRole':mention['nameRole'],'derivation':'transliteration','sourceRecordVersionId':mention['sourceRecordVersionId'],'sourceSpanId':mention['sourceSpanId'],'sourceSurfaceSha256':mention['surfaceSha256'],'assessmentIds':[],'ambiguityGroupIds':[]}
        s['names'].append(name);next(e for e in s['entities'] if e['id']==name['entityId'])['nameIds'].append(identity)
    for value in s['values']:value['amountNumerator']=value.pop('amount');value['amountDenominator']=1
    for assessment in s['assessments']:assessment['receiptArtifactIds']=[]
    for row in s['spanDispositions']:
        span=next(x for x in i['sourceSpans'] if x['id']==row['sourceSpanId'])
        record=next(x for x in s['sourceRecords'] if span['sourceUnitId'] in x['authorityUnitIds'])
        row['sourceRecordVersionId']=record['id']
        s['currentSpanDispositionSelection'].append({'sourceRecordVersionId':record['id'],'sourceSpanId':span['id'],'spanDispositionId':row['id']})
        selection=next(x for x in s['assessmentSelection'] if x['sourceRecordVersionId']==record['id'])
        extraction=next(x for x in s['assessments'] if x['id']==selection['extractionAssessmentId'])
        extraction['targets'].append({'kind':'spanDispositions','id':row['id']})
    bind_assessments(s)
    b={'schema':'al-isabah.knowledge-receipt-bundle.v1-draft','fixtureClass':'synthetic-conformance','registrySha256':k.digest(registry),'receipts':[],'bindings':[]}
    attach_chain(s,i,p,b,registry,'initial')
    return s,i,p,seal(s,i,p,b),b,registry


def new_snapshot_ids(s,label):
    s['id']=uid('snapshot',label);s['batch']['id']=uid('batch',label);s['batch']['exportId']=uid('export',label)


def correction(base,source_change):
    s,i,p,_,b,registry=copy.deepcopy(base);label='source-correction' if source_change else 'extraction-correction'
    new_snapshot_ids(s,label)
    original={key:copy.deepcopy(s[key]) for key in k.COLLECTIONS}
    replacements={}
    kinds=[c for c in k.COLLECTIONS if c not in {'sourceRecords','actors','artifacts','lifecycleEvents'}]
    for kind in kinds:
        replacements.update({v['id']:v['id']+'-'+label for v in original[kind]})
    if source_change:replacements[uid('sourceRecords',1)]=uid('sourceRecords',1)+'-'+label
    def replace(value):
        if isinstance(value,str):return replacements.get(value,value)
        if isinstance(value,list):return [replace(x) for x in value]
        if isinstance(value,dict):return {key:replace(child) for key,child in value.items()}
        return value
    for kind in kinds+(['sourceRecords'] if source_change else []):
        for old in original[kind]:
            if old['id'] not in replacements:continue
            new=replace(old)
            if kind=='sourceRecords':new['recordSha256']=k.digest('synthetic-corrected-record-bytes')
            if kind=='assessments':new['receiptArtifactIds']=[]
            s[kind].append(new)
            s['lifecycleEvents'].append({'id':uid('lifecycleEvents',label+'-'+kind.lower()+'-'+old['id'].rsplit(':',1)[-1]),'kind':'corrects','targets':[{'kind':kind,'id':old['id']}],'replacements':[{'kind':kind,'id':new['id']}],'effectiveAt':date(True),'decisionArtifactId':uid('artifacts',4),'dependencyIds':[]})
    for key in ('currentSourceSelection','assessmentSelection','currentSpanDispositionSelection'):s[key]=replace(s[key])
    # Only successor assessments may change; history remains byte-identical.
    maps={key:k.indexed(s[key]) for key in k.COLLECTIONS}
    for assessment in s['assessments']:
        if assessment['id'] in replacements.values():
            assessment['inputs']=[{'ref':copy.deepcopy(r),'sha256':k.digest(maps[r['kind']][r['id']])} for r in assessment['targets']]
    attach_chain(s,i,p,b,registry,label)
    return s,i,p,seal(s,i,p,b),b,registry


def reaffirmation(base):
    s,i,p,_,b,registry=copy.deepcopy(base);label='reaffirmation';new_snapshot_ids(s,label)
    amap=k.indexed(s['assessments'])
    for selection in s['assessmentSelection']:
        old=amap[selection['extractionAssessmentId']];new=copy.deepcopy(old)
        new['id']=old['id']+'-'+label;new['predecessorIds']=[old['id']];new['receiptArtifactIds']=[]
        s['assessments'].append(new);selection['extractionAssessmentId']=new['id']
        s['lifecycleEvents'].append({'id':uid('lifecycleEvents',label+'-'+old['id'].rsplit(':',1)[-1]),'kind':'supersedes','targets':[{'kind':'assessments','id':old['id']}],'replacements':[{'kind':'assessments','id':new['id']}],'effectiveAt':date(True),'decisionArtifactId':uid('artifacts',4),'dependencyIds':[]})
    attach_chain(s,i,p,b,registry,label)
    return s,i,p,seal(s,i,p,b),b,registry


def independent_correction(base):
    s,i,p,_,b,registry=copy.deepcopy(base);label='independent-correction';new_snapshot_ids(s,label)
    rid=uid('sourceRecords',2)
    selection=next(x for x in s['assessmentSelection'] if x['sourceRecordVersionId']==rid)
    row_selection=next(x for x in s['currentSpanDispositionSelection'] if x['sourceRecordVersionId']==rid)
    old_a=next(x for x in s['assessments'] if x['id']==selection['extractionAssessmentId'])
    old_row=next(x for x in s['spanDispositions'] if x['id']==row_selection['spanDispositionId'])
    new_a=copy.deepcopy(old_a);new_a['id']+='-'+label;new_a['receiptArtifactIds']=[]
    new_row=copy.deepcopy(old_row);new_row['id']+='-'+label;new_row['assessmentIds']=[new_a['id']]
    new_a['targets']=[{'kind':'sourceRecords','id':rid},{'kind':'spanDispositions','id':new_row['id']}]
    record=next(x for x in s['sourceRecords'] if x['id']==rid)
    new_a['inputs']=[{'ref':new_a['targets'][0],'sha256':k.digest(record)},{'ref':new_a['targets'][1],'sha256':k.digest(new_row)}]
    s['assessments'].append(new_a);s['spanDispositions'].append(new_row)
    selection['extractionAssessmentId']=new_a['id'];row_selection['spanDispositionId']=new_row['id']
    for kind,old,new in [('assessments',old_a,new_a),('spanDispositions',old_row,new_row)]:
        s['lifecycleEvents'].append({'id':uid('lifecycleEvents',label+'-'+kind.lower()),'kind':'corrects','targets':[{'kind':kind,'id':old['id']}],'replacements':[{'kind':kind,'id':new['id']}],'effectiveAt':date(True),'decisionArtifactId':uid('artifacts',4),'dependencyIds':[]})
    attach_chain(s,i,p,b,registry,label,[rid])
    return s,i,p,seal(s,i,p,b),b,registry


def export(data):
    s,i,p,t,b,r=data
    return k.build(s,i,p,t,s['batch']['id'],b,r)


if __name__=='__main__':
    directory=ROOT/'tests/fixtures/knowledge-export-v2-draft2';directory.mkdir(parents=True,exist_ok=True)
    base=fixture()
    for label,data in [('initial',base),('source-correction',correction(base,True)),('extraction-correction',correction(base,False)),('reaffirmation',reaffirmation(base)),('independent-correction',independent_correction(base))]:
        payload=export(data)
        target=directory/label;target.mkdir(exist_ok=True)
        for name,value in zip(('snapshot','inventory','profile','trust','receipts','knowledge-method-registry'),data):(target/(name+'.json')).write_bytes(k.canonical(value))
        (target/'batch.json').write_bytes(k.canonical(payload))
    print('synthetic-draft2-fixtures-written')
