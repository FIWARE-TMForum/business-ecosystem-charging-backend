# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2023 Future Internet Consulting and Development Solutions S.L

# This file belongs to the business-charging-backend
# of the Business API Ecosystem.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import requests
from itertools import islice
from bson import ObjectId
from django.conf import settings
from django.core.exceptions import PermissionDenied

from wstore.asset_manager.catalog_validator import CatalogValidator
from wstore.asset_manager.errors import ProductError
from wstore.asset_manager.inventory_upgrader import InventoryUpgrader
from wstore.asset_manager.models import Resource, ResourcePlugin
from wstore.asset_manager.resource_plugins.decorators import (
    on_product_spec_validation,
)
from wstore.store_commons.database import DocumentLock
from wstore.store_commons.errors import ConflictError
from wstore.store_commons.rollback import downgrade_asset, downgrade_asset_pa, rollback
from wstore.store_commons.utils.url import is_valid_url
from wstore.store_commons.utils.version import is_lower_version, is_valid_version
from bson.errors import InvalidId

PAGE_LEN = 100

class ProductValidator(CatalogValidator):

    @on_product_spec_validation
    def _validate_product(self,  provider, asset_t, media_type, url, asset_id):
        print("validate_product")
        try:
            asset = Resource.objects.get(pk=ObjectId(asset_id))
            return asset
        except Resource.DoesNotExist:
            raise ProductError("The asset id included in the product specification is not valid")
        except InvalidId:
            raise ProductError("Invalid asset id")   

    def _build_bundle(self, provider, product_spec):
        if (
            "bundledProductSpecification" not in product_spec
            or not len(product_spec["bundledProductSpecification"]) > 1
        ):
            raise ProductError("A product spec bundle must contain at least two bundled product specs")

    @rollback()
    def validate_creation(self, provider, product_spec):
        if not product_spec["isBundle"] and "serviceSpecification" in product_spec:
            print("validate single creation")
            ref_ids_it = map(lambda service_spec_ref: service_spec_ref["id"] , product_spec["serviceSpecification"])
            print("mapping service spec")
            print(product_spec["serviceSpecification"])
            # Generating a query seperated by commas
            for query_ref_block in self.gen_query_block(ref_ids_it):
                service_specs = self._get_service_specs(query_ref_block)
                # Process the new digital product
                for service_spec in service_specs:
                    print(service_spec)
                    asset_t, media_type, url, asset_id = self.parse_spec_characteristics(service_spec)
                    print("parse spec char completed")
                    # Product specs can have services without assets
                    if asset_t is not None:
                        self._validate_product(provider, asset_t, media_type, url, asset_id)
                    
        elif product_spec["isBundle"]:
            
            # The product bundle may contain digital products already registered
            self._build_bundle(provider, product_spec)
    
    def gen_query_block(self, iterator):
        # Generating query id blocks
        while True:
            # generating query of ids
            ids_query = ",".join(islice(iterator, PAGE_LEN))
            if not ids_query:
                break
            yield ids_query
            
    # def _get_asset_resouces(self, asset_t, url):
    #     # Search the asset type
    #     asset_type = ResourcePlugin.objects.get(name=asset_t)

    #     # Validate location format
    #     if not is_valid_url(url):
    #         raise ProductError("The location characteristic included in the product specification is not a valid URL")

    #     # Use the location to retrieve the attached asset
    #     assets = Resource.objects.filter(download_link=url)

    #     return asset_type, assets

    # def _validate_product_characteristics(self, asset, provider, asset_t, media_type):
    #     if asset.provider != provider:
    #         raise PermissionDenied(
    #             "You are not authorized to use the digital asset specified in the location characteristic"
    #         )

    #     if asset.resource_type != asset_t:
    #         raise ProductError("The specified asset type is different from the asset one")

    #     if asset.content_type.lower() != media_type.lower():
    #         raise ProductError("The provided media type characteristic is different from the asset one")

    #     if asset.is_public:
    #         raise ProductError("It is not allowed to create products with public assets")


    # def _rollback_handler(self, provider, product_spec, rollback_method):
    #     asset_t, media_type, url, asset_id = self.parse_characteristics(product_spec)
    #     is_digital = asset_t is not None and media_type is not None and url is not None

    #     if is_digital:
    #         asset_type, assets = self._get_asset_resouces(asset_t, url)

    #         asset = assets[0]
    #         self._validate_product_characteristics(asset, provider, asset_t, media_type)
    #         rollback_method(asset)

    # def rollback_upgrade(self, provider, product_spec):
    #     def rollback_method(asset):
    #         if asset.product_id == product_spec["id"] and asset.state == "upgrading":
    #             downgrade_asset(asset)

    #     self._rollback_handler(provider, product_spec, rollback_method)

    # def _extract_digital_assets(self, bundled_specs):
    #     assets = []
    #     for bundled_info in bundled_specs:
    #         digital_asset = Resource.objects.filter(product_id=bundled_info["id"])
    #         if len(digital_asset):
    #             assets.append(digital_asset[0].pk)

    #     return assets