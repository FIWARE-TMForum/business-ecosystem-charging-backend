from wstore.charging_engine.payment_client.payment_client import PaymentClient
from wstore.ordering.errors import PaymentError
from django.conf import settings

import os
import requests
import jwt

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
                "productProviderExternalId": t["provider"], # This is the provider party ID
                "paymentItemExternalId": t["rateId"], # this is the ID of the applied billing rate
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
                "externalId": str(self._order.order_id),  ## Use the raw order ID
                "customerOrganizationId": str(self._order.owner_organization.actor_id), ## Use the organization Party ID
                "invoiceId": "invoice id", #
                "paymentItems": payment_items
            },
            "customerId": str(self._order.customer.userprofile.actor_id), ## Use the user Party ID
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
        token = kwargs.get("jwt", None)

        result = []
        if token is not None:
            decoded = jwt.decode(token, options={"verify_signature": False})
            result.append(decoded['paymentPreAuthorizationId'])

        return result

    def refund(self, sale_id):
        pass

    def get_checkout_url(self):
        return self._checkout_url
