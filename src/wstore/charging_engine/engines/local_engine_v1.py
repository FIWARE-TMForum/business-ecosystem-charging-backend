# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

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



import threading
from datetime import datetime, timedelta
from logging import getLogger

from bson import ObjectId

from wstore.admin.users.notification_handler import NotificationsHandler
from wstore.charging_engine.accounting.sdr_manager import SDRManager
from wstore.charging_engine.accounting.usage_client import UsageClient
from wstore.charging_engine.charging.billing_client import BillingClient
from wstore.rss.cdr_manager import CDRManager
from wstore.charging_engine.invoice_builder import InvoiceBuilder
from wstore.charging_engine.price_resolver import PriceResolver
from wstore.charging_engine.payment_client.payment_client import PaymentClient
from wstore.ordering.errors import OrderingError
from wstore.ordering.models import Charge, Offering, Order
from wstore.ordering.ordering_client import OrderingClient
from wstore.store_commons.database import get_database_connection
from wstore.store_commons.utils.units import ChargePeriod

logger = getLogger("wstore.default_logger")


class LocalEngineV1:
    def __init__(self, order):
        self._order = order
        self._price_resolver = PriceResolver()
        self.charging_processors = {
            "initial": self._process_initial_charge,
            "recurring": self._process_renovation_charge,
            "usage": self._process_use_charge,
        }
        self.end_processors = {
            "initial": self._end_initial_charge,
            "recurring": self._end_renovation_charge,
            "usage": self._end_use_charge,
        }

    def _initial_charge_timeout(self, order):
        ordering_client = OrderingClient()
        raw_order = ordering_client.get_order(order.order_id)

        # Setting all the items as Failed, set the whole order as failed
        # ordering_client.update_state(raw_order, 'Failed')
        ordering_client.update_items_state(raw_order, "Failed")

        logger.info(f"Initial charge timed out. Order {order.order_id} failed")
        order.delete()

    def _renew_charge_timeout(self, order):
        order.state = "paid"
        order.pending_payment = None

        logger.info(f"Renew charge timed out. Order {order.order_id} paid")
        order.save()

    def _timeout_handler(self):
        db = get_database_connection()

        # Uses an atomic operation to get and set the _lock value in the purchase
        # document
        pre_value = db.wstore_order.find_one_and_update({"_id": self._order.pk}, {"$set": {"_lock": True}})

        # If _lock not exists or is set to false means that this function has
        # acquired the resource
        if "_lock" not in pre_value or not pre_value["_lock"]:
            # Only rollback if the state is pending
            if pre_value["state"] == "pending":
                order = Order.objects.get(pk=self._order.pk)
                timeout_processors = {
                    "initial": self._initial_charge_timeout,
                    "recurring": self._renew_charge_timeout,
                    "usage": self._renew_charge_timeout,
                }
                timeout_processors[self._concept](order)

            db.wstore_order.find_one_and_update({"_id": self._order.pk}, {"$set": {"_lock": False}})

    def _charge_client(self, transactions):
        logger.info("Starting charging process")

        # Load payment client
        payment_client = PaymentClient.get_payment_client_class()

        # build the payment client
        client = payment_client(self._order)

        client.start_redirection_payment(transactions)
        checkout_url = client.get_checkout_url()

        # Set timeout for PayPal transaction to 5 minutes
        t = threading.Timer(300, self._timeout_handler)
        t.start()
        logger.debug(f"Timer for {payment_client.__name__} transaction started")

        return checkout_url

    def _calculate_renovation_date(self, unit):
        return datetime.utcnow() + timedelta(days=ChargePeriod.get_value(unit))

    def _end_initial_charge(self, contract, transaction):
        # If a subscription part has been charged update renovation date
        logger.debug("Finishing INITIAL charge process")

        related_model = transaction["related_model"]
        valid_to = None
        if "subscription" in related_model:
            updated_subscriptions = []

            logger.debug("Updating subscriptions")

            for subs in contract.pricing_model["subscription"]:
                up_sub = subs
                # Calculate renovation date
                valid_to = self._calculate_renovation_date(subs["unit"])
                up_sub["renovation_date"] = valid_to
                updated_subscriptions.append(up_sub)

            contract.pricing_model["subscription"] = updated_subscriptions
            related_model["subscription"] = updated_subscriptions

        # Save offerings in org profile
        self._order.owner_organization.acquired_offerings.append(contract.offering)
        self._order.owner_organization.save()

        return None, valid_to

    def _end_renovation_charge(self, contract, transaction):
        related_model = transaction["related_model"]
        # Process contract subscriptions

        logger.debug("Finishing RENOVATION charge process")
        logger.debug("Updating subscriptions")
        valid_to = None
        for subs in related_model["subscription"]:
            valid_to = self._calculate_renovation_date(subs["unit"])
            subs["renovation_date"] = valid_to
            updated_subscriptions = related_model["subscription"]

            if "unmodified" in related_model:
                updated_subscriptions.extend(related_model["unmodified"])

            # Save pricing model with new renovation dates
            contract.pricing_model["subscription"] = updated_subscriptions
            related_model["subscription"] = updated_subscriptions

        return None, valid_to

    def _end_use_charge(self, contract, transaction):
        # Change applied usage documents SDR Guided to Rated
        usage_client = UsageClient()

        logger.debug("Finishing USE charge process")

        for sdr_info in transaction["applied_accounting"]:
            for sdr in sdr_info["accounting"]:
                usage_client.rate_usage(
                    sdr["usage_id"],
                    str(contract.last_charge),
                    sdr["duty_free"],
                    sdr["price"],
                    sdr_info["model"]["tax_rate"],
                    transaction["currency"],
                    contract.product_id,
                )

        transaction["related_model"]["accounting"] = transaction["applied_accounting"]

        return (
            contract.charges[-1].date if len(contract.charges) > 0 else self._order.date,
            None,
        )

    def _send_notification(self, concept, transactions):
        # TODO: Improve the rollback in case of unexpected exception
        try:
            # Send notifications if required
            logger.info("Sending notification")
            handler = NotificationsHandler()
            if concept == "initial":
                # Send customer and provider notifications
                handler.send_acquired_notification(self._order)
                for cont in self._order.get_contracts():
                    handler.send_provider_notification(self._order, cont)

            elif concept == "recurring" or concept == "usage":
                handler.send_renovation_notification(self._order, transactions)
        except:
            pass

    def end_charging(self, transactions, free_contracts, concept):
        """
        Process the second step of a payment once the customer has approved the charge
        :param transactions: List of transactions applied including the total price and the related model
        :param concept: Concept of the charge, it can be initial, renovation, or use
        """
        logger.info("Finishing charging process")

        # Update purchase state
        if self._order.state == "pending":
            self._order.state = "paid"
            self._order.save()

        time_stamp = datetime.utcnow()

        self._order.pending_payment = None

        invoice_builder = InvoiceBuilder(self._order)
        billing_client = BillingClient() if concept != "initial" else None

        updated_contracts = {}
        for transaction in transactions:
            logger.debug(f"Updating contract for {transaction['item']}")
            contract = self._order.get_item_contract(transaction["item"])
            contract.last_charge = time_stamp

            valid_from, valid_to = self.end_processors[concept](contract, transaction)

            # If the customer has been charged create the CDR
            # cdr_manager = CDRManager(self._order, contract)
            # cdr_manager.generate_cdr(transaction["related_model"], time_stamp.isoformat() + "Z")

            # Generate the invoice
            invoice_path = ""
            try:
                invoice_path = invoice_builder.generate_invoice(contract, transaction, concept)
            except:
                pass

            # Update contracts
            charge = Charge(
                date=time_stamp,
                cost=transaction["price"],
                duty_free=transaction["duty_free"],
                currency=transaction["currency"],
                concept=concept,
                invoice=invoice_path,
            )
            if contract.charges is None:
                contract.charges = []

            contract.charges.append(charge)
            updated_contracts[transaction["item"]] = contract

            # Send the charge to the billing API to allow user accesses
            if concept != "initial":
                # When the change concept is initial, the product has not been yet created in the inventory
                billing_client.create_charge(
                    charge,
                    contract.product_id,
                    start_date=valid_from,
                    end_date=valid_to,
                )
                pass

        for free in free_contracts:
            logger.debug(f"Setting {free.offering} as acquired")
            self._order.owner_organization.acquired_offerings.append(free.offering)

        # Update order contracts
        new_contracts = []
        for cont in self._order.get_contracts():
            logger.debug(f"Updating order contract {cont.item_id}")
            if cont.item_id not in updated_contracts:
                new_contracts.append(cont)
            else:
                new_contracts.append(updated_contracts[cont.item_id])

        self._order.contracts = new_contracts
        self._order.owner_organization.save()
        self._order.save()

        self._send_notification(concept, transactions)
        logger.info("Finished charging process OK")

    def _save_pending_charge(self, transactions, free_contracts=[]):
        pending_payment = {  # Payment model
            "transactions": transactions,
            "concept": self._concept,
            "free_contracts": free_contracts,
        }

        self._order.pending_payment = pending_payment
        self._order.save()
        logger.debug(f"Saved pending charge for order: {self._order.order_id}")

    def _append_transaction(self, transactions, contract, related_model, accounting=None):
        # Call the price resolver
        price, duty_free = self._price_resolver.resolve_price(related_model, accounting)

        if "alteration" in related_model and not self._price_resolver.is_altered():
            del related_model["alteration"]

        offering = Offering.objects.get(pk=ObjectId(contract.offering))
        transaction = {
            "price": price,
            "duty_free": duty_free,
            "description": offering.description,
            "currency": contract.pricing_model["general_currency"],
            "related_model": related_model,
            "item": contract.item_id,
        }

        # Get the applied accounting info is needed
        if accounting is not None:
            transaction["applied_accounting"] = self._price_resolver.get_applied_sdr()

        logger.debug(f"Transaction for item {transaction['item']} appended")
        transactions.append(transaction)

    def _process_initial_charge(self, contracts):
        """
        Resolves initial charges, which can include single payments or the initial payment of a subscription
        :return: The URL where redirecting the customer to approve the charge
        """

        transactions = []
        free_contracts = []
        redirect_url = None

        logger.info(f"Resolving initial charges for order {self._order.order_id}")

        for contract in contracts:
            logger.debug(f"Processing contract {contract.item_id}")
            related_model = {}
            # Check if there are price parts different from pay per use
            if "single_payment" in contract.pricing_model:
                related_model["single_payment"] = contract.pricing_model["single_payment"]

            if "subscription" in contract.pricing_model:
                related_model["subscription"] = contract.pricing_model["subscription"]

            if "alteration" in contract.pricing_model:
                related_model["alteration"] = contract.pricing_model["alteration"]

            if len(related_model):
                self._append_transaction(transactions, contract, related_model)
            else:
                free_contracts.append(contract)

        if len(transactions):
            logger.debug(f"Appended a total of {len(transactions)} transactions to order {self._order.order_id}")
            # Make the charge
            redirect_url = self._charge_client(transactions)
            self._save_pending_charge(transactions, free_contracts=free_contracts)
        else:
            # If it is not necessary to charge the customer, the state is set to paid
            logger.debug(f"No initial charges for order {self._order.order_id}")
            self._order.state = "paid"
            self.end_charging(transactions, free_contracts, self._concept)

        logger.info(f"URL for initial charge: {redirect_url}")
        return redirect_url

    def _execute_renovation_transactions(self, transactions, err_msg):
        if len(transactions):
            # Make the charge
            redirect_url = self._charge_client(transactions)
            self._save_pending_charge(transactions)
            logger.info(f"URL for renovation charge: {redirect_url}")
        else:
            # If it is not necessary to charge the customer, the state is set to paid
            self._order.state = "paid"
            self._order.save()
            logger.error(f"Not necessary to charge the customer (no transactions) for order {self._order.order_id}")
            raise OrderingError(err_msg)

        return redirect_url

    def _process_renovation_charge(self, contracts):
        """
        Resolves renovation charges, which includes the renovation of subscriptions and optionally usage payments
        :return: The URL where redirecting the customer to approve the charge
        """

        self._order.state = "pending"
        logger.info(f"Resolving renovation charges for order {self._order.order_id}")

        now = datetime.utcnow()
        transactions = []
        for contract in contracts:
            logger.debug(f"Appending transactions for contract {contract.item_id}")
            # Check if the contract has any recurring model
            if "subscription" not in contract.pricing_model:
                continue

            # Determine the price parts to renovate
            related_model = {"subscription": []}

            unmodified = []
            for s in contract.pricing_model["subscription"]:
                renovation_date = s["renovation_date"]
                if renovation_date < now:
                    related_model["subscription"].append(s)
                else:
                    unmodified.append(s)

            # Save unmodified recurring payment (not ended yed)
            if len(unmodified):
                related_model["unmodified"] = unmodified

            if (
                "alteration" in contract.pricing_model
                and contract.pricing_model["alteration"].get("period") == "recurring"
            ):
                related_model["alteration"] = contract.pricing_model["alteration"]

            # Calculate the price to be charged if required
            if len(related_model["subscription"]):
                self._append_transaction(transactions, contract, related_model)

        return self._execute_renovation_transactions(transactions, "There is not recurring payments to renovate")

    def _parse_raw_accounting(self, usage):
        sdr_manager = SDRManager()
        sdrs = []

        for usage_document in usage:
            sdr_values = sdr_manager.get_sdr_values(usage_document)
            sdr_values.update({"usage_id": usage_document["id"]})
            sdrs.append(sdr_values)

        return sdrs

    def _process_use_charge(self, contracts):
        """
        Resolves usage charges, which includes pay-per-use payments
        :return: The URL where redirecting the customer to approve the charge
        """
        self._order.state = "pending"
        logger.info(f"Resolving usage charges for order {self._order.order_id}")

        transactions = []
        usage_client = UsageClient()
        for contract in contracts:
            logger.debug(f"Appending transactions for contract {contract.item_id}")
            if "pay_per_use" not in contract.pricing_model:
                continue

            related_model = {"pay_per_use": contract.pricing_model["pay_per_use"]}

            accounting = self._parse_raw_accounting(
                usage_client.get_customer_usage(
                    self._order.owner_organization.name,
                    contract.product_id,
                    state="Guided",
                )
            )

            if (
                "alteration" in contract.pricing_model
                and contract.pricing_model["alteration"].get("period") == "recurring"
            ):
                related_model["alteration"] = contract.pricing_model["alteration"]

            if len(accounting) > 0:
                self._append_transaction(transactions, contract, related_model, accounting=accounting)

        return self._execute_renovation_transactions(transactions, "There is not usage payments to renovate")

    def resolve_charging(self, type_="initial", related_contracts=None):
        """
        Calculates the charge of a customer depending on the pricing model and the type of charge.
        :param type_: Type of charge, it defines if it is an initial charge, a renovation or a usage based charge
        :param related_contracts: optional field that can be used to specify a set of contracts to be processed.
        If None all the contracts in the order are processed
        :return: The URL where redirecting the user to be charged (PayPal)
        """

        self._concept = type_

        if type_ not in self.charging_processors:
            logger.error("Invalid charge type, must be `initial`, `recurring`, or `usage`")
            raise ValueError("Invalid charge type, must be `initial`, `recurring`, or `usage`")

        if related_contracts is None:
            related_contracts = self._order.get_contracts()

        logger.info(f"Resolving charging of type {type_} for order {self._order}")
        return self.charging_processors[type_](related_contracts)
