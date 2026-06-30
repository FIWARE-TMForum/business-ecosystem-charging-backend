# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid

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


from datetime import datetime

from django.test import TestCase
from mock import MagicMock
from parameterized import parameterized

from wstore.charging_engine.charging import billing_client

TIMESTAMP = datetime(2016, 6, 21, 10, 0, 0)
RENEW_DATE = datetime(2016, 7, 21, 10, 0, 0)
START_DATE = datetime(2016, 5, 21, 10, 0, 0)

COMMON_CHARGE = {
    "date": TIMESTAMP.isoformat() + "Z",
    "currencyCode": "EUR",
    "taxIncludedAmount": "10",
    "taxExcludedAmount": "8",
    "appliedCustomerBillingTaxRate": [{"amount": "20", "taxCategory": "VAT"}],
    "serviceId": [{"id": "1", "type": "Inventory product"}],
}

BASIC_CHARGE = {
    "description": "initial charge of 10 EUR http://extpath.com:8080/charging/media/bills/bill1.pdf",
    "type": "initial",
}
BASIC_CHARGE.update(COMMON_CHARGE)

RECURRING_CHARGE = {
    "description": "recurring charge of 10 EUR http://extpath.com:8080/charging/media/bills/bill1.pdf",
    "type": "recurring",
    "period": [
        {
            "startPeriod": TIMESTAMP.isoformat() + "Z",
            "endPeriod": RENEW_DATE.isoformat() + "Z",
        }
    ],
}
RECURRING_CHARGE.update(COMMON_CHARGE)

USAGE_CHARGE = {
    "description": "usage charge of 10 EUR http://extpath.com:8080/charging/media/bills/bill1.pdf",
    "type": "usage",
    "period": [
        {
            "startPeriod": START_DATE.isoformat() + "Z",
            "endPeriod": TIMESTAMP.isoformat() + "Z",
        }
    ],
}
USAGE_CHARGE.update(COMMON_CHARGE)


class BillingClientTestCase(TestCase):
    tags = ("billing",)

    @parameterized.expand(
        [
            ("initial", None, None, BASIC_CHARGE),
            ("recurring", None, RENEW_DATE, RECURRING_CHARGE),
            ("usage", START_DATE, None, USAGE_CHARGE),
        ]
    )
    def test_create_charge(self, name, start_date, end_date, exp_body):
        ## TODO: This API has changed and it is not yet implemented
        pass
        # # Create Mocks
        # billing_client.settings.BILLING = "http://billing.api.com"

        # charge = {}
        # charge["date"] = TIMESTAMP
        # charge["cost"] = "10"
        # charge["duty_free"] = "8"
        # charge["invoice"] = "charging/media/bills/bill1.pdf"
        # charge["currency"] = "EUR"
        # charge["concept"] = name

        # site = "http://extpath.com:8080/"
        # billing_client.settings.SITE = site

        # billing_client.Request = MagicMock()
        # billing_client.Session = MagicMock()
        # session = MagicMock()
        # billing_client.Session.return_value = session

        # preped = MagicMock()
        # preped.headers = {}
        # session.prepare_request.return_value = preped

        # # Call the method to test
        # client = billing_client.BillingClient()
        # client.create_charge(charge, "1", start_date=start_date, end_date=end_date)

        # # Validate calls
        # billing_client.Request.assert_called_once_with(
        #     "POST",
        #     "http://billing.api.com/api/billingManagement/v2/appliedCustomerBillingCharge",
        #     json=exp_body,
        # )

        # billing_client.Session.assert_called_once_with()
        # session.prepare_request.assert_called_once_with(billing_client.Request())

        # self.assertEquals("extpath.com:8080", preped.headers["Host"])

        # session.send.assert_called_once_with(preped)
        # session.send().raise_for_status.assert_called_once_with()


class BillingClientAPITestCase(TestCase):
    tags = ("billing", "billing-api")

    def setUp(self):
        billing_client.requests = MagicMock()
        billing_client.get_service_url = MagicMock(return_value="http://billing.test/api")
        billing_client.settings = MagicMock(VERIFY_REQUESTS=False, BILLING_ENGINE="local",
                                             RELATED_PARTY_SCHEMA_LOCATION="http://schema.test")
        billing_client.normalize_party_ref = MagicMock(side_effect=lambda x: x)
        billing_client.get_operator_party_roles = MagicMock(return_value=[])
        billing_client.to_utc_z = MagicMock(return_value="2026-01-01T00:00:00Z")
        billing_client.utc_z_to_dt = MagicMock(side_effect=lambda s: s)
        self.client = billing_client.BillingClient()

    def test_get_customer_bills_by_state(self):
        expected = [{"id": "cb-1", "state": "new"}]
        billing_client.requests.get.return_value.json.return_value = expected
        result = self.client.get_customer_bills_by_state("new")
        self.assertEqual(result, expected)
        billing_client.requests.get.assert_called_once()

    @parameterized.expand([
        ("found", [{"product": {"id": "prod-1"}}], "prod-1"),
        ("not_found", [], None),
    ])
    def test_get_product_id_by_cb(self, name, acbrs, expected):
        billing_client.requests.get.return_value.json.return_value = acbrs
        self.assertEqual(self.client.get_product_id_by_cb("cb-1"), expected)

    def test_get_acbrs_single_page(self):
        acbrs = [{"id": "acbr-1", "date": "2026-01-01T00:00:00Z"}]
        billing_client.requests.get.return_value.json.return_value = acbrs
        result = self.client.get_acbrs("prod-1", "pop-1")
        self.assertEqual(len(result), 1)

    def test_get_acbrs_paginates(self):
        page1 = [{"id": f"acbr-{i}", "date": f"2026-0{i+1}-01T00:00:00Z"} for i in range(2)]
        page2 = [{"id": "acbr-2", "date": "2026-03-01T00:00:00Z"}]
        billing_client.requests.get.return_value.json.side_effect = [page1, page2]
        result = self.client.get_acbrs("prod-1", "pop-1", limit=2)
        self.assertEqual(len(result), 3)

    def test_create_customer_rate_requires_price_id_on_local_engine(self):
        with self.assertRaises(ValueError):
            self.client.create_customer_rate("name", "desc", "initial", "EUR",
                                             21, "2.10", "12.10", "10.00",
                                             {"id": "ba-1"}, "prod-1")

    def test_create_customer_rate_success(self):
        billing_client.requests.post.return_value.json.return_value = {"id": "acbr-new"}
        result = self.client.create_customer_rate("name", "desc", "initial", "EUR",
                                                  21, "2.10", "12.10", "10.00",
                                                  {"id": "ba-1"}, "prod-1", priceId="pop-1")
        self.assertEqual(result["id"], "acbr-new")
        billing_client.requests.post.assert_called_once()

    def test_set_customer_bill_invalid_state_raises(self):
        with self.assertRaises(ValueError):
            self.client.set_customer_bill("invalid", "cb-1")

    def test_set_customer_bill_success(self):
        self.client.set_customer_bill("settled", "cb-1")
        billing_client.requests.patch.assert_called_once()

    def test_create_customer_bill_empty_acbrs(self):
        self.assertEqual(self.client.create_customer_bill([], {}), {})
        billing_client.requests.post.assert_not_called()

    def test_create_customer_bill_success(self):
        cb_resp = {"id": "cb-1", "taxIncludedAmount": {"value": "10"}, "taxExcludedAmount": {"value": "8"}}
        billing_client.requests.post.return_value.json.return_value = cb_resp
        cb_model = {"taxIncludedAmount": {"unit": "EUR", "value": "10"}, "taxExcludedAmount": {"unit": "EUR", "value": "8"}}
        result = self.client.create_customer_bill([{"id": "acbr-1"}], cb_model, cb_state="new")
        self.assertEqual(result["id"], "cb-1")
