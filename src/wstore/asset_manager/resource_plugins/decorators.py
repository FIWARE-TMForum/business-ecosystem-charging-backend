# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S. L.

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

from functools import wraps
from logging import getLogger

from bson.objectid import ObjectId

from wstore.asset_manager.errors import ProductError
from wstore.asset_manager.models import Resource
from wstore.models import ResourcePlugin
from wstore.ordering.models import Offering

logger = getLogger("wstore.default_logger")


def _get_plugin_model(name):
    try:
        plugin_model = ResourcePlugin.objects.get(name=name)
    except:
        # Validate resource type
        raise ProductError("The given product specification contains a not supported asset type: " + name)

    return plugin_model


def load_plugin_module(asset_t):
    plugin_model = _get_plugin_model(asset_t)
    module = plugin_model.module
    module_class_name = module.split(".")[-1]
    module_package = module.partition("." + module_class_name)[0]

    module_class = getattr(
        __import__(module_package, globals(), locals(), [module_class_name], 0),
        module_class_name,
    )

    logger.debug(f"Loaded plugin module for {asset_t}")
    return module_class(plugin_model)


def on_product_spec_validation(func):
    @wraps(func)
    def wrapper(self, provider, asset_t, media_type, url, asset_id):
        plugin_module = load_plugin_module(asset_t)

        # On pre validation
        plugin_module.on_pre_product_spec_validation(provider, asset_t, media_type, url)

        # Call method
        asset = func(self, provider, asset_t, media_type, url, asset_id)

        # On post validation
        plugin_module.on_post_product_spec_validation(provider, asset)

        return asset

    return wrapper


def on_product_spec_attachment(func):
    @wraps(func)
    def wrapper(self, asset, asset_t, product_spec):
        if not len(asset.bundled_assets):
            # Load plugin module
            plugin_module = load_plugin_module(asset_t)

            # Call on pre create event handler
            plugin_module.on_pre_product_spec_attachment(asset, asset_t, product_spec)

        # Call method
        func(self, asset, asset_t, product_spec)

        if not len(asset.bundled_assets):
            # Call on post create event handler
            plugin_module.on_post_product_spec_attachment(asset, asset_t, product_spec)

    return wrapper


def on_product_spec_upgrade(func):
    @wraps(func)
    def wrapper(self, asset, asset_t, product_spec):
        if not len(asset.bundled_assets):
            # Load plugin module
            plugin_module = load_plugin_module(asset_t)

            # Call on pre create event handler
            plugin_module.on_pre_product_spec_upgrade(asset, asset_t, product_spec)

        # Call method
        func(self, asset, asset_t, product_spec)

        if not len(asset.bundled_assets):
            # Call on post create event handler
            plugin_module.on_post_product_spec_upgrade(asset, asset_t, product_spec)

    return wrapper


def _expand_bundled_assets(offering_assets):
    assets = []
    for off_asset in offering_assets:
        if len(off_asset.bundled_assets) > 0:
            for bundled_asset_pk in off_asset.bundled_assets:
                assets.append(Resource.objects.get(pk=bundled_asset_pk))
        else:
            assets.append(off_asset)

    return assets


def on_product_offering_validation(func):
    @wraps(func)
    def wrapper(self, provider, product_offering, bundled_offerings):
        offering_assets = []
        if len(bundled_offerings) > 0:
            # Get bundled offerings assets
            offering_assets = [offering.asset for offering in bundled_offerings if offering.is_digital]
        else:
            # Get offering asset
            asset = Resource.objects.filter(product_id=product_offering["productSpecification"]["id"])
            offering_assets.extend(asset)

        # Get the effective assets
        assets = _expand_bundled_assets(offering_assets)

        for asset in assets:
            plugin_module = load_plugin_module(asset.resource_type)
            plugin_module.on_pre_product_offering_validation(asset, product_offering)

        is_open = func(self, provider, product_offering, bundled_offerings)

        for asset in assets:
            plugin_module.on_post_product_offering_validation(asset, product_offering)

        return is_open

    return wrapper


def _execute_asset_event(asset, order, contract, type_):
    # Load plugin module
    plugin_module = load_plugin_module(asset.resource_type)

    events = {
        "activate": plugin_module.on_product_acquisition,
        "suspend": plugin_module.on_product_suspension,
        "usage": plugin_module.on_usage_refresh,
    }
    # Execute event
    events[type_](asset, contract, order)


def process_product_notification(order, contract, type_):
    # Get digital asset from the contract
    offering_assets = []
    offering = Offering.objects.get(pk=ObjectId(contract.offering))

    if len(offering.bundled_offerings) > 0:
        offering_assets = [
            Offering.objects.get(pk=ObjectId(key)).asset
            for key in offering.bundled_offerings
            if Offering.objects.get(pk=ObjectId(key)).is_digital
        ]

    elif offering.is_digital:
        offering_assets = [offering.asset]

    assets = _expand_bundled_assets(offering_assets)

    for event_asset in assets:
        _execute_asset_event(event_asset, order, contract, type_)


def on_product_acquired(order, contract):
    process_product_notification(order, contract, "activate")


def on_product_suspended(order, contract):
    process_product_notification(order, contract, "suspend")


def on_usage_refreshed(order, contract):
    process_product_notification(order, contract, "usage")

##################################################

def on_service_spec_validation(func):
    @wraps(func)
    def wrapper(self, provider, asset_t, media_type, url):
    #def wrapper(self, provider, asset_t, media_type, url, asset_id):
        print("Entra en los decorators")
        plugin_module = load_plugin_module(asset_t)
        print("Tras el load_plugin_module")

        # On pre validation
        plugin_module.on_pre_product_spec_validation(provider, asset_t, media_type, url)
        print("On pre validation")

        # Call method
        #asset = func(self, provider, asset_t, media_type, url, asset_id)
        asset = func(self, provider, asset_t, media_type, url)
        print("Call method")

        # On post validation
        plugin_module.on_post_product_spec_validation(provider, asset)

        print("Sale de los decorators")

        return asset

    return wrapper

##################################################