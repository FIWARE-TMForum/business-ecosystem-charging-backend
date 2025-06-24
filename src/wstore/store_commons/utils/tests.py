# -*- coding: utf-8 -*-

# Copyright (c) 2017 CoNWeT Lab., Universidad Politécnica de Madrid

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
from django.test import TestCase
from django.test.utils import override_settings
from parameterized import parameterized

from wstore.store_commons.utils.units import ChargePeriod, CurrencyCode


@override_settings(
    CHARGE_PERIODS={
        "daily": 1,
    },
)
class ChargePeriodUnitsTestCase(TestCase):
    tags = ("units",)

    def setUp(self):
        self.valid = {
            "title": "daily",
            "value": 1,
        }
        self.not_valid = {
            "title": "weekly",
            "value": 7,
        }

    def _get_title(self, valid, uppercase):
        title = self.valid["title"] if valid else self.not_valid["title"]
        return title.upper() if uppercase else title.lower()

    @parameterized.expand(
        [
            ("valid_in_lowercase", True, False, True),
            ("valid_in_uppercase", True, True, True),
            ("not_valid", False, False, False),
        ]
    )
    def test_should_check_if_given_title_exists(self, name, valid, uppercase, expected):
        title = self._get_title(valid, uppercase)
        self.assertEqual(ChargePeriod.contains(title), expected)

    @parameterized.expand(
        [
            ("valid_in_lowercase", True, False),
            ("valid_in_uppercase", True, True),
            ("not_valid", False, False),
        ]
    )
    def test_should_get_value_of_given_title(self, name, valid, uppercase):
        title = self._get_title(valid, uppercase)
        expected = self.valid["value"] if valid else None
        self.assertEqual(ChargePeriod.get_value(title), expected)

    def test_should_parse_to_json(self):
        dict_expected = [
            self.valid,
        ]
        self.assertEqual(ChargePeriod.to_json(), dict_expected)


@override_settings(
    CURRENCY_CODES=[
        ("EUR", "Euro"),
    ],
)
class CurrencyCodeUnitsTestCase(TestCase):
    tags = ("units",)

    def setUp(self):
        self.valid = {
            "title": "Euro",
            "value": "EUR",
        }
        self.not_valid = {
            "title": "Canada Dollar",
            "value": "CAD",
        }

    def _get_value(self, valid, uppercase):
        value = self.valid["value"] if valid else self.not_valid["value"]
        return value.upper() if uppercase else value.lower()

    @parameterized.expand(
        [
            ("valid_in_lowercase", True, False, True),
            ("valid_in_uppercase", True, True, True),
            ("not_valid", False, False, False),
        ]
    )
    def test_should_check_if_given_value_exists(self, name, valid, uppercase, expected):
        value = self._get_value(valid, uppercase)
        self.assertEqual(CurrencyCode.contains(value), expected)

    def test_should_parse_to_json(self):
        dict_expected = [
            self.valid,
        ]
        self.assertEqual(CurrencyCode.to_json(), dict_expected)



class URLTestCase(TestCase):
    tags = ("url",)

    @parameterized.expand(
        [
            ("catalog", "http://example.com", "/api/catalog", "http://example.com/api/catalog"),
            ("catalog", "https://example.com/", "/api/catalog", "https://example.com/api/catalog"),
            ("catalog", "https://example.com:8000", "/api/catalog", "https://example.com:8000/api/catalog"),
            ("catalog", "https://example.com:8000/", "/api/catalog", "https://example.com:8000/api/catalog"),
            ("catalog", "https://example.com:8000", "api/catalog", "https://example.com:8000/api/catalog"),
            ("catalog", "https://example.com:8000/tmf/v4", "api/catalog", "https://example.com:8000/tmf/v4/api/catalog"),
            ("catalog", "https://example.com:8000/tmf/v4/", "api/catalog", "https://example.com:8000/tmf/v4/api/catalog"),
            ("catalog", "https://example.com:8000/tmf/v4/", "/api/catalog", "https://example.com:8000/tmf/v4/api/catalog"),
        ]
    )
    def test_get_service_url(self, name, base_url, path, expected):
        import wstore.store_commons.utils.url
        wstore.store_commons.utils.url.settings.CATALOG = base_url

        result = wstore.store_commons.utils.url.get_service_url('catalog', path)

        self.assertEqual(result, expected)
