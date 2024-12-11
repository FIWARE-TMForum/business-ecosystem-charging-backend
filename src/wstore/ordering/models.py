# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid
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


from django.contrib.auth.models import User
from djongo import models

from wstore.models import Organization, Resource
from wstore.ordering.errors import OrderingError


class Offering(models.Model):
    _id = models.ObjectIdField()
    off_id = models.CharField(max_length=50, blank=True, null=True)
    href = models.URLField()
    owner_organization = models.ForeignKey(Organization, on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=100)
    description = models.CharField(max_length=1500)
    is_digital = models.BooleanField(default=True)
    asset = models.ManyToManyField(Resource, blank=True)
    is_open = models.BooleanField(default=False)
    is_custom = models.BooleanField(default=False)
    bundled_offerings = models.JSONField(default=[])  # List


class Charge(models.Model):
    concept = models.CharField(
        max_length=100, primary_key=True
    )  # Workarround to prevent issues, not really a primary Key
    date = models.DateTimeField()
    cost = models.CharField(max_length=100)
    duty_free = models.CharField(max_length=100)
    currency = models.CharField(max_length=3)
    invoice = models.CharField(max_length=200)

    class Meta:
        managed = False

    def __getitem__(self, name):
        return getattr(self, name)


class Contract(models.Model):
    item_id = models.CharField(
        max_length=50, primary_key=True
    )  # Workarround to prevent issues, not really a primary Key
    product_id = models.CharField(max_length=50, blank=True, null=True)

    offering = models.CharField(max_length=50)  # Offering.pk as Foreing Key is not working for EmbeddedFields
    # offering = models.ForeignKey(Offering, on_delete=models.DO_NOTHING)

    # Parsed version of the pricing model used to calculate charges
    pricing_model = models.JSONField(default={})  # Dict
    # Date of the last charge to the customer
    last_charge = models.DateTimeField(blank=True, null=True)
    # List with the made charges
    charges = models.ArrayField(model_container=Charge, default=[])

    # Usage fields
    correlation_number = models.IntegerField(default=0)
    last_usage = models.DateTimeField(blank=True, null=True)

    # Revenue sharing product class
    revenue_class = models.CharField(max_length=15, blank=True, null=True)

    suspended = models.BooleanField(default=False)
    terminated = models.BooleanField(default=False)

    class Meta:
        managed = False

    def __getitem__(self, name):
        return getattr(self, name)


class Payment(models.Model):
    concept = models.CharField(
        max_length=20, primary_key=True
    )  # Workarround to prevent issues, not really a primary Key
    transactions = models.JSONField()  # List
    free_contracts = models.ArrayField(model_container=Contract)

    class Meta:
        managed = False

    def __getitem__(self, name):
        return getattr(self, name)


class Order(models.Model):
    _id = models.ObjectIdField()
    description = models.CharField(max_length=1500)
    order_id = models.CharField(max_length=50)
    customer = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    owner_organization = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, null=True, blank=True)
    date = models.DateTimeField()
    sales_ids = models.JSONField(default=[])  # List

    state = models.CharField(max_length=50)
    tax_address = models.JSONField(default={})  # Dict

    # List of contracts attached to the current order
    contracts = models.ArrayField(model_container=Contract)

    # Pending payment info used in asynchronous charges
    pending_payment = models.EmbeddedField(model_container=Payment, null=True)

    objects = models.DjongoManager()

    def _build_contract(self, contract_info):
        return Contract(
            item_id=contract_info["item_id"],
            product_id=contract_info["product_id"],
            offering=contract_info["offering"],
            pricing_model=contract_info["pricing_model"],
            last_charge=contract_info["last_charge"],
            charges=contract_info["charges"],
            correlation_number=contract_info["correlation_number"],
            last_usage=contract_info["last_usage"],
            revenue_class=contract_info["revenue_class"],
            suspended=contract_info["suspended"],
            terminated=contract_info["terminated"],
        )

    def get_contracts(self):
        return [self._build_contract(contract) for contract in self.contracts]

    def get_item_contract(self, item_id):
        # Search related contract
        for c in self.contracts:
            if c["item_id"] == item_id:
                contract = c
                break
        else:
            raise OrderingError("Invalid item id")

        return self._build_contract(contract)

    def get_product_contract(self, product_id):
        # Search related contract
        for c in self.contracts:
            if c["product_id"] == product_id:
                contract = c
                break
        else:
            raise OrderingError("Invalid product id")

        return self._build_contract(contract)

    class Meta:
        app_label = "wstore"
