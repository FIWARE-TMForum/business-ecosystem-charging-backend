# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid

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


class OrderingError(Exception):
    def __init__(self, msg):
        self.value = msg

    def __str__(self):
        return "OrderingError: " + self.value

class InventoryError(Exception):
    def __init__(self, msg):
        self.value = msg

    def __str__(self):
        return "InventoryError: " + self.value


class PaymentTimeoutError(Exception):
    def __init__(self, msg):
        self.value = msg

    def __str__(self):
        return "PaymentTimeoutError: " + self.value


class PaymentError(Exception):
    def __init__(self, msg):
        self.value = msg

    def __str__(self):
        return "PaymentError: " + self.value


class PayoutError(Exception):
    def __init__(self, msg):
        super(PayoutError, self).__init__(msg)
        self.value = msg

    def __str__(self):
        return "PayoutError: " + self.value
