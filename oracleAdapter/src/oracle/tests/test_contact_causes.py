import unittest
from oracle.verification.contact_causes import contact_category

class ContactCauses(unittest.TestCase):
    def test_sweep_only_is_not_actual_endpoint_penetration(self):
        self.assertEqual(contact_category(None, None, {'triangle':1}), 'linear_sweep_only_contact')
        self.assertEqual(contact_category(None, {'triangle':1}, {'triangle':1}), 'actual_after_state_contact')

    def test_missing_reproduced_contact_remains_disagreement(self):
        self.assertEqual(contact_category(None, None, None), 'contact_not_reproduced')
