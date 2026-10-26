"""Isolated unit tests for MINJAZ digital-services route validation (no database needed)."""
import unittest
from minjaz_digital_services import dispatch

class NoDatabase:
    def __call__(self):
        raise AssertionError('database should not be accessed for invalid requests')

class DigitalServicesValidationTests(unittest.TestCase):
    def test_anonymous_cannot_list_orders(self):
        self.assertEqual(dispatch('GET','/api/digital-services/orders',{},None,None,NoDatabase())[0],401)
    def test_anonymous_cannot_create_orders(self):
        self.assertEqual(dispatch('POST','/api/digital-services/orders',{}, {},None,NoDatabase())[0],401)
    def test_anonymous_cannot_read_order(self):
        self.assertEqual(dispatch('GET','/api/digital-services/orders/1',{},None,None,NoDatabase())[0],401)
    def test_invalid_category(self):
        self.assertEqual(dispatch('GET','/api/digital-services/catalog',{'category':['invalid']},None,None,NoDatabase())[0],400)
    def test_invalid_order(self):
        self.assertEqual(dispatch('POST','/api/digital-services/orders',{}, {'package_id':0,'requirements':'short'}, {'id':5},NoDatabase())[0],400)
    def test_bool_package_id_rejected(self):
        self.assertEqual(dispatch('POST','/api/digital-services/orders',{}, {'package_id':True,'requirements':'requirements long enough'}, {'id':5},NoDatabase())[0],400)
    def test_invalid_order_id(self):
        self.assertEqual(dispatch('GET','/api/digital-services/orders/abc',{},None,{'id':5},NoDatabase())[0],404)
    def test_unsupported_method(self):
        self.assertEqual(dispatch('DELETE','/api/digital-services/orders',{},None,{'id':5},NoDatabase())[0],405)

if __name__=='__main__': unittest.main()
