from wstore.charging_engine.payment_client.payment_client import PaymentClient
from wstore.ordering.errors import PaymentError
from django.conf import settings

import os
import requests
from decimal import Decimal
from logging import getLogger

logger = getLogger("wstore.default_logger")

DPAS_CLIENT_API_URL = os.environ.get("BAE_CB_DPAS_CLIENT_API_URL", "https://dpas-sbx.egroup.hu/api/payment-start")

class DpasClient(PaymentClient):
    _checkout_url = None

    def __init__(self, order):
        self._order = order
        self.api_url = DPAS_CLIENT_API_URL 

    def start_redirection_payment(self, transactions):
        payment_items = []
        for t in transactions:
            payment_item = {
                "productProviderId": "1", #
                "amount": float(t['price']),
                "currency": t['currency'],
                "productProviderSpecificData": {}
            }
            if "recurring" in t['related_model']:
                payment_item.update({"recurring": True})
            else:
                payment_item.update({"recurring": False})

            payment_items.append(payment_item)

        redirect_uri = settings.SITE
        if redirect_uri[-1] != "/":
            redirect_uri += "/"

        redirect_uri += "checkout?client=dpas"
        success_url = redirect_uri + "&action=accept&ref=" + str(self._order.pk)
        cancel_url = redirect_uri + "&action=cancel&ref=" + str(self._order.pk)

        payload = {
            "baseAttributes": {
                "externalId": str(self._order.order_id),
                "customerId": str(self._order.customer_id),
                "customerOrganizationId": str(self._order.owner_organization_id),
                "invoiceId": "invoice id", #
                "paymentItems": payment_items
            },
            "processSuccessUrl": success_url,
            "processErrorUrl": cancel_url,
            "responseUrlJwtQueryName": "jwt"
        }

        headers = {
            "Authorization": "Bearer " + self._order.customer.userprofile.access_token
        }

        try:
            response = requests.post(self.api_url, json=payload, headers=headers)
            self._checkout_url = response.json()["redirectUrl"]
            return self._checkout_url
        except requests.RequestException as e:
            logger.debug(f"Error contacting payment API: {e}")

    def end_redirection_payment(self, **kwargs):
        return []

    def refund(self, sale_id):
        pass

    def get_checkout_url(self):
        return self._checkout_url
