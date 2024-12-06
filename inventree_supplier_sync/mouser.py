"""
Unfortunately Mouser does not list possible errir codes. Here are some examples:

If the access key is wrong:
{'Errors': [
            {'Id': 0,
             'Code': 'Invalid',
             'Message': 'Invalid unique identifier.',
             'ResourceKey': 'InvalidIdentifier',
             'ResourceFormatString': None,
             'ResourceFormatString2': None,
             'PropertyName': 'API Key'}
           ], 'SearchResults': None}

If the access key is empty:
{'Errors': [
            {'Id': 0,
             'Code': 'Required',
             'Message': 'Required',
             'ResourceKey': 'Required',
             'ResourceFormatString': None,
             'ResourceFormatString2': None,
             'PropertyName': 'API Key'}
           ], 'SearchResults': None}

If there are invalid characters in the search string like non ACSII:
{'Errors': [
            {'Id': 0,
             'Code': 'InvalidCharacters',
             'Message': None,
             'ResourceKey': None,
             'ResourceFormatString': None,
             'ResourceFormatString2': None,
             'PropertyName': None}
           ], 'SearchResults': None}

If you created more than 1000 requests within 24 hours:
{'Errors': [
            {'Id': 0,
             'Code': 'TooManyRequests',
             'Message': None,
             'ResourceKey': None,
             'ResourceFormatString': None,
             'ResourceFormatString2': None,
             'PropertyName': None}
           ], 'SearchResults': None}

"""
from common.models import InvenTreeSetting

from .request_wrappers import Wrappers
from .meta_access import MetaAccess

import re
import json


class Mouser():

    # --------------------------- get_mouser_partdata -----------------------------
    def get_mouser_partdata(self, sku, options):

        part_data = {}
        part = {"SearchByPartRequest": {"mouserPartNumber": sku,
                                        "partSearchOptions": options,
                                        }
                }
        url = 'https://api.mouser.com/api/v1.0/search/partnumber?apiKey=' + self.get_setting('MOUSERSEARCHKEY')
        header = {'Content-type': 'application/json', 'Accept': 'application/json'}
        response = Wrappers.post_request(self, json.dumps(part), url, header)
        try:
            response = response.json()
        except Exception:
            part_data['error_status'] = response
            part_data['number_of_results'] = -1
            return part_data

        # If we are here, Mouser responded. Lets look for errors. Some
        # errors do not come in the Errors array, but in a Message.
        # Lets check those first
        try: 
            part_data['error_status'] = response['Message'] 
            part_data['number_of_results'] = -1
            return part_data
        except Exception:
            pass

        # Then we evaluate the Errors array. there are some known errors
        # and the rest. 
        if response['Errors'] != []:
            if response['Errors'][0]['Code'] == 'InvalidCharacters':
                part_data['error_status'] = 'InvalidCharacters'
                part_data['number_of_results'] = -1
            elif response['Errors'][0]['Code'] == 'Invalid':
                part_data['error_status'] = 'InvalidAuthorization'
                part_data['number_of_results'] = -1
            elif response['Errors'][0]['Code'] == 'TooManyRequests':
                part_data['error_status'] = 'TooManyRequests'
                part_data['number_of_results'] = -1
            else:
                part_data['error_status'] = response['Errors'][0]['Code']
                part_data['number_of_results'] = -1
            return part_data

        # If we came here, no errors have been reported and there sould be results.
        number_of_results = int(response['SearchResults']['NumberOfResult'])
        if number_of_results == 0:
            part_data['error_status'] = 'OK'
            part_data['number_of_results'] = number_of_results
            return part_data

        # Here least one result has been reported
        part_data['error_status'] = 'OK'
        part_data['number_of_results'] = number_of_results
        part_data['SKU'] = response['SearchResults']['Parts'][0]['MouserPartNumber']
        part_data['MPN'] = response['SearchResults']['Parts'][0]['ManufacturerPartNumber']
        part_data['URL'] = response['SearchResults']['Parts'][0]['ProductDetailUrl']
        part_data['lifecycle_status'] = response['SearchResults']['Parts'][0]['LifecycleStatus']
        part_data['pack_quantity'] = response['SearchResults']['Parts'][0]['Mult']
        part_data['description'] = response['SearchResults']['Parts'][0]['Description']
        part_data['package'] = Mouser.get_mouser_package(self, response['SearchResults']['Parts'][0])
        part_data['price_breaks'] = []

        # If we got serveral results, do not collect the price breaks
        if number_of_results > 1:
            return part_data

        for pb in response['SearchResults']['Parts'][0]['PriceBreaks']:
            new_price = Mouser.reformat_mouser_price(self, pb['Price'])
            part_data['price_breaks'].append({'Quantity': pb['Quantity'], 'Price': new_price, 'Currency': pb['Currency']})
        return part_data

    # ------------------------------- get_mouser_package --------------------------
    # Extracts the available packages from the Mouser part data json
    def get_mouser_package(self, part_data):
        package = ''
        try:
            attributes = part_data['ProductAttributes']
        except Exception:
            return None
        for att in attributes:
            if att['AttributeName'] == 'Verpackung':
                package = package + att['AttributeValue'] + ', '
        return (package)

    # --------------------------- reformat_mouser_price --------------------------
    # We need a Mouser specific modification to the price answer because they put
    # funny things inside like an EURO sign and they use , instead of .

    def reformat_mouser_price(self, price):
        price = price.replace('.', '')
        price = price.replace(',', '.')
        non_decimal = re.compile(r'[^\d.]+')
        price = non_decimal.sub('', price)
        if price == '':
            price = 0
        else:
            price = float(price)
        return price
