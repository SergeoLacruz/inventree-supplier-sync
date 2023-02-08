# Plugin that syncronises parts with the Mouser database. 
# Todo :
# Go directly to next part in case no update happened


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
formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('sync.log')
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

#---------------------------- MouserSyncPlugin --------------------------------------------------
class SupplierSyncPlugin(ScheduleMixin, SettingsMixin, InvenTreePlugin):

    NAME = "SupplierSyncPlugin"
    SLUG = "suppliersync"
    TITLE = "Sync parts with a supplier"
    AUTHOR = "Michael"
    PUBLISH_DATE = "2023-01-04T20:55:08.914461+00:00"
    VERSION= '0.0.1'
    DESCRIPTION = 'Syncronize parts with Supplier SKU and price breaks'
    MIN_VERSION = '0.11.0'

    SCHEDULED_TASKS = {
        'member': {
            'func': 'UpdatePart',
            'schedule': 'I',
            'minutes': 1,
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

        Update = int(self.get_setting('AKTPK', cache=False))
        logger.info('Running update on pk %i',Update)
        AllParts=Part.objects.all()
        FirstPart=AllParts[0].pk
        LastPart=AllParts[len(AllParts)-1].pk
        AllPartsPK=[]
        for p in AllParts:
            AllPartsPK.append(p.pk)
        if Update not in AllPartsPK:
            Update=FirstPart

        Success=True
        PartToUpdate=Part.objects.get(pk=Update)
        if self.ShoudBeUpdated(PartToUpdate):
            SupplierParts=self.GetExistingSupplierParts(PartToUpdate.supplier_parts)
            if len(SupplierParts)>0:
                for sp in SupplierParts:
                    if sp.SKU != 'N/A' and sp.SKU != self.GenericSKU:    
                        Success=self.UpdateSupplierParts(sp)
            else:
                Success=self.CreateSupplierPart(PartToUpdate)
        if Success:
            Index=0
            for p in AllPartsPK:
                if p==Update:
                    break
                Index +=1
            if Update==LastPart:    
                Update=FirstPart
            else:
                Update=AllPartsPK[Index+1]
            self.set_setting('AKTPK',str(Update))

#------------------------------------------------------------------------------------------
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
# into the catagory meta data field. 

    def ShoudBeUpdated(self,p):
        try:
            CatExclude=SyncMetadata=p.category.get_metadata('supplier_sync')['exclude']=='True'
        except:
            CatExclude=False

        if CatExclude:
            logger.info('Skipping part %s. Catagory is excluded',p.IPN)
            return False
        if not p.purchaseable:
            logger.info('Skipping part %s. Part is not purchasable',p.IPN)
            return False
        if not p.active:
            logger.info('Skipping part %s. Part is not active',p.IPN)
            return False
        logger.info('Updating part %s %s', p.IPN, p.name)
        return True

#------------------------------- GetSupplierData -----------------------------------------
# This creates the request sends it to the suppliere API and recieves the result
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

    # We need a supplier specicfic modification to the price answer because they put 
    # funny things inside like an EURO sifn into the number and use , instead of . 
    def ReformatPrice(self,price):
         return price[0:len(price)-1].replace(',','.')

#----------------------------- CreateSupplierPart ----------------------------------------
    def CreateSupplierPart(self,p):
        logger.info('Try to create mouser part for %s',p.IPN)
        Results, Data=self.GetSupplierData(p.name,'none')
        Supplier=Company.objects.get(name=self.SupplierName)
        if Results == -1:
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
# In case the part has already a supplier part we update the price breaks here. 
# We just erase all price breaks and create new ones. 

    def UpdateSupplierParts(self,sp):

        logger.info('Updating mouser part for %s',sp.SKU)
        Results, Data=self.GetSupplierData(sp.SKU,'exact')
#        print('Lifecycle',Data['Parts'][0]['LifecycleStatus'])
        if Results == -1:
            return False
        elif Results == 0:
            logger.info('%s reported 0 parts. Nothing to update', self.SupplierName)
        elif Results == 1:
            logger.info('%s repoted 1 part. Updating price breaks', self.SupplierName)
            spb=SupplierPriceBreak.objects.filter(part=sp.pk).all()
            for pb in spb:
                pb.delete()
            for pb in Data['Parts'][0]['PriceBreaks']:
                NewPrice=self.ReformatPrice(pb['Price'])
                SupplierPriceBreak.objects.create(part=sp, quantity=pb['Quantity'],price=NewPrice)
        elif Results>1:
            logger.info('%s reported %i parts. No update', self.SupplierName, Results)
        return True

