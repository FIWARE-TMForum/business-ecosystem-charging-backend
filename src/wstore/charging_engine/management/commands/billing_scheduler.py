# -*- coding: utf-8 -*-

# Copyright (c) 2025 Future Internet Consulting and Development Solutions S.L.

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

import datetime
from decimal import Decimal
from logging import getLogger

from django.core.management.base import BaseCommand

from wstore.charging_engine.accounting.usage_client import UsageClient
from wstore.charging_engine.charging.billing_client import BillingClient
from wstore.charging_engine.engines.local_engine import LocalEngine
from wstore.charging_engine.pricing_engine import PriceEngine
from wstore.charging_engine.utils import to_utc_z, utc_z_to_dt
from wstore.ordering.inventory_client import InventoryClient

logger = getLogger("wstore.default_logger")

RECURRING = "recurring"
RECURRING_PREPAID = "recurring-prepaid"
USAGE = "usage"

BILLABLE_TYPES = [RECURRING, RECURRING_PREPAID, USAGE]


class Command(BaseCommand):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._billing_client = BillingClient()
        self._price_engine = PriceEngine()
        self._usage_client = UsageClient()
        self._inventory_client = InventoryClient()
        self._local_engine = LocalEngine(None)

    def _get_pop_components(self, product_prices):
        components = []
        for price_ref in product_prices:
            pop = self._inventory_client.get_price_component(price_ref["productOfferingPrice"]["id"])
            if not pop.get("isBundle", False):
                components.append(pop)
        return components

    def _get_pops_to_bill(self, product_id, pop_components, now, product_start_date):
        pops_to_bill = {}
        pops_to_process = []
        usage_period = None

        for pop in pop_components:
            pop_id = pop["id"]
            pop_type = pop.get("priceType", "").lower()

            if pop_type not in BILLABLE_TYPES:
                continue

            charge_period = (
                PriceEngine.PERIOD_MONTH
                if pop_type == "usage"
                else f"{pop.get('recurringChargePeriodLength', '')} {pop.get('recurringChargePeriodType', '')}".strip()
            )

            acbrs = self._billing_client.get_acbrs(product_id, pop_id)

            if not acbrs:
                first_period = self._local_engine._build_period_coverage(
                    charge_period, utc_z_to_dt(product_start_date)
                )
                end_str = first_period.get("endDateTime")
                if not end_str or utc_z_to_dt(end_str) > now:
                    continue
                next_period = first_period
            else:
                last_acbr = acbrs[-1]
                end_str = last_acbr.get("periodCoverage", {}).get("endDateTime")
                if not end_str or utc_z_to_dt(end_str) > now:
                    continue
                next_start = utc_z_to_dt(end_str)
                next_period = self._local_engine._build_period_coverage(charge_period, next_start)
                if pop_type in (RECURRING, USAGE):
                    next_end_str = next_period.get("endDateTime")
                    if not next_end_str or utc_z_to_dt(next_end_str) > now:
                        continue

            pops_to_bill[pop_id] = {
                "periodCoverage": next_period,
                "type": pop_type,
            }
            pops_to_process.append(pop)

            if pop_type == "usage":
                usage_period = next_period

        return pops_to_bill, usage_period, pops_to_process

    def _create_acbrs(self, product, prices, pops_to_bill):
        created_acbrs = []
        currency = None
        tax_included_total = Decimal("0")
        duty_free_total = Decimal("0")

        for price in prices:
            price_id = price.get("priceId")
            if price_id not in pops_to_bill:
                continue

            pop_info = pops_to_bill[price_id]
            price_type = price.get("priceType", pop_info["type"]).lower()
            currency = price["price"]["dutyFreeAmount"]["unit"]
            tax_included = price["price"]["taxIncludedAmount"]["value"]
            duty_free = price["price"]["dutyFreeAmount"]["value"]
            tax_rate = price["price"]["taxRate"]
            tax = str((Decimal(str(tax_included)) - Decimal(str(duty_free))).quantize(Decimal("0.01")))

            acbr = self._billing_client.create_customer_rate(
                name=price.get("name", price_type.capitalize() + " charge"),
                description=price.get("description", ""),
                rate_type=price_type,
                currency=currency,
                tax_rate=tax_rate,
                tax=tax,
                tax_included=tax_included,
                tax_excluded=duty_free,
                billing_account=product["billingAccount"],
                product_id=product["id"],
                coverage_period=pop_info["periodCoverage"],
                party=product.get("relatedParty", []),
                priceId=price_id,
            )
            created_acbrs.append(acbr)
            tax_included_total += Decimal(str(tax_included))
            duty_free_total += Decimal(str(duty_free))

        return created_acbrs, currency, tax_included_total, duty_free_total

    def _process_product(self, product, now):
        if not product.get("productPrice"):
            return

        pop_components = self._get_pop_components(product["productPrice"])
        pops_to_bill, usage_period, pops_to_process = self._get_pops_to_bill(product["id"], pop_components, now, product["startDate"])

        if not pops_to_bill:
            return

        usages = []
        if usage_period:
            usages = self._usage_client.get_customer_usage_in_period(
                product["id"],
                usage_period["startDateTime"],
                usage_period["endDateTime"],
            )

        prices = self._price_engine.calculate_prices({
            "productOrderItem": [{
                "itemTotalPrice": [{"productOfferingPrice": {"id": product["productPrice"][0]["productOfferingPrice"]["id"]}}],
                "product": product,
            }]
        }, usage=usages, preview=False, pop_components=pops_to_process)

        created_acbrs, currency, tax_included_total, duty_free_total = self._create_acbrs(product, prices, pops_to_bill)

        if not created_acbrs:
            return

        cb_model = {
            "appliedPayment": [],
            "billDate": to_utc_z(datetime.datetime.now(datetime.timezone.utc)),
            "billingAccount": {"id": product["billingAccount"]["id"], "href": product["billingAccount"]["href"]},
            "taxIncludedAmount": {"unit": currency, "value": float(tax_included_total)},
            "taxExcludedAmount": {"unit": currency, "value": float(duty_free_total)},
            "relatedParty": product.get("relatedParty", []),
        }

        self._billing_client.create_customer_bill(created_acbrs, cb_model, cb_state="new")
        logger.info(f"CustomerBill created for product {product['id']}, {len(created_acbrs)} ACBRs")

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, default=None, help='Override current datetime (ISO 8601) for testing')

    def handle(self, *args, **options):
        # TODO: Create a sync system if during an acbr patch iteration tmf api or some error ocurred.
        if options.get('date'):
            now = utc_z_to_dt(options['date']) if 'T' in options['date'] else datetime.datetime.fromisoformat(options['date']).replace(tzinfo=datetime.timezone.utc)
        else:
            now = datetime.datetime.now(datetime.timezone.utc)
        logger.info(f"Running billing scheduler for {now}")

        offset = 0
        limit = 100

        while True:
            products = self._inventory_client.get_products({"status": "active", "limit": limit, "offset": offset})
            if not products:
                break

            for product in products:
                try:
                    self._process_product(product, now)
                except Exception as e:
                    logger.error(f"Error processing product {product.get('id')}: {e}")

            if len(products) < limit:
                break
            offset += limit

        logger.info("Billing scheduler finished")
