# -*- encoding: utf-8 -*-

# Copyright (c) 2023 ficodes

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


import hashlib
import hmac
import os

# import random
# import string

import stripe
from django.conf import settings
from logging import getLogger
from decimal import Decimal

from wstore.charging_engine.payment_client.payment_client import PaymentClient, PaymentClientError
from wstore.ordering.errors import PaymentError
from wstore.ordering.models import Offering, PaymentRecord


logger = getLogger("wstore.default_logger")

MODE = "sandbox"  # sandbox or live

stripe.api_key = os.environ.get(
    "BAE_CB_STRIPE_API_KEY", "sk_test_CGGvfNiIPwLXiDwaOfZ3oX6Y"  # PUBLIC SAMPLE API KEY DO NOT USE!!!
)
if _test_api_base := os.environ.get("BAE_CB_STRIPE_TEST_API_BASE"):
    stripe.api_base = _test_api_base


class StripeClient(PaymentClient):
    NAME = "stripe"
    END_PAYMENT_PARAMS = ("session_id",)

    _purchase = None
    _checkout_url = None

    def __init__(self, order):
        """Creates a new Stripe Payment Client

        Args:
            order (ordering.models.Order): the order to pay.
        """
        self._order = order

    def start_redirection_payment(self, transactions):
        """Start the payment process and produces a url to the stripe payment gateway.

        Args:
            transactions (list): a list of the transactions to bundle in a payment
        """
        logger.debug(f"Starting redirection payment to Stripe for order {self._order}")

        # Build URL
        url = settings.SITE
        if url[-1] != "/":
            url += "/"

        accept_param = f"client=stripe&action=accept&ref={self._order.order_id}"
        cancel_param = f"client=stripe&action=cancel&ref={self._order.order_id}"

        success_sig = hmac.new(self._order.hash_key, accept_param.encode() , hashlib.sha256).hexdigest()
        cancel_sig = hmac.new(self._order.hash_key, cancel_param.encode() , hashlib.sha256).hexdigest()
        logger.debug("success signature:" + success_sig) # It is supposed that in production debug() method will not print in the logs.
        logger.debug("cancel signature:" + cancel_sig) # It is supposed that in production debug() method will not print in the logs.

        url += "checkout?session_id={CHECKOUT_SESSION_ID}&"
        return_url = url + accept_param + f"&sig={success_sig}"
        cancel_url = url + cancel_param + f"&sig={cancel_sig}"

        products = {contract.item_id: Offering.objects.get(off_id=contract.offering) for contract in self._order.contracts}

        # Build payment object
        has_recurring = False
        line_items = []
        for t in transactions:
            if t.get("recurring"):
                has_recurring = True
            line_items.append({
                "quantity": 1,
                "metadata": {"paymentItemExternalId": t["billId"]},
                "price_data": {
                    "currency": t["currency"],
                    "unit_amount": int(Decimal(t["price"]) * Decimal(100)),
                    "product_data": {
                        "name": products[t["item"]].name,
                        "description": products[t["item"]].description or "No description",
                    },
                },
            })

        try:
            logger.debug(f"Creating checkout session for order {self._order.order_id}")
            checkout = stripe.checkout.Session.create(
                success_url=return_url,
                cancel_url=cancel_url,
                client_reference_id=str(self._order.order_id),
                mode="payment",
                **({"customer_creation": "always", "payment_intent_data": {"setup_future_usage": "off_session"}} if has_recurring else {}),
                line_items=line_items,
            )

        # Check for errors in session
        except Exception as e:  # TODO: Narrow exceptions caught
            logger.error(e)
            raise PaymentClientError(self.NAME, "The checkout session cannot be created.") from e

        # Extract URL where redirecting the customer
        self._checkout_url = checkout.url
        logger.info("PAYMENT URL: %s", self._checkout_url)
        return checkout.url

    def direct_payment(self, currency, price, credit_card):
        pass

    def end_redirection_payment(self, **kwargs):
        """Finalizes the payment process

        Keyword Args:
            session_id: The checkout session id
        """
        session_id = kwargs["session_id"]
        logger.debug(f"Stripe payment for order {self._order.order_id} completed")

        session = stripe.checkout.Session.retrieve(session_id)

        if self._order.order_id != session.client_reference_id:
            raise PaymentError('Stripe redirection was manipulated')

        state = "processed" if session.payment_status == "paid" else "pending"

        payout_list = []
        page = stripe.checkout.Session.list_line_items(session_id, limit=100)
        while True:
            for item in page.data:
                cb_id = item.metadata.get("paymentItemExternalId")
                payout_list.append({
                    "paymentItemExternalId": cb_id,
                    "state": state,
                })
                PaymentRecord.create(cb_id, payment_type=self.NAME, payment_reference=session_id)
            if not page.has_more:
                break
            page = stripe.checkout.Session.list_line_items(session_id, limit=100, starting_after=page.data[-1].id)

        return [session_id], payout_list

    def refund(self, session_id):
        try:
            checkout = stripe.checkout.Session.retrieve(session_id)
            refund = stripe.Refund.create(payment_intent=checkout.payment_intent)
            logger.debug(f"Refunding Stripe payment for checkout {session_id}")
            return refund

        except Exception as e:
            logger.error(f"Couldn't refund Stripe payment for checkout {session_id}")
            raise PaymentClientError(self.NAME, "The refund cannot be completed") from e

    def get_checkout_url(self):
        return self._checkout_url

    def check_payment_status(self, payment_reference):
        if payment_reference.startswith('pi_'):
            pi = stripe.PaymentIntent.retrieve(payment_reference)
            if pi.status == 'succeeded':
                return 'succeeded'
            if pi.status in ('processing', 'requires_action', 'requires_confirmation'):
                return 'pending'
            return 'failed'

        session = stripe.checkout.Session.retrieve(payment_reference)
        if session.payment_status == 'paid':
            return 'succeeded'
        if session.payment_status == 'unpaid':
            return 'pending'
        return 'failed'

    def charge_recurring(self, payment_reference, amount, currency):
        try:
            if payment_reference.startswith('pi_'):
                pi = stripe.PaymentIntent.retrieve(payment_reference)
                customer_id = pi.customer
                payment_method = pi.payment_method
            else:
                session = stripe.checkout.Session.retrieve(payment_reference)
                customer_id = session.customer
                pi = stripe.PaymentIntent.retrieve(session.payment_intent)
                payment_method = pi.payment_method

            if not customer_id or not payment_method:
                logger.error(f"Missing customer or payment method for reference {payment_reference}")
                return None, 'failed'

            new_pi = stripe.PaymentIntent.create(
                amount=int(Decimal(str(amount)) * 100),
                currency=currency.lower(),
                customer=customer_id,
                payment_method=payment_method,
                off_session=True,
                confirm=True,
            )

            if new_pi.status == 'succeeded':
                return new_pi.id, 'succeeded'
            if new_pi.status in ('processing', 'requires_action'):
                return new_pi.id, 'pending'
            return new_pi.id, 'failed'

        except stripe.error.CardError as e:
            logger.error(f"Card error during recurring charge for {payment_reference}: {e}")
            return None, 'failed'
        except Exception as e:
            logger.error(f"Error during recurring charge for {payment_reference}: {e}")
            return None, 'failed'

    def batch_payout(self, payouts):
        # TODO: Translate to Stripe API.
        pass
        # sender_batch_id = "".join(random.choice(string.ascii_uppercase) for i in range(12))
        # payout = paypalrestsdk.Payout(
        #     {
        #         "sender_batch_header": {
        #             "sender_batch_id": sender_batch_id,
        #             "email_subject": "You have a payment",
        #         },
        #         "items": payouts,
        #     }
        # )
        #
        # return payout, payout.create()
