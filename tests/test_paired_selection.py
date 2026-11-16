import unittest
from host.template_selector import PROFILES,library,relations,select_examples,source,normalized

class PairedSelectionTests(unittest.TestCase):
    def test_all_template_sources_exclude_self_and_preserve_pair_order(self):
        for profile in PROFILES:
            bank = {r['template_id']:r for r in library('reviewer',profile)}
            texts = {source(r) for role in ('generator','reviewer') for r in library(role,profile)}
            for raw in texts:
                g = select_examples('generator',profile,raw)
                reviewer = select_examples('reviewer',profile,raw)
                pairs, extras = reviewer[:len(g)], reviewer[len(g):]
                self.assertTrue(6<=len(g)<=8 and 2<=len(extras)<=4)
                self.assertEqual([bank[i]['pair_id'] for i in pairs],g)
                self.assertTrue(all(not bank[i].get('pair_id') for i in extras))
                used = [normalized(source(bank[i])) for i in reviewer]
                self.assertEqual(len(used),len(set(used)))
                self.assertNotIn(normalized(raw),used)

    def test_temporal_attachment_and_matched_evidence(self):
        a='Before you enter the kitchen, turn right. After you pass the stairs, turn left.'
        b='After you enter the kitchen, turn left. Before you pass the stairs, turn right.'
        self.assertIn(('before','event','enter'),relations(a))
        self.assertIn(('after','event','enter'),relations(b))
        self.assertNotEqual(relations(a),relations(b))
        from host.template_selector import rank_examples
        fixtures=[{'input':{'original_instruction':text},'teaching_notes':{},'provenance':{},'template_id':label}
                  for label,text in [('before',a.replace('kitchen','bedroom')),('after',b.replace('kitchen','bedroom'))]]
        for text,winner in [(a,'before'),(b,'after')]:
            self.assertEqual(rank_examples(fixtures,text,1)[0]['template_id'],winner)

    def test_full_library_and_explicit_base_count(self):
        for profile in PROFILES:
            for role in ('generator','reviewer'):
                self.assertEqual(len(select_examples(role,profile,'',mode='all')),len(library(role,profile)))
            self.assertEqual(len(select_examples('generator',profile,'Go.',count=3)),3)
            self.assertEqual(len(select_examples('reviewer',profile,'Go.',count=3)),5)
