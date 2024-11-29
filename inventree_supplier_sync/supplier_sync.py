# Plugin that syncronises parts with the Mouser database.
from django.http import HttpResponse
from django.urls import re_path

import logging

from plugin import InvenTreePlugin
from plugin.mixins import ScheduleMixin, SettingsMixin, AppMixin, PanelMixin, UrlsMixin
from part.models import Part
from company.models import Company, SupplierPriceBreak, ManufacturerPart, SupplierPart
from part.views import PartIndex

from .version import PLUGIN_VERSION
from .mouser import Mouser
from .meta_access import MetaAccess
from .models import SupplierPartChange

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
fh = logging.FileHandler('sync.log')
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)


# ---------------------------- SupplierSyncPlugin -----------------------------
class SupplierSyncPlugin(AppMixin, ScheduleMixin, SettingsMixin, PanelMixin, InvenTreePlugin, UrlsMixin):

    NAME = "SupplierSyncPlugin"
    SLUG = "suppliersync"
    TITLE = "Sync parts with a supplier"
    AUTHOR = "Michael"
    PUBLISH_DATE = "2023-02-16T20:55:08.914461+00:00"
    VERSION = PLUGIN_VERSION
    DESCRIPTION = 'Syncronize parts with Supplier SKU and price breaks'
    MIN_VERSION = '0.11.0'

    SCHEDULED_TASKS = {
        'member': {
            'func': 'update_part',
            'schedule': 'I',
            'minutes': 1,
        }
    }

    SETTINGS = {
        'MOUSER_PK': {
            'name': 'Mouser Supplier ID',
            'description': 'Primary key of the Mouser supplier',
            'model': 'company.company',
        },
        'MOUSERSEARCHKEY': {
            'name': 'Supplier API Key new',
            'description': 'Place here your key for the suppliers API',
        },
        'ENABLE_SYNC': {
            'name': 'Enable the plugin',
            'description': 'Allow the regular synchronisation',
            'default': True,
            'validator': bool,
        },
        'PROXY_CON': {
            'name': 'Proxy CON',
            'description': 'Connection protocol to proxy server if needed e.g. https',
        },
        'PROXY_URL': {
            'name': 'Proxy URL',
            'description': 'URL to proxy server if needed e.g. http://user:password@ipaddress:port',
        },
        'AKTPK': {
            'name': 'The actual component',
            'description': 'The next component to be updated',
        },
        'FAILCOUNT': {
            'name': 'Failure count',
            'description': 'Counts how many accesses to the supplier failed',
        },
    }

    # ------------------------- get_settings_content ---------------------------
    # Some nice info for the user that will be shown in the plugin's settings
    # page

    def get_settings_content(self, request):
        return """
        <p>Setup:</p>
        <ol>
        <li>Create a key for the Mouser API</li>
        <li>RTFM</li>
        <li>Enable the plugin</li>
        <li>Put key into settings</li>
        <li>Put link to the API into settings</li>
        <li>Enjoy</li>
        </ol>
        """

    # silence the requests messages
    logging.getLogger("requests").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    def get_custom_panels(self, view, request):
        panels = []
        self.sync_objects = SupplierPartChange.objects.order_by('pk')
        if isinstance(view, PartIndex):
            panels.append({'title': 'Sync results',
                           'icon': 'fa-user',
                           'content_template': 'supplier_sync/sync.html'})
        return panels

    def setup_urls(self):
        self.set_setting('FAILCOUNT', str(0))
        return [
            re_path(r'deleteentry/(?P<key>\d+)/', self.delete_entry, name='delete-entry'),
            re_path(r'addpart/(?P<key>\d+)/', self.add_supplierpart, name='add-part'),
            re_path(r'ignorepart/(?P<key>\d+)/', self.ignore_part, name='ignore-part'),
        ]

    # ---------------------------- update_part ------------------------------------
    # Main function that is called by the scheduler
    # -----------------------------------------------------------------------------
    def update_part(self, *args, **kwargs):

        if not self.get_setting('ENABLE_SYNC'):
            return
        company = Company.objects.filter(pk=int(self.get_setting('MOUSER_PK')))[0]
        try:
            update_pk = int(self.get_setting('AKTPK', cache=False))
        except Exception:
            update_pk = 1
        logger.info('Running update on pk %i', update_pk)

        # First check if the pk exists. It might have been deleted between the executions
        # ore someone might have changed the AKTPK manually. We go back to start in that case.
        all_parts = Part.objects.all()
        all_parts_pk = []
        for p in all_parts:
            all_parts_pk.append(p.pk)
        if update_pk not in all_parts_pk:
            update_pk = all_parts[0].pk

        part_to_update = Part.objects.get(pk=update_pk)

        # In case the part shall not be updated go to next one to not loose the slot.
        while not self.should_be_updated(part_to_update):
            update_pk = self.get_next_part(all_parts, part_to_update).pk
            part_to_update = Part.objects.get(pk=update_pk)
        logger.info('Updating part %s %s', part_to_update.IPN, part_to_update.name)
        supplier_parts = self.get_existing_supplierparts(part_to_update.supplier_parts, company.name)
        if len(supplier_parts) > 0:
            logger.info('Supplier part found. Update')
            for sp in supplier_parts:
                if sp.SKU != 'N/A':
                    success = self.update_supplier_parts(part_to_update, sp, company.name)
                else:
                    logger.info('Supplier part has no valid SKU. Try to find new ones')
                    success = self.log_new_supplierpart(part_to_update)
        else:
            logger.info('No supplier part found. Try to find new ones')
            success = self.log_new_supplierpart(part_to_update)

        # In case the update was OK we go to the next one. Otherwise we try it again and again...
        fail_counter = int(self.get_setting('FAILCOUNT', cache=False))
        if success:
            update_pk = self.get_next_part(all_parts, part_to_update).pk
            self.set_setting('AKTPK', str(update_pk))
            fail_counter = 0
            self.set_setting('FAILCOUNT', str(fail_counter))
        else:
            fail_counter = fail_counter + 1
            self.set_setting('FAILCOUNT', str(fail_counter))
        if fail_counter > 10:
            self.set_setting('ENABLE_SYNC', False)
            return ('Error')
        else:
            return ('OK')

# ------------------------------ get_next_part --------------------------------
# Get the next part to be updated. Returns part object.

    def get_next_part(self, all_parts, part_to_find):

        getit = False
        for m in all_parts:
            if getit:
                return m
            if part_to_find == m:
                getit = True
        if getit:
            # This would happen when the last
            # item made getit True
            return all_parts[0]
        return False

# ----------------------- get_existing_supplier_parts -------------------------
# Returns all existing supplier parts where the supplier name is supplier_name

    def get_existing_supplierparts(self, sp, supplier_name):
        supplier_parts = []

        for ssp in sp.all():
            if ssp.supplier.name == supplier_name:
                supplier_parts.append(ssp)
        return supplier_parts

# --------------------------- should_be_updated -------------------------------
# Returns false if the part is excluded from update for various reasons. See code.
# A complete category can be excluded by putting json:
# {"supplier_sync": {"exclude": "True"}}
# into the category meta data field.

    def should_be_updated(self, p):
        try:
            cat_exclude = p.category.get_metadata('supplier_sync')['exclude'] == 'True'
        except Exception:
            cat_exclude = False
        if cat_exclude:
            logger.info('Skipping part %s. Category is excluded', p.IPN)
            return False
        if not p.purchaseable:
            logger.info('Skipping part %s. Part is not purchasable', p.IPN)
            return False
        if not p.active:
            logger.info('Skipping part %s. Part is not active', p.IPN)
            return False
        ignore = MetaAccess.get_value(self, p, self.NAME, 'SyncIgnore')
        if ignore:
            logger.info('Skipping part %s. Part is set to ignore', p.IPN)
            return False
        return True

# --------------------------- update_supplier_parts ---------------------------
# Here we use an 'exact' search because we have already the exact SKU in the
# database. So there should be exactly one result. In this case we update the
# price breaks by deleting the existing ones and creating new ones.
# In case SKU does not exist the supplier might have canceled the part and we
# log a warning.
# In case we get several hits something might have gone wrong with the search.
# We log a warning. These cases need to be cleared manually.

    def update_supplier_parts(self, part_to_update, sp, supplier_name):
        logger.info('Updating Mouser part for %s', sp.SKU)
        data = Mouser.get_mouser_partdata(self, sp.SKU, 'exact')
        if data['number_of_results'] == -1:
            logger.info('SKU search on %s reported error. ', supplier_name)
            return False
        if data['number_of_results'] == 0:
            logger.info('SKU search on %s reported 0 parts. ', supplier_name)
            SupplierPartChange.objects.create(part=part_to_update, change_type="deleted", comment='Part has been deleted from suppliers catalog')
            return True
        if data['number_of_results'] == 1:
            logger.info('%s reported 1 part. Updating price breaks and lifecycle', supplier_name)
            life_cycle_status = data['lifecycle_status']
            if sp.note != life_cycle_status:
                SupplierPartChange.objects.create(part=part_to_update, change_type="Life cycle", old_value=sp.note, new_value=life_cycle_status)
                sp.note = life_cycle_status
                sp.save()
                logger.info('New lifecycle saved to notes')
            spb = SupplierPriceBreak.objects.filter(part=sp.pk).all()
            for pb in spb:
                pb.delete()
            for pb in data['price_breaks']:
                SupplierPriceBreak.objects.create(part=sp, quantity=pb['Quantity'], price=pb['Price'])
        elif data['number_of_results'] > 1:
            logger.info('%s reported %i parts. No update', supplier_name, data['number_of_results'])
        return True

# ----------------------------- log_new_supplierpart --------------------------

    def log_new_supplierpart(self, p):
        logger.info('Seach Mouser for %s', p.IPN)
        data = Mouser.get_mouser_partdata(self, p.name, 'none')
        number_of_results = data['number_of_results']
        if data['error_status'] == 'ConnectionError':
            raise ConnectionError('Error connecting to Supplier API', data)
            return False
        if data['error_status'] == 'InvalidAuthorization':
            logger.info('Invalid Authorizaion')
            return False
        if data['error_status'] == 'TooManyRequests':
            logger.info('Too many requests')
            return False
        if data['error_status'] == 'InvalidCharacters':
            SupplierPartChange.objects.create(part=p,
                                              change_type="error",
                                              old_value='',
                                              new_value='',
                                              comment='Illegal character in MPN')
            logger.info('Illegal character reported')
            return True
        if number_of_results == 0:
            logger.info('Mouser reported 0 parts, nothing to do!')
        else:
            logger.info(f'Mouser reported {number_of_results} parts')
            if number_of_results > 1:
                SupplierPartChange.objects.create(part=p,
                                                  change_type="add",
                                                  comment=f'{number_of_results} supplier parts reported',
                                                  link=f'https://www.mouser.de/c/?q={p.name}',
                                                  number_of_parts=number_of_results,
                                                  new_value=data['SKU'] + ' ...')
            else:
                if data['SKU'] != 'N/A':
                    SupplierPartChange.objects.create(part=p,
                                                      change_type="add",
                                                      comment=f'{number_of_results} supplier part reported',
                                                      link=data['URL'],
                                                      number_of_parts=number_of_results,
                                                      new_value=data['SKU'])
        return True

# ------------------------------------- delete_entry -------------------------
    def delete_entry(self, request, key):

        entry_to_delete = SupplierPartChange.objects.filter(pk=key)
        entry_to_delete.delete()
        return HttpResponse('OK')

# ---------------------------- add_supplierpart -------------------------------
    def add_supplierpart(self, request, key):

        sync_object = SupplierPartChange.objects.filter(pk=key)[0]
        part = sync_object.part
        supplier = Company.objects.filter(pk=int(self.get_setting('MOUSER_PK')))[0]

        manufacturer_part = ManufacturerPart.objects.filter(part=part.pk)
        if len(manufacturer_part) == 0:
            logger.error('Part has no manufactuer part')
            return HttpResponse('Error')

        part_data = Mouser.get_mouser_partdata(self, sync_object.new_value, 'exact')

        if part_data['number_of_results'] == -1:
            logger.error('Connection error')
            return HttpResponse('Error')
        if part_data['number_of_results'] == 0:
            logger.error('No parts returned')
            return HttpResponse('Error')

        supplier_parts = SupplierPart.objects.filter(part=part.pk)
        for sp in supplier_parts:
            if sp.SKU.strip() == part_data['SKU'].strip():
                logger.error('Part has already a supplier part')
                return HttpResponse('Error')

        sp = SupplierPart.objects.create(part=part,
                                         supplier=supplier,
                                         manufacturer_part=manufacturer_part[0],
                                         SKU=part_data['SKU'],
                                         link=part_data['URL'],
                                         note=part_data['lifecycle_status'],
                                         packaging=part_data['package'],
                                         pack_quantity=part_data['pack_quantity'],
                                         description=part_data['description'],
                                         )
        for pb in part_data['price_breaks']:
            SupplierPriceBreak.objects.create(part=sp, quantity=pb['Quantity'], price=pb['Price'], price_currency=pb['Currency'])
        sync_object.delete()
        return HttpResponse('OK')

# ------------------------------------- ignore_part -------------------------
    def ignore_part(self, request, key):

        sync_object = SupplierPartChange.objects.get(pk=key)
        part = sync_object.part
        MetaAccess.set_value(self, part, self.NAME, 'SyncIgnore', True)
        return HttpResponse('OK')
