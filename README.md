[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![PEP](https://github.com/inventree/inventree-python/actions/workflows/pep.yaml/badge.svg)


# inventree-supplier-plugin

This is a scheduled task plugin for [InvenTree](https://inventree.org), which gets data from a
supplier like Mouser and puts it into the Inventree Database. 
It is work in progress. A lot of things need to be done. 
Error handling is very basic. 

## Installation

There is no package yet. Just copy the code into src/Inventree/plugins

## What it does
The plugin uses the scheduled task mixin and runs every few minutes. On each run it
synchronizes one part with the distributor Mouser. In case no supplier part exists
the plugin creates one and ads the mouser part number to the SKU field. In case a 
supplier part with supplier Mouser already exists the plugin creates new price breaks. 
Mouser allows 1000 hits per Day. So the plugin can run every two minutes. 

Parts are excluded from the synchronisation if:

- the part is no active
- the part is no purchasable
- the category of the part is excluded. 

Because there is no "purchasable" flag on categories we use metadata to exclude it. 
Put {"supplier_sync": {"exclude": "True"}} into the metadata field of the category. 

## Configuration Options
### Supplier API key
Accessing the Mouser REST API requires an access key. You can create it easily on the Mouser 
WEB page. Put the key here.

### Supplier Link
Put here the link to the API. Usually it is constant and does not need to be changed but who knows. 

### Proxies
In case you need to authorise a proxy server between your Inventree server and the internet
put the required sting here for example proxies={ 'https' : 'http://user:password@ipaddress:port' }

### The actual component
This is the primary key of the next component to be synchronized. It is a persistent storage 
of the plugin and changes automatically. You should not touch it.

## How it works
The Mouser API limits the access frequency and the total number of accesses per 24 hours. 
Because of that the plugin runs every two minutes an and works always on one part. It uses
a setting to persistantly store the primary key of the next part to by synchronized. The
function UpdatePart does the magic. 

In case the part has no supplier part from the supplier Mouser the plugin tries to create one. 
It runs a part number search on the mouser API with the parts manufacturer part number. 
the search can return several results e.g. BC107 will find BC107A as well. 
In case Mouser reports exactly one hit, a supplier part is created and the mouser part number
is put into the SKU field. In case more than one parts are reported the plugin creates a supplier
part and ads a generic string into the SKu field. The plugin cannot decide which part is the 
right one. These parts can be sorted out manually.

In case the part has already a Mouser part an exact search on the SKU is executed. This search 
usually finds exactly one result. In that case all price breaks are replaced with actual ones. 
It might happen that the search does not return any result. In that case the part has been
removed from Mouser and the supplier part is deleted. 

## Things to to
Actually you need to scroll through the log to find problems with the received data. This
is not comfortable. 

Error handling is not good yet. In case Mouser return garbage the plugin might just crash 
because keys in the json might be missing

The plugin should be more generic to easier support other suppliers like Digikey. 
