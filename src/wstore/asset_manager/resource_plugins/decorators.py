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

from wstore.asset_manager.errors import ServiceError
from wstore.asset_manager.resource_plugins.resolver import CatalogResolver
from wstore.models import ResourcePlugin

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


def _get_plugins(associations):
    plugins = []

    for service_spec, product_spec in associations:
        plugin = load_plugin_module(service_spec=service_spec)

        if plugin is not None:
            plugins.append((plugin, service_spec, product_spec))

    return plugins


def on_product_spec_validation(provider, product_spec):
    associations = CatalogResolver().product_services(product_spec)

    for plugin, service_spec, product in _get_plugins(associations):
        plugin.on_product_spec_validation(provider, service_spec, product)


def on_product_offering_validation(func):
    @wraps(func)
    def wrapper(self, provider, product_offering):
        associations = CatalogResolver().offering_services(product_offering)
        plugins = _get_plugins(associations)

        for plugin, service_spec, product_spec in plugins:
            plugin.on_pre_product_offering_validation(provider, service_spec, product_spec, product_offering)

        result = func(self, provider, product_offering)

        for plugin, service_spec, product_spec in plugins:
            plugin.on_post_product_offering_validation(provider, service_spec, product_spec, product_offering)

        return result

    return wrapper


def process_product_notification(order, contract, type_):
    # Purchased-service dispatch is integrated in its own lifecycle step.
    pass


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
