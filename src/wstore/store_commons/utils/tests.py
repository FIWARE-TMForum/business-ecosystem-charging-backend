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
from mock import MagicMock, call

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


@override_settings(
    PARTY='http://myparty.com',
)
class PartyTestCase(TestCase):
    tags=("party-utils",)

    def setUp(self):
        from wstore.store_commons.utils import party
        self._party = party

        self._party.cache = MagicMock()
        self._party.cache.get.return_value = None

        return super().setUp()

    def test_get_operator_party_id_cached(self):
        self._party.cache = MagicMock()
        self._party.cache.get.return_value = 'urn:partyid'

        party_id = self._party.get_operator_party_id()

        self.assertEquals('urn:partyid', party_id)
        self._party.cache.get.assert_called_once_with("operator:party_id")

    @override_settings(
        OPERATOR_ID=None,
    )
    def test_get_operator_party_id_none(self):
        party_id = self._party.get_operator_party_id()
        self.assertTrue(party_id is None)

    def _test_get_operator_party_id(self, responses, calls):
        self._party.requests = MagicMock()
        self._party.requests.get.side_effect = responses

        party_id = self._party.get_operator_party_id()

        self.assertEquals('urn:partyid', party_id)
        self.assertEquals(calls, self._party.requests.get.call_args_list)

    @override_settings(
        OPERATOR_ID='VATES-123',
    )
    def test_get_operator_party_id_org_id(self):
        response = MagicMock(status_code=200)
        response.json.return_value = [{
            'id': 'urn:partyid'
        }]

        self._test_get_operator_party_id([response], [
            call('http://myparty.com/organization?organizationIdentification.identificationId=did:elsi:VATES-123')
        ])

    @override_settings(
        OPERATOR_ID='VATES-123',
    )
    def test_get_operator_party_id_ext_ref(self):
        response1 = MagicMock(status_code=200)
        response1.json.return_value = []

        response = MagicMock(status_code=200)
        response.json.return_value = [{
            'id': 'urn:partyid'
        }]

        self._test_get_operator_party_id([response1, response], [
            call('http://myparty.com/organization?organizationIdentification.identificationId=did:elsi:VATES-123'),
            call('http://myparty.com/organization?externalReference.name=did:elsi:VATES-123')
        ])

    @override_settings(
        OPERATOR_ID='VATES-123',
    )
    def test_get_operator_party_id_ext_ref_elsi(self):
        response1 = MagicMock(status_code=200)
        response1.json.return_value = []

        response2 = MagicMock(status_code=200)
        response2.json.return_value = []

        response = MagicMock(status_code=200)
        response.json.return_value = [{
            'id': 'urn:partyid'
        }]

        self._test_get_operator_party_id([response1, response2, response], [
            call('http://myparty.com/organization?organizationIdentification.identificationId=did:elsi:VATES-123'),
            call('http://myparty.com/organization?externalReference.name=did:elsi:VATES-123'),
            call('http://myparty.com/organization?externalReference.name=VATES-123')
        ])

    def test_get_operator_party_roles_none(self):
        self._party.get_operator_party_id = MagicMock(return_value=None)

        roles = self._party.get_operator_party_roles()

        self.assertEquals([], roles)

    @override_settings(
        OPERATOR_ID='VATES-123',
        SELLER_OPERATOR_ROLE='SellerOperator',
        BUYER_OPERATOR_ROLE='BuyerOperator'
    )
    def test_get_operator_party_roles_none(self):
        self._party.get_operator_party_id = MagicMock(return_value='urn:partyId')

        roles = self._party.get_operator_party_roles()

        self.assertEquals([{
            "id": 'urn:partyId',
            "href": 'urn:partyId',
            "name": 'VATES-123',
            "role": 'SellerOperator',
            "@referredType": "Organization"
        }, {
            "id": 'urn:partyId',
            "href": 'urn:partyId',
            "name": 'VATES-123',
            "role": 'BuyerOperator',
            "@referredType": "Organization"
        }], roles)

    def test_normalize_party_ref_cache(self):
        self._party.cache = MagicMock()
        self._party.cache.get.return_value = 'VAT-ext'

        norm = self._party.normalize_party_ref({
            'id': 'urn:organization:partyId',
            'role': 'Seller'
        })

        self.assertEquals({
            'id': 'urn:organization:partyId',
            'href': 'urn:organization:partyId',
            'name': 'VAT-ext',
            'role': 'Seller',
            '@referredType': 'Organization'
        }, norm)

    def test_normalize_party_ref_query(self):
        self._party.cache = MagicMock()
        self._party.cache.get.return_value = None

        response = MagicMock(status_code=200)
        response.json.return_value = {
            'id': 'urn:individual:partyId',
            'externalReference': [{
                'externalReferenceType': 'idm_id',
                'name': 'VAT-ext'
            }]
        }

        self._party.requests = MagicMock()
        self._party.requests.get.return_value = response

        norm = self._party.normalize_party_ref({
            'id': 'urn:individual:partyId',
            'role': 'Seller'
        })

        self.assertEquals({
            'id': 'urn:individual:partyId',
            'href': 'urn:individual:partyId',
            'name': 'VAT-ext',
            'role': 'Seller',
            '@referredType': 'Individual'
        }, norm)

        self.assertEquals([
            call('http://myparty.com/organization/urn:individual:partyId')
        ], self._party.requests.get.call_args_list)