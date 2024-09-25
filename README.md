[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

# inventree-supplier-sync

This is a scheduled task plugin for [InvenTree](https://inventree.org), which gets data from a
supplier like Mouser and puts it into the InvenTree Database. 

## Installation

```
pip install git+https://github.com/SergeoLacruz/inventree-supplier-sync
```

## What it does
The plugin uses the scheduled task mixin and runs every few minutes. On each run it
synchronizes one part with the distributor Mouser. In case no supplier part exists
the plugin creates one and ads the mouser part number to the SKU field. In case a 
supplier part with supplier Mouser already exists the plugin creates new price breaks. 
Mouser allows 1000 hits per Day. So the plugin can run every two minutes. 

Parts are excluded from the synchronisation if:

- the part is not active
- the part is not purchasable
- the category of the part is excluded. 

Because there is no "purchasable" flag on categories we use metadata to exclude it. 
Put {"supplier_sync": {"exclude": "True"}} into the metadata field of the category. 

## Configuration Options

### Mouser Supplier ID
Place here the primary key of the supplier Mouser in your system. You can select from a list of
your suppliers. If this is not set the panel will not be displayed and a error is raised.

### Mouser Serach API key
Accessing the Mouser REST API requires an access key. You can create it easily on the Mouser 
WEB page. Put the key here.

### Supplier Link
Put here the link to the API. Usually it is constant and does not need to be changed but who knows. 

### Proxies
In case you need to authorise a proxy server between your InvenTree server and the internet
put the required sting here for example something like { 'https' : 'https://user:password@ipaddress:port' }
Please refer to the code for details.

### The actual component
This is the primary key of the next component to be synchronized. It is a persistent storage 
of the plugin and changes automatically. You should not touch it.

## How it works
The Mouser API limits the access frequency and the total number of accesses per 24 hours. 
Because of that the plugin runs every two minutes and works always on one part. It uses
a setting to persistently store the primary key of the next part to by synchronized. To 
get the value we use cache=False option of the get_settings function. Otherwise plugin 
does not work properly as the value is not correctly changed.

In case the part has a Mouser supplier part an exact search on the SKU is executed. This search 
usually finds exactly one result. In that case all price breaks are replaced with actual ones. 
It might happen that the search does not return any result. In that case the part has been
removed from Mouser and the supplier part is deleted. 

## Things to to
Actually you need to scroll through the log to find problems with the received data. This
is not comfortable. 

Error handling is not good yet. In case Mouser returns garbage the plugin might just crash 
because keys in the json might be missing

E.g. Mouser sends more data like availability, packaging and so on. I may make sense to 
include these into the properties to update.
