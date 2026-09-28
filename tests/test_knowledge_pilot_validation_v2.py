"""Private v2 validation remains separate from semantic execution approval."""
import copy
import unittest
from test_knowledge_pilot_trial import fixture,partial_output
from knowledge_export_v2_draft3_support import capabilities
import knowledge_pilot_validation_v2 as v2
import knowledge_pilot_trial as legacy
from knowledge_export import read,digest,Rejection


class KnowledgePilotValidationV2Tests(unittest.TestCase):
    def fixture(self):
        packet,metadata,decision=fixture()
        stage=legacy.prepare_stage(legacy.STAGES[0],decision,digest(decision),packet,metadata,'0'*40)
        stage['profile']=capabilities()[2];stage['profileSha256']=digest(stage['profile'])
        stage['outputSchema']=read(v2.SCHEMA);stage['outputSchemaSha256']=digest(stage['outputSchema'])
        output=partial_output(stage,packet);output['schema']='al-isabah.knowledge-pilot-stage-output.v2'
        return packet,stage,output
    def test_v2_partial_validates_without_semantic_approval(self):
        packet,stage,output=self.fixture();self.assertEqual(v2.validate_output(output,stage,packet),output)
        self.assertFalse(stage['profile']['realExecutionEnabled']);self.assertFalse(stage['profile']['realAdmissionEnabled'])
    def test_typed_event_quantity_and_source_notice_rules_apply_privately(self):
        packet,stage,output=self.fixture();rid=packet['records'][0]['id'];sid=packet['units'][0]['spans'][0]['id']
        u=lambda name:'urn:al-isabah:synthetic:'+name
        person=u('entity:author');report=u('report:attestation');event=u('event:oath')
        output['entities']=[{'id':person,'logicalEntityId':u('logical:author'),'kind':'person','sourceRecordVersionIds':[rid],'mentionIds':[],'nameIds':[],'identityAssessmentIds':[],'ambiguityGroupIds':[]}]
        output['events']=[{'id':event,'typeId':u('event-type:oath'),'sourceRecordVersionIds':[rid],'reportIds':[report],'participantRoles':[{'roleId':stage['profile']['participantRoles'][0],'entityId':person}],'placeIds':[],'timeIds':[],'ambiguityGroupIds':[]}]
        output['values']=[{'id':u('value:pledge'),'kind':'count','unit':'camels','amountNumerator':7,'amountDenominator':2,'approximate':True,'sourceRecordVersionIds':[rid]}]
        output['reports']=[{'id':report,'sourceRecordVersionIds':[rid],'sourceSpanIds':[sid],'attributorEntityIds':[person],'transmission':[],'claimIds':[],'criticalAssessmentIds':[],'ambiguityGroupIds':[]}]
        output['attributions']=[{'id':u('attribution:author'),'kind':'source_author','entityIds':[person],'artifactIds':['urn:al-isabah:trial:artifact:authority'],'required':True}]
        output['useRestrictions']=[{'id':u('restriction:qualified'),'tier':'qualified_context','attributionRequired':True}]
        for name,subject,obj,polarity in [('pledged-quantity',{'kind':'events','id':event},{'kind':'values','id':u('value:pledge')},'positive'),('companion-status-evidence-in',{'kind':'entities','id':person},{'kind':'sourceRecords','id':rid},'absence_of_evidence')]:
            cid=u('claim:'+name);qid=u('qualification:'+name)
            output['claims'].append({'id':cid,'subjectRef':subject,'predicateId':u('predicate:'+name),'objectRef':obj,'sourceRecordVersionIds':[rid],'sourceSpanIds':[sid],'reportIds':[report],'assertionClass':'source_attested','polarity':polarity,'modality':'asserted','qualificationIds':[qid],'assessmentIds':[],'attributionIds':[u('attribution:author')],'ambiguityGroupIds':[],'useRestrictionIds':[u('restriction:qualified')]})
            output['qualifications'].append({'id':qid,'targets':[{'kind':'claims','id':cid}],'evaluatorEntityIds':[person],'criticalStatus':'qualified','evidentiaryStrength':'source_supported','transmissionStrength':'unassessed','sourceRecordVersionIds':[rid]})
            output['reports'][0]['claimIds'].append(cid)
        output['spanDispositions'][0].update(status='represented',reasonCode='mapped',claimIds=[c['id'] for c in output['claims']],reportIds=[report])
        v2.validate_output(output,stage,packet)
        changed=copy.deepcopy(output);changed['claims'][1]['polarity']='negative';changed['useRestrictions'][0]['tier']='factual_spine'
        with self.assertRaisesRegex(Rejection,'predicate-epistemic-mismatch'):v2.validate_output(changed,stage,packet)
        changed=copy.deepcopy(output);changed['attributions'][0]['kind']='work'
        with self.assertRaisesRegex(Rejection,'source-author-attribution-mismatch'):v2.validate_output(changed,stage,packet)

    def test_frozen_v1_does_not_accept_v2_or_relabel_old_output(self):
        packet,stage,output=self.fixture()
        with self.assertRaises(Rejection):legacy.validate_output(output,stage,packet)
        output['schema']='al-isabah.knowledge-pilot-stage-output.v1'
        with self.assertRaises(Rejection):v2.validate_output(output,stage,packet)
    def test_embedded_schema_profile_pins_cannot_drift(self):
        for key in ('profileSha256','outputSchemaSha256'):
            packet,stage,output=self.fixture();stage[key]='f'*64;output['stageInputSha256']=digest(stage)
            with self.assertRaisesRegex(Rejection,'trial-schema-profile-mismatch'):v2.validate_output(output,stage,packet)
    def test_concerns_and_incomplete_coverage_do_not_become_completion(self):
        packet,stage,output=self.fixture();output['status']='complete'
        with self.assertRaisesRegex(Rejection,'trial-false-completion'):v2.validate_output(output,stage,packet)


if __name__=='__main__':unittest.main()
