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

from wstore.rss_adaptor.rss_manager import RSSManager

logger = getLogger("wstore.default_logger")


class ModelManager(RSSManager):
    def create_revenue_model(self, model_info):
        """
        Creates a revenue sharing model in the Revenue Sharing and
        Settlement system
        """
        self._manage_rs_model(model_info, "POST")

    def update_revenue_model(self, model_info):
        """
        Updates a revenue sharing model in the Revenue Sharing and
        Settlement system
        """
        self._manage_rs_model(model_info, "PUT")

    def _check_model_value(self, field, model_info):
        if field not in model_info:
            raise ValueError(f"Missing a required field in model info: `{field}`")

        try:
            float(model_info[field])
        except:
            raise TypeError(f"Invalid type for `{field}` field")

        if model_info[field] < 0 or model_info[field] > 100:
            raise ValueError(f"`{field}` must be a number between 0 and 100")

    def _check_string_value(self, field, model_info):
        if field not in model_info:
            raise ValueError(f"Missing a required field in model info: `{field}`")

        if not isinstance(model_info[field], str) and not isinstance(model_info[field], str):
            raise TypeError(f"Invalid type for `{field}` field")

    def _manage_rs_model(self, model_info, method):
        self._check_model_value("ownerValue", model_info)
        self._check_model_value("aggregatorValue", model_info)
        self._check_string_value("ownerProviderId", model_info)
        self._check_string_value("productClass", model_info)

        # Validate RS model
        model_info["aggregatorId"] = settings.WSTOREMAIL
        model_info["aggregatorValue"] = str(model_info["aggregatorValue"])
        model_info["ownerValue"] = str(model_info["ownerValue"])
        model_info["algorithmType"] = "FIXED_PERCENTAGE"

        if "stakeholders" not in model_info:
            model_info["stakeholders"] = []

        endpoint = settings.RSS + "rss/models"

        self._make_request(method, endpoint, model_info)
