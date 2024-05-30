# -*- coding: utf-8 -*-

import setuptools
from inventree_supplier_sync.version import PLUGIN_VERSION


with open('README.md', encoding='utf-8') as f:
    long_description = f.read()


setuptools.setup(
    name="inventree-supplier-sync",

    version=PLUGIN_VERSION,

    author="Michael Buchmann",

    author_email="michael@buchmann.ruhr",

    description="Syncronize parts with Supplier SKU and price breaks",

    long_description=long_description,

    long_description_content_type='text/markdown',

    keywords="inventree supplier price breaks inventory",

    url="https://github.com/SergeoLacruz/inventree-supplier-sync",

    license="MIT",

    packages=setuptools.find_packages(),

    install_requires=[
    ],

    setup_requires=[
        "wheel",
        "twine",
    ],

    python_requires=">=3.6",

    entry_points={
        "inventree_plugins": [
            "SupplierSyncPlugin = inventree_supplier_sync.supplier_sync:SupplierSyncPlugin"
        ]
    },
)
