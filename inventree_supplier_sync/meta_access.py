# Class to access the meta data field in InvenTree. The wrappers build
# a dict with plugin name so that the data from different plugins does
# not overlap

class MetaAccess():

    def get_value(self, inventree_object, app, key):
        try:
            value = inventree_object.metadata[app][key]
        except Exception:
            value = None
        return (value)

    def set_value(self, inventree_object, app, key, value):
        data = inventree_object.metadata
        if data is None:
            data = {}
        if app in data:
            app_data = data[app]
            app_data.update({key: value})
            data.update({app: app_data})
        else:
            data.update({app: {key: value}})
        inventree_object.metadata = data
        inventree_object.save()
