# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid

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


from django.conf import settings
from logging import getLogger
from decimal import Decimal

from wstore.rss.models import RSSModel


class ModelManager:

    MODEL_FIELDS = {
        "ownerProviderId": str,
        "productClass": str,
        "algorithmType": str,
        "ownerValue": Decimal,
        "aggregatorValue": Decimal,
    }

    def _check_field(self, model_info, field):
        """
        Checks if a field is valid. Only returns if so.

        Args:
            model_info (dict): A dicitionary with the necessary MODEL_FIELDS
            field (str): The field key
        """
        if field not in model_info:
            raise ValueError(f"Missing a required field in model info: `{field}`")

        if not isinstance(model_info[field], self.MODEL_FIELDS[field]):
            raise TypeError(f"Invalid type for `{field}` field")

    def _check_model(self, model_info):
        """
        Checks if the model info is valid.

        Args:
            model_info (dict): A dicitionary with the necessary MODEL_FIELDS
        """
        for field in self.MODEL_FIELDS:
            self._check_field(model_info, field)

    def create_revenue_model(self, model_info):
        """
        Creates a revenue sharing model in the Revenue Sharing and
        Settlement system.

        Args:
            model_info (dict): A dicitionary with the necessary MODEL_FIELDS
        """
        self.check_model(model_info)
        RSSModel(model_info).save()

    def update_revenue_model(self, model_info):
        """
        Updates a revenue sharing model in the Revenue Sharing and
        Settlement system

        Args:
            model_info (dict): A dicitionary with the necessary MODEL_FIELDS
        """
        self.check_model(model_info)
        model = RSSModel.objects.get(owner_provider_id=model_info["ownerProviderId"], product_class=model_info["productClass"])
        model.algorithm_type = model_info["algorithmType"]
        model.owner_value = model_info["ownerValue"]
        model.aggregator_value = model_info["aggregatorValue"]
        model.stakeholders = model_info["stakeholders"]
        model.save()
