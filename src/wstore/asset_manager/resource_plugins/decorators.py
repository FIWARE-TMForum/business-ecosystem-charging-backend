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

from wstore.asset_manager.errors import ServiceError
from wstore.asset_manager.models import Resource
from wstore.models import ResourcePlugin
from wstore.ordering.models import Offering

logger = getLogger("wstore.default_logger")


def _get_plugin_model(category_id):
    plugins = list(ResourcePlugin.objects.filter(category_id=category_id))

    if len(plugins) > 1:
        raise ServiceError("The service category resolves to more than one installed plugin")

    return plugins[0] if plugins else None


def load_plugin_module(service_spec):
    entries = service_spec.get("specCharacteristic")
    if not isinstance(entries, list):
        return None

    service_types = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and entry["name"].strip().lower() == "service type"
    ]

    if not service_types:
        return None

    if len(service_types) != 1:
        raise ServiceError("The service specification must contain exactly one Service Type characteristic")

    values = service_types[0].get("characteristicValueSpecification")

    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise ServiceError("The Service Type characteristic must contain exactly one value")

    category_ref = values[0].get("value")

    if (
        not isinstance(category_ref, dict)
        or not isinstance(category_ref.get("id"), str)
        or not category_ref["id"].strip()
    ):
        raise ServiceError("Service Type must contain a service category reference with an id")

    plugin_model = _get_plugin_model(category_id=category_ref["id"])

    return _load_plugin_model(plugin_model) if plugin_model is not None else None


def _load_plugin_model(plugin_model):
    module = plugin_model.module
    module_class_name = module.split(".")[-1]
    module_package = module.partition("." + module_class_name)[0]

    module_class = getattr(
        __import__(module_package, globals(), locals(), [module_class_name], 0),
        module_class_name,
    )

    logger.debug("Loaded plugin module %s", module)
    return module_class(plugin_model)


# Legacy plugin dispatch is disabled until callers supply the new hook arguments.
# Keep running the wrapped backend operations during the migration.
def on_product_spec_validation(func):
    @wraps(func)
    def wrapper(self, provider, asset_t, media_type, url, asset_id):
        # plugin_module = load_plugin_module(asset_t)
        # plugin_module.on_pre_product_spec_validation(provider, asset_t, media_type, url)
        asset = func(self, provider, asset_t, media_type, url, asset_id)
        # plugin_module.on_post_product_spec_validation(provider, asset)
        return asset

    return wrapper


def on_product_spec_attachment(func):
    @wraps(func)
    def wrapper(self, asset, asset_t, product_spec):
        # plugin_module = load_plugin_module(asset_t)
        # plugin_module.on_pre_product_spec_attachment(asset, asset_t, product_spec)
        func(self, asset, asset_t, product_spec)
        # plugin_module.on_post_product_spec_attachment(asset, asset_t, product_spec)

    return wrapper


def on_product_spec_upgrade(func):
    @wraps(func)
    def wrapper(self, asset, asset_t, product_spec):
        # plugin_module = load_plugin_module(asset_t)
        # plugin_module.on_pre_product_spec_upgrade(asset, asset_t, product_spec)
        func(self, asset, asset_t, product_spec)
        # plugin_module.on_post_product_spec_upgrade(asset, asset_t, product_spec)

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
        # Plugin resolution/asset traversal is deferred to the service-spec migration.
        # plugin_module.on_pre_product_offering_validation(asset, product_offering)
        is_open = func(self, provider, product_offering, bundled_offerings)
        # plugin_module.on_post_product_offering_validation(asset, product_offering)
        return is_open

    return wrapper


def process_product_notification(order, contract, type_):
    pass
    # Get digital asset from the contract
    # offering_assets = []
    # offering = Offering.objects.get(pk=ObjectId(contract.offering))

    # if len(offering.bundled_offerings) > 0:
    #     offering_assets = [
    #         Offering.objects.get(pk=ObjectId(key)).asset
    #         for key in offering.bundled_offerings
    #         if Offering.objects.get(pk=ObjectId(key)).is_digital
    #     ]

    # elif offering.is_digital:
    #     offering_assets = [offering.asset]

    # assets = _expand_bundled_assets(offering_assets)


def on_product_acquired(order, contract):
    process_product_notification(order, contract, "activate")


def on_product_suspended(order, contract):
    process_product_notification(order, contract, "suspend")


def on_usage_refreshed(order, contract):
    process_product_notification(order, contract, "usage")


def on_service_spec_validation(func):
    @wraps(func)
    def wrapper(self, provider, service_spec):
        plugin = load_plugin_module(service_spec=service_spec)

        if plugin is None:
            return

        plugin.on_pre_service_spec_validation(provider, service_spec)

        result = func(self, provider, service_spec, plugin._model)

        plugin.on_post_service_spec_validation(provider, service_spec)

        return result

    return wrapper
