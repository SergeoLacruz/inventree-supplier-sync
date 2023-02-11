# Plugin that syncronises parts with the Mouser database. 

import requests
import json
import logging

from plugin import InvenTreePlugin
from plugin.mixins import ScheduleMixin, SettingsMixin
from part.models import Part
from part.models import SupplierPart
from company.models import Company
from company.models import SupplierPriceBreak

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
#fh = logging.FileHandler('sync.log')
#fh.setLevel(logging.DEBUG)
#formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#fh.setFormatter(formatter)
#logger.addHandler(fh)

#---------------------------- MouserSyncPlugin --------------------------------------------------
class SupplierSyncPlugin(ScheduleMixin, SettingsMixin, InvenTreePlugin):

    NAME = "SupplierSyncPlugin"
    SLUG = "suppliersync"
    TITLE = "Sync parts with a supplier"
    AUTHOR = "Michael"
    PUBLISH_DATE = "2023-02-11T20:55:08.914461+00:00"
    VERSION = '0.0.1'
    DESCRIPTION = 'Syncronize parts with Supplier SKU and price breaks'
    MIN_VERSION = '0.11.0'

    SCHEDULED_TASKS = {
        'member': {
            'func': 'UpdatePart',
            'schedule': 'I',
            'minutes': 2,
        }
    }

    SETTINGS = {
        'SUPPLIERKEY': {
            'name': 'Supplier API Key',
            'description': 'Place here your key for the suppliers API',
        },
        'SUPPLIERLINK': {
            'name': 'Supplier link',
            'description': 'Comlpete http link to the suppliers API',
            'default': 'https://api.mouser.com/api/v1.0/search/partnumber?apiKey=',
        },
        'PROXIES': {
            'name': 'Proxies',
            'description': 'Access to proxy server if needed',
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

    # Set some supplier specific constants
    SupplierName='Mouser'
    GenericSKU='MouserGeneric'
    SupplierLink='https://www.mouser.de/c/?q='

#---------------------------- UpdatePart --------------------------------------------------
# Main function that is called by the scheduler
#------------------------------------------------------------------------------------------
    def UpdatePart(self, *args, **kwargs):

        Update=int(self.get_setting('AKTPK', cache = False))
        logger.info('Running update on pk %i',Update)

        # First check if the pk exists. It might have been deleted between the executions
        # ore someone might have changed the AKTPK manually. We go back to start in that case.
        AllParts=Part.objects.all()
        AllPartsPK=[]
        for p in AllParts:
            AllPartsPK.append(p.pk)
        if Update not in AllPartsPK:
            Update=AllParts[0].pk

        PartToUpdate=Part.objects.get(pk=Update)

        # In case the part shall not be updated go to next one to not loose the slot. 
        while not self.ShoudBeUpdated(PartToUpdate):
            Update=self.GetNextPart(AllParts,PartToUpdate).pk
            PartToUpdate=Part.objects.get(pk=Update)
        Success=True
        SupplierParts=self.GetExistingSupplierParts(PartToUpdate.supplier_parts)
        if len(SupplierParts)>0:
            for sp in SupplierParts:
                if sp.SKU != 'N/A' and sp.SKU != self.GenericSKU:    
                    Success=self.UpdateSupplierParts(sp)
        else:
            Success=self.CreateSupplierPart(PartToUpdate)

        # In case the update was OK we go to the next one. Otherwise we try it again and again...
        if Success:
            Update=self.GetNextPart(AllParts,PartToUpdate).pk
            self.set_setting('AKTPK',str(Update))

 
#------------------------------------------------------------------------------------------
#------------------------------ GetNextPart -----------------------------------------------
# Get the next part to be updated.

    def GetNextPart(self, parts, item):
        getit=False
        for m in parts:
            if getit:
                return m
            if item == m:
                getit=True
        if getit:
            # This would happen when the last
            # item made getit True
            return parts[0]
        return False

#----------------------- GetExistingSupplierParts -----------------------------------------
# Returns all existing supplier parts where the supplier name is SupplierName

    def GetExistingSupplierParts(self,sp):
        SupplierParts=[]

        for ssp in sp.all():
            if ssp.supplier.name == self.SupplierName:
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
            logger.debug('Skipping part %s. Category is excluded',p.IPN)
            return False
        if not p.purchaseable:
            logger.debug('Skipping part %s. Part is not purchasable',p.IPN)
            return False
        if not p.active:
            logger.debug('Skipping part %s. Part is not active',p.IPN)
            return False
        logger.debug('Updating part %s %s', p.IPN, p.name)
        return True

#------------------------------- GetSupplierData -----------------------------------------
# This creates the request sends it to the supplier API and receives the result
# This part is supplier specific. 

    def GetSupplierData(self,Keyword, Options):

            headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
            part={
              "SearchByPartRequest": {
              "mouserPartNumber": Keyword,
              "partSearchOptions": Options
              }
            }
            Response=requests.post(self.get_setting('SUPPLIERLINK')+self.get_setting('SUPPLIERKEY'),
                                   proxies=self.get_setting('PROXIES'), 
                                   data=json.dumps(part), 
                                   headers=headers)
            JsonResponse=Response.json()
#            print(JsonResponse)
            try:
                if len(JsonResponse['Errors']) > 0:
                    logger.error('Error received from supplier API: %s', JsonResponse['Errors'][0]['Message'])
                    return -1, JsonResponse['Errors'][0]['Message']
                else:
                    return JsonResponse['SearchResults']['NumberOfResult'], JsonResponse['SearchResults']
            except:
                logger.error('No valid answer received from supplier')
                return -1, 'No valid answer received from supplier'

    # We need a supplier specific modification to the price answer because they put 
    # funny things inside like an EURO sign into the number and use , instead of . 
    def ReformatPrice(self,price):
         return price[0:len(price)-1].replace(',','.')

#----------------------------- CreateSupplierPart ----------------------------------------
# Here we use a normal search because otherwise the MPN are not found. This means that 
# might end up with several results. In that case we create a SupplierPart with a 
# generic SKU and the search link to the supplier. These cases need to be handled manually
# because we cannot decide which part is the real one. 

    def CreateSupplierPart(self,p):
        logger.debug('Try to create mouser part for %s',p.IPN)
        Results, Data=self.GetSupplierData(p.name,'none')
        Supplier=Company.objects.get(name=self.SupplierName)
        if Results == -1:
            raise ConnectionError('Error connecting to Supplier API',Data)
            return False
        elif  Results == 0:
            logger.info('%s reported 0 parts, no suppler part created',self.SupplierName)
        elif Results == 1:
            SupplierSKU=Data['Parts'][0]['MouserPartNumber']
            SupplierLink=Data['Parts'][0]['ProductDetailUrl']
            sp=SupplierPart.objects.create(part=p, supplier=Supplier, SKU=SupplierSKU, link=SupplierLink)
            logger.info('%s reported 1 part. Created supplier part with SKU %s',self.SupplierName, SupplierSKU)
        elif Results>1:
            SupplierLink=self.SupplierLink+p.name
            sp=SupplierPart.objects.create(part=p, supplier=Supplier, SKU=self.GenericSKU, link=SupplierLink)
            logger.info('%s reported %i parts, created generic SKU',self.SupplierName, Results)
        return True

#----------------------------- UpdateSupplierPart ----------------------------------------
# Here we use an 'exact' search because we have already the exact SKU in the database. 
# So there should be exactly one result. In this case we update the price breaks by 
# deleting the existing ones and creating new ones. 
# In case SKU does not exist # the supplier might have canceled the part. So we delete the
# SupplierPart. 
# In case we get several hits something might have gone wrong with the search. We log a warning.
# These cases need to be cleared manually. 

    def UpdateSupplierParts(self,sp):
        logger.debug('Updating mouser part for %s',sp.SKU)
        Results, Data=self.GetSupplierData(sp.SKU,'exact')
        if Results == -1:
            raise ConnectionError('Error connecting to Supplier API',Data)
            return False
        elif Results == 0:
            logger.info('SKU search on %s reported 0 parts. Deleting SupplierPart', self.SupplierName)
            sp.delete()
        elif Results == 1:
            logger.info('%s reported 1 part. Updating price breaks', self.SupplierName)
            logger.info('Lifecycle %s',Data['Parts'][0]['LifecycleStatus'])
            sp.note=Data['Parts'][0]['LifecycleStatus']
            sp.save()
            spb=SupplierPriceBreak.objects.filter(part=sp.pk).all()
            for pb in spb:
                pb.delete()
            for pb in Data['Parts'][0]['PriceBreaks']:
                NewPrice=self.ReformatPrice(pb['Price'])
                SupplierPriceBreak.objects.create(part=sp, quantity=pb['Quantity'],price=NewPrice)
        elif Results>1:
            logger.warning('%s reported %i parts. No update', self.SupplierName, Results)
        return True

