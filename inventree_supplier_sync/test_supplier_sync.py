"""Basic unit tests for the plugin"""

from httmock import urlmatch, HTTMock, response

from django.test import TestCase

from plugin import InvenTreePlugin
from plugin.mixins import SettingsMixin
from part.models import Part, PartCategory

from .mouser import Mouser
from .supplier_sync import SupplierSyncPlugin


class TestSyncPlugin(TestCase, SettingsMixin, InvenTreePlugin):

    def test_reformat_mouser_price(self):

        self.assertEqual(Mouser.reformat_mouser_price(self, '1.456,34 €'), 1456.34)
        self.assertEqual(Mouser.reformat_mouser_price(self, '1,45645 €'), 1.45645)
        self.assertEqual(Mouser.reformat_mouser_price(self, '1,56 $'), 1.56)
        self.assertEqual(Mouser.reformat_mouser_price(self, ''), 0)
        self.assertEqual(Mouser.reformat_mouser_price(self, 'Mumpitz'), 0)

    def test_should_be_updated(self):
        cat_include = PartCategory.objects.create(name='cat_include')
        cat_ignore = PartCategory.objects.create(name='cat_ignore', metadata={"SupplierSyncPlugin": {"SyncIgnore": True}})
        part_sync1 = Part.objects.create(
            name='Part1',
            IPN='IPN1',
            category=cat_include,
            active=True,
            purchaseable=True,
            component=True,
            virtual=False)
        part_ignore_cat = Part.objects.create(
            name='Part2',
            IPN='IPN2',
            category=cat_ignore,
            active=True,
            purchaseable=True,
            component=True,
            virtual=False)
        part_ignore_inactive = Part.objects.create(
            name='Part3',
            IPN='IPN3',
            category=cat_include,
            active=False,
            purchaseable=True,
            component=True,
            virtual=False)
        part_ignore_not_pur = Part.objects.create(
            name='Part4',
            IPN='IPN4',
            category=cat_include,
            active=True,
            purchaseable=False,
            component=True,
            virtual=False)
        part_ignore_meta = Part.objects.create(
            name='Part5',
            IPN='IPN5',
            category=cat_include,
            active=True,
            purchaseable=True,
            component=True,
            metadata={"SupplierSyncPlugin": {"SyncIgnore": True}}, virtual=False)
        test_class = self
        test_class.NAME = 'SupplierSyncPlugin'
        self.assertEqual(SupplierSyncPlugin.should_be_updated(test_class, part_sync1), True, 'Sync part')
        self.assertEqual(SupplierSyncPlugin.should_be_updated(test_class, part_ignore_cat), False, 'Ignore part category')
        self.assertEqual(SupplierSyncPlugin.should_be_updated(test_class, part_ignore_inactive), False, 'Inactive part')
        self.assertEqual(SupplierSyncPlugin.should_be_updated(test_class, part_ignore_not_pur), False, 'Part not purchasable')
        self.assertEqual(SupplierSyncPlugin.should_be_updated(test_class, part_ignore_meta), False, 'Part ignored becasue of metadata')

# ------------------------------- test_get_mouser_partdata -------------------
# This ist the most interesting one. We test for several possible answers
# from Mouser

    def test_get_mouser_partdata(self):

        # No access key in settings. We test against the original Mouser API
        data = Mouser.get_mouser_partdata(self, 'namxxxe', 'none')
        self.assertEqual(data['error_status'], 'Required')

        # Wrong access key in settings. Create a key and test against Mouser API
        SettingsMixin.set_setting(self, key='MOUSERSEARCHKEY', value='blabla')
        data = Mouser.get_mouser_partdata(self, 'namxxxe', 'none')
        self.assertEqual(data['error_status'], 'InvalidAuthorization')

        # Test with corect data, one result returned. Because we do notr want to
        # distribute a valid key and need a stable response, we mock the Mouser
        # URL using the HTTMock library.  # Some unused entries have been trmoved
        # from the content.
        headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
        content = {
            'Errors': [],
            'SearchResults': {
                'NumberOfResult': 1,
                'Parts': [{
                    'Description': '40V, Low IQ, 3MHz, 2-Phase Synchronous Boost Controller',
                    'LeadTime': '0 Tage',
                    'LifecycleStatus': None,
                    'Manufacturer': 'Analog Devices',
                    'ManufacturerPartNumber': 'LTC7806IUFDM#WPBF',
                    'Min': '0',
                    'Mult': '0',
                    'MouserPartNumber': 'N/A',
                    'ProductAttributes': [],
                    'PriceBreaks': [],
                    'ProductDetailUrl': 'https://www.mouser.de/ProductDetail/Analog-Devices/LTC7806IUFDMWPBF',
                    'Reeling': False,
                    'ROHSStatus': '',
                    'SuggestedReplacement': '',
                    'AvailabilityInStock': None,
                    'AvailabilityOnOrder': [],
                    'InfoMessages': []}]}}

        @urlmatch(netloc=r'(.*\.)?api\.mouser\.com.*')
        def mouser_mock(url, request):
            return response(200, content, headers, None, 5, request)

        with HTTMock(mouser_mock):
            data = Mouser.get_mouser_partdata(self, 'LTC7806IUFDM#WPBF', 'none')
        self.assertEqual(data['error_status'], 'OK', 'Test one result')
        self.assertEqual(data['number_of_results'], 1)
        self.assertEqual(data['SKU'], 'N/A')
        self.assertEqual(data['MPN'], 'LTC7806IUFDM#WPBF')
        self.assertEqual(data['URL'], 'https://www.mouser.de/ProductDetail/Analog-Devices/LTC7806IUFDMWPBF')
        self.assertEqual(data['lifecycle_status'], None)
        self.assertEqual(data['pack_quantity'], '0')
        self.assertEqual(data['description'], '40V, Low IQ, 3MHz, 2-Phase Synchronous Boost Controller')
        self.assertEqual(data['package'], '')
        self.assertEqual(data['price_breaks'], [])
