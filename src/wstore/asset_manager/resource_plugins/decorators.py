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

from django.conf import settings
from logging import getLogger

from wstore.asset_manager.errors import ServiceError, ResourceError
from wstore.asset_manager.resource_plugins.resolver import CatalogResolver
from wstore.models import Organization, ResourcePlugin
from wstore.ordering.inventory_client import InventoryClient

logger = getLogger("wstore.default_logger")


def _get_plugin_model(category_id, plugin_type="service"):
    plugins = list(ResourcePlugin.objects.filter(category_id=category_id, type=plugin_type))

    if len(plugins) > 1:
        error = ResourceError if plugin_type == "resource" else ServiceError
        raise error("The " + plugin_type + " category resolves to more than one installed plugin")

    return plugins[0] if plugins else None


def _get_type_characteristic(entries, plugin_type, description):
    if not isinstance(entries, list):
        return None

    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and entry["name"].strip().lower() == plugin_type + " type"
    ]
    if not matches:
        return None
    if len(matches) != 1:
        error = ResourceError if plugin_type == "resource" else ServiceError
        raise error(description + " must contain exactly one " + plugin_type.title() + " Type characteristic")
    return matches[0]


def _load_specification_plugin(specification, plugin_type, characteristics_field, values_field):
    entry = _get_type_characteristic(
        specification.get(characteristics_field), plugin_type, "The " + plugin_type + " specification"
    )
    if entry is None:
        return None

    values = entry.get(values_field)
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        error = ResourceError if plugin_type == "resource" else ServiceError
        raise error("The " + plugin_type.title() + " Type characteristic must contain exactly one value")
    return _load_category_plugin(values[0].get("value"), plugin_type)


def load_plugin_module(service_spec):
    return _load_specification_plugin(
        service_spec, "service", "specCharacteristic", "characteristicValueSpecification"
    )


def load_resource_plugin_module(resource_spec):
    return _load_specification_plugin(
        resource_spec, "resource", "resourceSpecCharacteristic", "resourceSpecCharacteristicValue"
    )


def load_service_plugin_module(service):
    """Resolve activation from the inventory instance without a catalog read."""
    entry = _get_type_characteristic(service.get("serviceCharacteristic"), "service", "The inventory service")
    return _load_category_plugin(entry.get("value"), "service") if entry is not None else None


def _load_category_plugin(category_id, plugin_type):
    if not isinstance(category_id, str) or not category_id.strip():
        error = ResourceError if plugin_type == "resource" else ServiceError
        raise error(
            plugin_type.title() + " Type must contain a non-empty " + plugin_type + " category id string"
        )

    model = _get_plugin_model(category_id=category_id, plugin_type=plugin_type)
    return _load_plugin_model(model) if model is not None else None


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

    for plugin_type, specification, product_spec in associations:
        loader = load_resource_plugin_module if plugin_type == "resource" else load_plugin_module
        plugin = loader(specification)

        if plugin is not None:
            plugins.append((plugin, specification, product_spec))

    return plugins


def on_product_spec_validation(provider, product_spec):
    associations = CatalogResolver().product_specifications(product_spec)

    for plugin, specification, product in _get_plugins(associations):
        plugin.on_product_spec_validation(provider, specification, product)


def on_product_offering_validation(func):
    @wraps(func)
    def wrapper(self, provider, product_offering):
        associations = CatalogResolver().offering_services(product_offering)
        plugins = _get_plugins(("service", specification, product) for specification, product in associations)

        for plugin, service_spec, product_spec in plugins:
            plugin.on_pre_product_offering_validation(provider, service_spec, product_spec, product_offering)

        result = func(self, provider, product_offering)

        for plugin, service_spec, product_spec in plugins:
            plugin.on_post_product_offering_validation(provider, service_spec, product_spec, product_offering)

        return result

    return wrapper


def _get_product_organization(product, role):
    party_ids = {
        party["id"]
        for party in product.get("relatedParty", [])
        if isinstance(party, dict)
        and isinstance(party.get("role"), str)
        and party["role"].lower() == role.lower()
        and isinstance(party.get("id"), str)
        and party["id"].strip()
    }

    if len(party_ids) != 1:
        raise ServiceError("The inventory product must identify one organization for role " + role)

    return Organization.objects.get(actor_id=party_ids.pop())


def on_product_activation(product, order, contract=None):
    """Dispatch product activation to its service plugins without interrupting purchase completion."""
    references = product.get("realizingService", [])

    if not isinstance(references, list):
        logger.error(
            "Cannot notify activation for product %s: realizingService must be a list", product.get("id")
        )
        return

    inventory = InventoryClient()
    organizations = None

    for reference in references:
        try:
            if (
                not isinstance(reference, dict)
                or not isinstance(reference.get("id"), str)
                or not reference["id"].strip()
            ):
                raise ServiceError("Each realizingService reference must contain a service id")

            service = inventory.get_service(reference["id"])

            if not isinstance(service, dict) or service.get("id") != reference["id"]:
                raise ServiceError("Invalid inventory service reference: " + reference["id"])

            plugin = load_service_plugin_module(service)

            if plugin is not None:
                if organizations is None:
                    organizations = (
                        _get_product_organization(product, settings.PROVIDER_ROLE),
                        _get_product_organization(product, settings.CUSTOMER_ROLE),
                    )
                provider, buyer = organizations
                plugin.on_service_activation(provider, buyer, service, product, order, contract)
        except Exception:
            # Payment has completed: a plugin notification must not block the purchase.
            logger.exception(
                "Service activation notification failed for order %s, product %s, service %s",
                order.get("id"),
                product.get("id"),
                reference.get("id") if isinstance(reference, dict) else None,
            )


def process_product_notification(order, contract, type_):
    # Purchased-service dispatch is integrated in its own lifecycle step.
    pass


def on_product_suspended(order, contract):
    process_product_notification(order, contract, "suspend")


def on_usage_refreshed(order, contract):
    process_product_notification(order, contract, "usage")


def _on_specification_validation(func, plugin_type, loader):
    @wraps(func)
    def wrapper(self, provider, specification):
        plugin = loader(specification)
        if plugin is None:
            return

        getattr(plugin, "on_pre_" + plugin_type + "_spec_validation")(provider, specification)
        result = func(self, provider, specification, plugin._model)
        getattr(plugin, "on_post_" + plugin_type + "_spec_validation")(provider, specification)
        return result

    return wrapper


def on_service_spec_validation(func):
    return _on_specification_validation(
        func, "service", lambda specification: load_plugin_module(service_spec=specification)
    )


def on_resource_spec_validation(func):
    return _on_specification_validation(
        func, "resource", lambda specification: load_resource_plugin_module(resource_spec=specification)
    )
