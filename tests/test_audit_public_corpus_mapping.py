"""Synthetic metadata-only regression coverage for the candidate mapping audit."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import audit_public_corpus_mapping as a

class CandidateMappingAuditTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.base=Path(self.tmp.name);self.root=self.base/'candidate';self.root.mkdir();(self.root/'items').mkdir()
  self.source=self.base/'source.mARkdown';self.source.write_text('### $$ 1 Synthetic One\n~~body one\n### | Synthetic heading\n# structural continuation\n### $$ 2 Synthetic Two\n~~body two\n',encoding='utf-8')
  self.authority=a.sha(self.source.read_bytes());self.ids={f'isabah-entry-{n:08d}' for n in [10759,10760]};self.exact=a.legacy_exact_domains(self.source)
  inventory={'authority':{'artifactSha256':self.authority},'entries':[{'id':f'synthetic-unit-{n}','ordinal':n,'printedEntryNumber':n,'rawSha256':a.sha(str(n).encode())} for n in [1,2]],'structuralSegments':[{'id':'synthetic-heading'}]};inventory['inventorySha256']=a.digest(inventory);self.inventory=self.base/'inventory.json';self.inventory.write_bytes(a.canonical(inventory));self.inventory_pin=a.sha(self.inventory.read_bytes())
  rows=[]
  for n,legacy in enumerate(sorted(self.ids),1):
   item={'id':legacy,'sourceEntryNumber':n,'remediation':{'legacyAllocationNumber':int(legacy.rsplit('-',1)[1])},'source':{'sourceExactTextSha256':self.exact[n][0],'sourceTextSha256':a.sha(b'Synthetic title Synthetic body'),'license':{'spdx':'CC-BY-NC-SA-4.0'}},'title':{'ar':'Synthetic title'},'segments':[{'arabic':'Synthetic body','english':'Synthetic English'}],'provenance':{'sourceArtifactSha256':self.authority,'sourceExactTextSha256':self.exact[n][0]},'machineAssessment':'passed','humanReview':'unreviewed','publicEligibility':'eligible','translationState':'translated','unresolved':[],'headingsBefore':[],'names':[]}
   self.write('items/'+legacy+'.json',item);rows.append({k:item[k] for k in ['id','sourceEntryNumber','machineAssessment','humanReview','publicEligibility','translationState']}|{'unresolvedCount':0})
  self.write('index.json',{'corpusId':'synthetic-corpus','items':rows});self.write('summary.json',{'corpus':{'id':'synthetic-corpus'}});self.write('quarantine.json',{'records':[]});self.write('exclusions.json',{'records':[]});self.rebind()
 def write(self,name,value):(self.root/name).write_bytes(a.canonical(value))
 def read(self,name):return json.loads((self.root/name).read_bytes())
 def rebind(self):
  files=[{'path':p.relative_to(self.root).as_posix(),'sha256':a.sha(p.read_bytes()),'bytes':len(p.read_bytes())} for p in sorted(self.root.rglob('*.json')) if p.name!='manifest.json'];self.write('manifest.json',{'corpusId':'synthetic-corpus','sourceArtifactSha256':self.authority,'objectCount':len(files),'files':files});self.manifest_pin=a.sha((self.root/'manifest.json').read_bytes())
 def run_audit(self):return a.audit(self.root,self.source,self.inventory,self.manifest_pin,self.inventory_pin,self.ids)
 def test_exact_historical_domain_excludes_heading_line_but_retains_its_body(self):
  expected='### $$ 1 Synthetic One\n~~body one\n# structural continuation';self.assertEqual(self.exact[1],[a.sha(expected.encode())]);r=self.run_audit();self.assertEqual(r['legacyRecordCount'],2);self.assertEqual(r['expectedStructuralSegmentCount'],1);self.assertEqual(r['candidateHeadingsBeforeCount'],0);self.assertNotIn('Synthetic body',a.canonical(r).decode())
 def test_source_and_manifest_byte_mismatch(self):
  self.source.write_bytes(self.source.read_bytes()+b'changed')
  with self.assertRaisesRegex(ValueError,'source-pin-mismatch'):self.run_audit()
  self.manifest_pin='0'*64
  with self.assertRaisesRegex(ValueError,'manifest-pin-mismatch'):self.run_audit()
 def test_inventory_external_pin_and_embedded_digest_are_independent(self):
  self.inventory.write_bytes(self.inventory.read_bytes()+b' ')
  with self.assertRaisesRegex(ValueError,'inventory-pin-mismatch'):self.run_audit()
  data=json.loads(self.inventory.read_bytes());data['inventorySha256']='0'*64;self.inventory.write_bytes(a.canonical(data));self.inventory_pin=a.sha(self.inventory.read_bytes())
  with self.assertRaisesRegex(ValueError,'inventory-content-mismatch'):self.run_audit()
 def test_missing_duplicate_and_swapped_mapping_reject(self):
  original=self.read('index.json');changed=json.loads(json.dumps(original));changed['items'].pop();self.write('index.json',changed);self.rebind()
  with self.assertRaisesRegex(ValueError,'legacy-id-coverage-mismatch'):self.run_audit()
  self.write('index.json',{'corpusId':'synthetic-corpus','items':[original['items'][0],original['items'][0]]});self.rebind()
  with self.assertRaisesRegex(ValueError,'legacy-id-coverage-mismatch'):self.run_audit()
  for row in original['items']:
   row['sourceEntryNumber']=3-row['sourceEntryNumber'];name='items/'+row['id']+'.json';item=self.read(name);item['sourceEntryNumber']=row['sourceEntryNumber'];self.write(name,item)
  self.write('index.json',original);self.rebind()
  with self.assertRaisesRegex(ValueError,'exact-source-domain-mismatch'):self.run_audit()
 def test_member_bytes_and_unsafe_manifest_members_reject(self):
  (self.root/'index.json').write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'manifest-member-mismatch'):self.run_audit()
  manifest=self.read('manifest.json');manifest['files'][0]['path']='../escape';self.write('manifest.json',manifest);self.manifest_pin=a.sha((self.root/'manifest.json').read_bytes())
  with self.assertRaisesRegex(ValueError,'unsafe-manifest-member'):self.run_audit()

if __name__=='__main__':unittest.main()
