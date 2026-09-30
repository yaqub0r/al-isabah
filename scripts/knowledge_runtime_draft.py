"""Draft knowledge-stage receipt binding using existing trusted-host checks.

Full receipts remain upstream. Only artifact identities/digests cross export.
Real execution is deliberately disabled pending an actual method decision.
"""
import copy
from pathlib import Path
import host_runtime
from knowledge_export import read,canonical,digest,reject
from schema_validation import validate_schema_instance

ROOT=Path(__file__).resolve().parents[1]
REGISTRY_PATH=ROOT/'profiles/knowledge/execution-methods.v1-draft.json'
SCHEMA_PATH=ROOT/'schemas/knowledge-runtime-receipt.v1-draft.schema.json'
STAGES=('knowledge_extraction','knowledge_independent_review','knowledge_adjudication')

def configuration(registry):
    if registry != read(REGISTRY_PATH):reject('knowledge-registry-mismatch')
    return registry['methods'][0]['configuration']

def checkpoint(receipt):
    return digest({key:receipt[key] for key in ('methodId','registrySha256','stage','sourceRecordVersionIds','inputSha256','outputSha256','upstreamReceiptIds','task','worker')})

def make_receipt(identity,stage,record_ids,inputs,outputs,task,worker,upstream,registry,fixture_class):
    if fixture_class!='synthetic-conformance':reject('real-method-disabled')
    config=configuration(registry)
    if stage not in STAGES:reject('knowledge-stage-mismatch')
    if host_runtime.launch_errors(task,config,'codex-task') or host_runtime.launch_errors(worker,config,'codex-worker'):reject('knowledge-host-mismatch')
    if task['observed']['sessionId']==worker['observed']['sessionId']:reject('knowledge-independence-mismatch')
    receipt={'schema':'al-isabah.knowledge-runtime-receipt.v1-draft','id':identity,'fixtureClass':fixture_class,'methodId':registry['methods'][0]['methodId'],'registrySha256':digest(registry),'stage':stage,'sourceRecordVersionIds':sorted(record_ids),'inputSha256':digest(inputs),'outputSha256':digest(outputs),'checkpointSha256':'0'*64,'upstreamReceiptIds':[r['id'] for r in upstream],'task':copy.deepcopy(task),'worker':copy.deepcopy(worker),'receiptSha256':'0'*64}
    receipt['checkpointSha256']=checkpoint(receipt);receipt['receiptSha256']=digest({k:v for k,v in receipt.items() if k!='receiptSha256'})
    return receipt

def validate_bundle(bundle,registry,expected_sha256):
    if digest(bundle)!=expected_sha256:reject('knowledge-receipt-bundle-pin-mismatch')
    if set(bundle)!={'schema','fixtureClass','registrySha256','receipts','bindings'} or bundle['schema']!='al-isabah.knowledge-receipt-bundle.v1-draft' or bundle['fixtureClass']!='synthetic-conformance':reject('knowledge-receipt-shape-mismatch')
    config=configuration(registry)
    if bundle['registrySha256']!=digest(registry):reject('knowledge-registry-mismatch')
    if not isinstance(bundle['receipts'],list) or not isinstance(bundle['bindings'],list):reject('knowledge-receipt-shape-mismatch')
    receipts={r.get('id'):r for r in bundle['receipts']}
    bindings={r.get('receiptId'):r for r in bundle['bindings']}
    if len(receipts)!=len(bundle['receipts']) or len(bindings)!=len(bundle['bindings']) or set(receipts)!=set(bindings):reject('knowledge-receipt-coverage-mismatch')
    for rid,receipt in receipts.items():
        if validate_schema_instance(receipt,read(SCHEMA_PATH)):reject('knowledge-receipt-shape-mismatch')
        if receipt['fixtureClass']!='synthetic-conformance':reject('real-method-disabled')
        if receipt['registrySha256']!=digest(registry):reject('knowledge-registry-mismatch')
        if host_runtime.launch_errors(receipt['task'],config,'codex-task') or host_runtime.launch_errors(receipt['worker'],config,'codex-worker'):reject('knowledge-host-mismatch')
        if receipt['worker']['observed']['sessionId']==receipt['task']['observed']['sessionId']:reject('knowledge-independence-mismatch')
        if checkpoint(receipt)!=receipt['checkpointSha256'] or digest({k:v for k,v in receipt.items() if k!='receiptSha256'})!=receipt['receiptSha256']:reject('knowledge-receipt-binding-mismatch')
        binding=bindings[rid]
        if set(binding)!={'receiptId','inputs','outputs'} or digest(binding['inputs'])!=receipt['inputSha256'] or digest(binding['outputs'])!=receipt['outputSha256']:reject('knowledge-receipt-binding-mismatch')
        stage_index=STAGES.index(receipt['stage'])
        if len(receipt['upstreamReceiptIds']) != (0 if stage_index==0 else 1):reject('knowledge-stage-chain-mismatch')
        if stage_index:
            previous=receipts.get(receipt['upstreamReceiptIds'][0])
            if not previous or previous['stage']!=STAGES[stage_index-1] or previous['sourceRecordVersionIds']!=receipt['sourceRecordVersionIds']:reject('knowledge-stage-chain-mismatch')
            if binding['inputs'].get('upstreamOutputSha256')!=previous['outputSha256']:reject('knowledge-stage-chain-mismatch')
            chain=[previous]
            while chain[-1]['upstreamReceiptIds']:
                prior=receipts.get(chain[-1]['upstreamReceiptIds'][0])
                if prior is None or prior in chain:reject('knowledge-stage-chain-mismatch')
                chain.append(prior)
            identities={r['worker']['observed']['sessionId'] for r in chain}
            if receipt['worker']['observed']['sessionId'] in identities:reject('knowledge-independence-mismatch')
            if any(r['task']!=receipt['task'] for r in chain):reject('knowledge-host-mismatch')
    worker_sessions=[r['worker']['observed']['sessionId'] for r in receipts.values()]
    task_sessions={r['task']['observed']['sessionId'] for r in receipts.values()}
    if len(worker_sessions)!=len(set(worker_sessions)) or set(worker_sessions)&task_sessions:reject('knowledge-independence-mismatch')
    return receipts
