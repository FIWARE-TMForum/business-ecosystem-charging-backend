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
from importlib import import_module


class PaymentClient:
    NAME = "default"
    END_PAYMENT_PARAMS = []
    _purchase = None

    @staticmethod
    def get_payment_client_class(client = None):
        cln_str = settings.CLIENTS[client] if client is not None else settings.PAYMENT_CLIENT
        client_package, client_class = cln_str.rsplit(".", 1)
        return getattr(import_module(client_package), client_class)

    def __init__(self, purchase):
        self._purchase = purchase

    def start_redirection_payment(self, transactions):
        pass

    def end_redirection_payment(self, **kwargs):
        pass

    def direct_payment(self, currency, price, credit_card):
        pass

    def refund(self):
        pass

    def get_checkout_url(self):
        pass

    def check_payment_status(self, payment_reference):
        pass

    def charge_recurring(self, payment_reference, amount, currency):
        pass


class PaymentClientError(Exception):
    """
    An error to raise when a request to the payment client fails or there's an
    unexpeced error outside the marketplaces control.
    """

    def __init__(self, client, msg):
        self.client = client
        self.value = msg

    def __str__(self):
        return f"PaymentClientError: An error has ocurred with {self.client}. Operation cannot be completed. {self.value}"
