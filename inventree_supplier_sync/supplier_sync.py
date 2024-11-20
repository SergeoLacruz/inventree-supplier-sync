# Plugin that syncronises parts with the Mouser database.

import requests
import json
import logging
import re

from plugin import InvenTreePlugin
from plugin.mixins import ScheduleMixin, SettingsMixin, AppMixin, PanelMixin
from part.models import Part
from part.models import SupplierPart
from company.models import Company
from company.models import SupplierPriceBreak
from inventree_supplier_sync.version import PLUGIN_VERSION
from inventree_supplier_panel.mouser import Mouser
from .models import SupplierPartChange
from part.views import PartIndex


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
fh = logging.FileHandler('sync.log')
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

#---------------------------- MouserSyncPlugin --------------------------------------------------
class SupplierSyncPlugin(AppMixin, ScheduleMixin, SettingsMixin, PanelMixin, InvenTreePlugin):

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
            'func': 'UpdatePart',
            'schedule': 'I',
            'minutes': 3,
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
            'description': 'The next comopnent to be updated',
        },
    }

    #------------------------- get_settings_content -------------------------------------
    # Some nice info for the user that will be shown in the plugin's settings page

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
        """

    # silence the requests messages
    logging.getLogger("requests").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


    def get_custom_panels(self, view, request):
        panels = []
        self.sync_objects = SupplierPartChange.objects.order_by('pk')
        if isinstance(view, PartIndex):
            panels.append({
                        'title': 'Sync results',
                        'icon': 'fa-user',
                        'content_template': 'supplier_sync/mouser.html',
                    })
        return panels

#---------------------------- UpdatePart --------------------------------------------------
# Main function that is called by the scheduler
#------------------------------------------------------------------------------------------
    def UpdatePart(self, *args, **kwargs):

#       bla = SupplierPartChange.objects.all()
#        for qay in bla:
#            print('PK:'. qay.pk)
#        sel = SupplierPartChange.objects.filter(pk=3)[0]
#        print(sel.old_value)
#        sel.old_value = 'Hallo'
#        sel.save()

        company = Company.objects.filter(pk=int(self.get_setting('MOUSER_PK')))[0]
        try:
            update_pk = int(self.get_setting('AKTPK', cache=False))
        except Exception:
            update_pk = 1
        logger.info('Running update on pk %i',update_pk)

        # First check if the pk exists. It might have been deleted between the executions
        # ore someone might have changed the AKTPK manually. We go back to start in that case.
        AllParts=Part.objects.all()
        AllPartsPK=[]
        for p in AllParts:
            AllPartsPK.append(p.pk)
        if update_pk not in AllPartsPK:
            update_pk=AllParts[0].pk

        part_to_update=Part.objects.get(pk=update_pk)

        # In case the part shall not be updated go to next one to not loose the slot.
        while not self.ShoudBeUpdated(part_to_update):
            update_pk=self.get_next_part(AllParts, part_to_update).pk
            part_to_update=Part.objects.get(pk=update_pk)
        logger.info('Updating part %s %s', part_to_update.IPN, part_to_update.name)
        SupplierParts=self.GetExistingSupplierParts(part_to_update.supplier_parts, company.name)
        if len(SupplierParts)>0:
            logger.info('Supplier part found. Update')
            for sp in SupplierParts:
                if sp.SKU != 'N/A':
                    Success=self.UpdateSupplierParts(part_to_update, sp, company.name)
                else:
                    logger.info('Supplier part has no valid SKU. Skip')
                    Success=True
        else:
            logger.info('No supplier part found. Try to find new ones')
            Success=self.log_new_supplierpart(part_to_update)

        # In case the update was OK we go to the next one. Otherwise we try it again and again...
        if Success:
            update_pk=self.get_next_part(AllParts,part_to_update).pk
            self.set_setting('AKTPK',str(update_pk))

#------------------------------ get_next_part -----------------------------------------------
# Get the next part to be updated. Returns part object.

    def get_next_part(self, all_parts, part_to_find):
        getit=False
        for m in all_parts:
            if getit:
                return m
            if part_to_find == m:
                getit=True
        if getit:
            # This would happen when the last
            # item made getit True
            return all_parts[0]
        return False

#----------------------- GetExistingSupplierParts -----------------------------------------
# Returns all existing supplier parts where the supplier name is SupplierName

    def GetExistingSupplierParts(self,sp, SupplierName):
        SupplierParts=[]

        for ssp in sp.all():
            if ssp.supplier.name == SupplierName:
                SupplierParts.append(ssp)
        return SupplierParts

#------------------------------- ShoudBeUpdated -----------------------------------------
# Returns false if the part is excluded from update for various reasons. See code.
# A complete category can be excluded by putting json:
# {"supplier_sync": {"exclude": "True"}}
# into the category meta data field.

    def ShoudBeUpdated(self,p):
        try:
            CatExclude=SyncMetadata=p.category.get_metadata('supplier_sync')['exclude']=='True'
        except:
            CatExclude=False

        if CatExclude:
            logger.info('Skipping part %s. Category is excluded',p.IPN)
            return False
        if not p.purchaseable:
            logger.info('Skipping part %s. Part is not purchasable',p.IPN)
            return False
        if not p.active:
            logger.info('Skipping part %s. Part is not active',p.IPN)
            return False
        return True

#----------------------------- UpdateSupplierPart ----------------------------------------
# Here we use an 'exact' search because we have already the exact SKU in the database.
# So there should be exactly one result. In this case we update the price breaks by
# deleting the existing ones and creating new ones.
# In case SKU does not exist the supplier might have canceled the part and we log a warning.
# In case we get several hits something might have gone wrong with the search. We log a warning.
# These cases need to be cleared manually.

    def UpdateSupplierParts(self, part_to_update, sp,SupplierName):
        logger.info('Updating Mouser part for %s', sp.SKU)
        Results, Data=Mouser.get_mouser_partdata(self, sp.SKU, 'exact')
        if Results == -1:
            logger.info('SKU search on %s reported error. ', SupplierName)
            return False
#        if Results == -2:
#            SupplierPartChange.objects.create(part=part_to_update, change_type="error", old_value='', new_value='', comment='Illegal character in MPN')
#            logger.info('illegal character reported')
#            return True
        if Results == 0:
            logger.info('SKU search on %s reported 0 parts. ', SupplierName)
            SupplierPartChange.objects.create(part=part_to_update, change_type="deleted", comment='Part has been deleted from suppliers catalog')
            return True
        if Results == 1:
            logger.info('%s reported 1 part. Updating price breaks and lifecycle', SupplierName)
            life_cycle_status = Data['lifecycle_status']
            logger.info('Lifecycle %s',life_cycle_status)
            if sp.note != life_cycle_status:
                SupplierPartChange.objects.create(part=part_to_update, change_type="Life cycle", old_value=sp.note, new_value=life_cycle_status)
                sp.note=life_cycle_status
                sp.save()
                logger.info('Lifecycle saved to notes')
            spb=SupplierPriceBreak.objects.filter(part=sp.pk).all()
            for pb in spb:
                pb.delete()
            for pb in Data['price_breaks']:
                SupplierPriceBreak.objects.create(part=sp, quantity=pb['Quantity'], price=pb['Price'])
        elif Results>1:
            logger.info('%s reported %i parts. No update', SupplierName, Results)
        return True

#----------------------------- log_new_supplierpart ----------------------------------------

    def log_new_supplierpart(self,p):
        logger.info('Seach Mouser for %s',p.IPN)
        number_of_results, data=Mouser.get_mouser_partdata(self, p.name,'none')
        if number_of_results == -1:
            raise ConnectionError('Error connecting to Supplier API',data)
            return False
        if number_of_results == -2:
            SupplierPartChange.objects.create(part=p, change_type="error", old_value='', new_value='', comment='Illegal character in MPN')
            logger.info('Illegal character reported')
            return True
        if  number_of_results == 0:
            logger.info('Mouser reported 0 parts, nothing to do!')
        else:
            logger.info(f'Mouser reported {number_of_results} parts')
            new_name = data['SKU']
            if number_of_results > 1:
                SupplierPartChange.objects.create(part=p,
                                                  change_type="add",
                                                  comment=f'{number_of_results} supplier parts reported',
                                                  new_value = new_name + '...'
                                                 )
            else:
                if new_name != 'N/A':
                    SupplierPartChange.objects.create(part=p,
                                                      change_type="add",
                                                      comment=f'{number_of_results} supplier part available',
                                                      new_value = new_name
                                                     )
        return True


