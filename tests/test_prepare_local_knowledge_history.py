"""Read-only assembly of authored synthetic execution files."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import knowledge_pilot_trial as old
import prepare_local_knowledge_history as prepare
from knowledge_export import read,digest,Rejection


class LocalHistoryAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history=read(old.ROOT/'tests/fixtures/knowledge-export-v2-local1/initial/receipts.json')['history']
    def files(self,root):
        directory=root/'captured'
        for name,item in zip(old.STAGES,self.history['stages']):
            for key,value in item.items():old.write_new(directory/(name+'.'+key+'.json'),value)
        old.write_new(directory/'validation-report.json',self.history['report'])
        old.write_new(root/'decision.json',self.history['decision']);old.write_new(root/'partition.json',self.history['partition'])
        return directory
    def test_assembly_preserves_exact_history_and_requires_independent_pins(self):
        with tempfile.TemporaryDirectory(dir=old.ROOT/'.runtime') as temp:
            root=Path(temp);directory=self.files(root)
            args=(directory,root/'decision.json',root/'partition.json',digest(self.history['decision']),digest(self.history['report']))
            self.assertEqual(prepare.assemble(*args),self.history)
            with self.assertRaisesRegex(Rejection,'local-history-external-pin-mismatch'):prepare.assemble(*args[:-1],'f'*64)
    def test_cli_writes_only_new_separate_history_file(self):
        with tempfile.TemporaryDirectory(dir=old.ROOT/'.runtime') as temp:
            root=Path(temp);directory=self.files(root);out=root/'new-history.json'
            args=['prepare','--directory',str(directory),'--decision',str(root/'decision.json'),'--partition',str(root/'partition.json'),
                  '--decision-sha256',digest(self.history['decision']),'--report-sha256',digest(self.history['report']),'--output',str(out)]
            with mock.patch.object(old,'require_runtime_directory'),mock.patch('sys.argv',args):self.assertEqual(prepare.main(),0)
            self.assertEqual(read(out),self.history)
            args[-1]=str(directory/'forbidden.json')
            with mock.patch.object(old,'require_runtime_directory'),mock.patch('sys.argv',args):self.assertEqual(prepare.main(),1)
            self.assertFalse((directory/'forbidden.json').exists())


if __name__=='__main__':unittest.main()
