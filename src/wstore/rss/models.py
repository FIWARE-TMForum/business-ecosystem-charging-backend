# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2023 Future Internet Consulting and Development Solutions S.L.

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
"""
This file contains the django models for the Revenue Sharing/Settlement System
(RSS). Model fields are in camelCase, breaking python convention for easier
compatibility and consistency with the API.
"""

from djongo import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from wstore.store_commons.utils.decimal import CustomDecimalField
from wstore.rss.algorithms.rss_algorithm import RSS_ALGORITHMS


class RSSValidators:
    @staticmethod
    def validate_stakeholders(stakeholders):
        stakeholder_ids = {st["stakeholderId"] for st in stakeholders}
        if len(stakeholder_ids) < len(stakeholders):
            raise ValidationError("All stakeholders must be unique.", params={"stakeholders": stakeholders})

    @staticmethod
    def validate_type(type):
        def validator(field):
            if not isinstance(field, type):
                raise ValidationError(f"{field} is not of type {type}")

        return validator

    def validate_algorithm(algorithm):
        if algorithm not in RSS_ALGORITHMS:
            raise ValidationError(f"{algorithm} is not a known revenue sharing algorithm.")


class StakeholderShare(models.Model):
    stakeholderId = models.CharField(
        max_length=100, primary_key=True, blank=False, validators=[RSSValidators.validate_type(str)]
    )
    stakeholderShare = CustomDecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )

    class Meta:
        managed = False


class RSSModel(models.Model):
    # `providerId` is compatible with `Organization.name`
    _id = models.ObjectIdField()

    providerId = models.CharField(max_length=100)
    productClass = models.CharField(max_length=100, blank=False, validators=[RSSValidators.validate_type(str)])
    algorithmType = models.CharField(
        max_length=100, default="FIXED_PERCENTAGE", validators=[RSSValidators.validate_algorithm]
    )
    providerShare = CustomDecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    aggregatorShare = CustomDecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    stakeholders = models.ArrayField(
        model_container=StakeholderShare, default=list, blank=True, validators=[RSSValidators.validate_stakeholders]
    )

    class Meta:
        unique_together = ("providerId", "productClass")

    def validate_value_sum(self):
        stakeholder_value_sum = sum(map(lambda stakeholder: stakeholder["stakeholderShare"], self.stakeholders))
        if stakeholder_value_sum + self.aggregatorShare + self.providerShare != 100.0:
            raise ValidationError(
                "The sum of percentages for the aggregator, owner and stakeholders must equal 100. "
                f"{self.aggregatorShare} + {self.providerShare} + {stakeholder_value_sum} != 100"
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        self.validate_value_sum()
        super().save(*args, **kwargs)


class CDR(models.Model):
    """
    Model for a Charging Data Record.
    """

    class TransactionTypes(models.TextChoices):
        CHARGE = "C", "Charge"
        REFUND = "R", "Refund"

    class TransactionStates(models.TextChoices):
        RECORDED = "R", "Recored"
        PROCESSING = "P", "Processing"
        SETTLED = "S", "Settled"

    productClass = models.CharField(max_length=100)
    correlationNumber = models.CharField(max_length=100)
    state = models.CharField(max_length=1, choices=TransactionStates.choices, default=TransactionStates.RECORDED)
    timestamp = models.DateTimeField(default=now)
    application = models.CharField(max_length=100)
    transactionType = models.CharField(max_length=1, choices=TransactionTypes.choices, default=TransactionTypes.CHARGE)
    event = models.CharField(max_length=100)
    referenceCode = models.CharField(max_length=100)
    description = models.TextField()
    chargedAmount = CustomDecimalField(max_digits=20, decimal_places=3)
    chargedTaxAmount = CustomDecimalField(max_digits=20, decimal_places=3)
    currency = models.CharField(max_length=100)
    customerId = models.CharField(max_length=100)
    providerId = models.CharField(max_length=100)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class StakeholderTotal(models.Model):
    stakeholderId = models.CharField(
        max_length=100, primary_key=True, blank=False, validators=[RSSValidators.validate_type(str)]
    )
    stakeholderTotal = CustomDecimalField(max_digits=23, decimal_places=3)

    class Meta:
        managed = False


class SettlementReport(models.Model):
    class ReportStates(models.TextChoices):
        RECORDED = "R", "Recorded"
        PAID = "P", "Paid"

    providerId = models.CharField(max_length=50)
    productClass = models.CharField(max_length=100)
    algorithmType = models.CharField(
        max_length=100, default="FIXED_PERCENTAGE", validators=[RSSValidators.validate_algorithm]
    )
    timestamp = models.DateTimeField(default=now)
    state = models.CharField(max_length=1, choices=ReportStates.choices, default=ReportStates.RECORDED)
    currency = models.CharField(max_length=100)
    providerTotal = CustomDecimalField(max_digits=23, decimal_places=3)
    aggregatorTotal = CustomDecimalField(max_digits=23, decimal_places=3)
    stakeholders = models.ArrayField(
        model_container=StakeholderTotal, default=list, blank=True, validators=[RSSValidators.validate_stakeholders]
    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def field_names(cls) -> set:
        return set(map(lambda x: x.name, cls._meta.get_fields()))
