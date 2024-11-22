[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

# inventree-supplier-sync

This is a scheduled task plugin for [InvenTree](https://inventree.org), which gets data from
the supplier Mouser and puts it into the InvenTree Database. 

## Installation

```
pip install git+https://github.com/SergeoLacruz/inventree-supplier-sync
```

Got to the plugin settings and set minimum the following switches on:

- Enable App integration
- Enable URL integration
- Enable navigation integration
- Enable schedule integration

This plugin uses he AppMixin which makes it important to run a migrate
after installing. 

- stop the server
- invoke migrate
- start the server

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

## Usage
### What it does
The plugin uses the ScheduleMixin and runs every few minutes. On each run it
synchronizes one part with the distributor Mouser. The following actions are performed:

In case the part already has a supplier part from Mouser the plugin downloads
the actual partdata. It stores the live cycle into the notes field and stores a 
message in case it was a changed. Then in updates the price breaks

In case no supplier part exists the plugin searches the Mouser catalog using the part name. 
If Mouser reports parts the results a are stored for later usage. 

Parts are excluded from the synchronisation if:

- the part is not active
- the part is not purchasable
- the category of the part is excluded. 

To exclude a category put {"supplier_sync": {"exclude": "True"}} into the metadata
field of the category. 

The Mouser API limits the access frequency and the total number of accesses per 24 hours. 
Because of that the plugin runs every two minutes and works always on one part. It uses
a setting to persistently store the primary key of the next part to by synchronized. To 
get the value we use cache=False option of the get_settings function. Otherwise plugin 
does not work properly as the value is not correctly changed.

### View the results
The plugin stores synchronization results into the database. That's why the AppMixin
is needed. The results are visible on a new tab under parts. 

![Result Panel](https://github.com/SergeoLacruz/inventree-supplier-sync/blob/master/pictures/results_panel.png)

For the two first parts the live cycle was changed. You can now decide what to do
with those parts and delete the sync entry using the delete button. 

624020 Mouser reported two hits. Mouser has parts in the catalog with
no valid SKU (N/A). Usually these are old parts not available any longer. 
You can ignore them. Click on the N/A to come to the Mouser WEB page and see the 
other results. 

504013 reported just one hit. You can click on the green shopping cart to 
automatically add the supplier part to your database.

360106 reported 348 parts. Here something with the part name might be wrong. 
You need to have a look. 

## Prerequisites
For the plugin to work your database needs to full fill some requirements:

- All parts need to have an IPN
- All parts need to have a name that matches the manufacturer part number 

## Things to do
Actually you need to scroll through the log to find problems with the received data. This
is not comfortable. 

Error handling is not good yet. In case Mouser returns garbage the plugin might just crash 
because keys in the json might be missing

E.g. Mouser sends more data like availability, packaging and so on. It may make sense to 
include these into the properties to update.
