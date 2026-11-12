# Business Ecosystem Charging Backend

[![](https://nexus.lab.fiware.org/repository/raw/public/badges/chapters/data-monetization.svg)](https://www.fiware.org/developers/catalogue/)
[![License badge](https://img.shields.io/github/license/FIWARE-TMForum/Business-API-Ecosystem.svg)](https://opensource.org/licenses/AGPL-3.0)
[![](https://img.shields.io/badge/tag-fiware-orange.svg?logo=stackoverflow)](http://stackoverflow.com/questions/tagged/fiware)
[![Support](https://img.shields.io/badge/support-askbot-yellowgreen.svg)](https://ask.fiware.org)
<br>
[![Quay badge](https://img.shields.io/badge/quay.io-fiware%2Fbiz--ecosystem--charging--backend-grey?logo=red%20hat&labelColor=EE0000)](https://quay.io/repository/fiware/biz-ecosystem-charging-backend)
[![Docker badge](https://img.shields.io/badge/docker-fiware%2Fbiz--ecosystem--charging--backend-blue?logo=docker)](https://registry.hub.docker.com/r/fiware/biz-ecosystem-charging-backend)
<br>
[![Docs](https://img.shields.io/badge/docs-latest-brightgreen.svg?style=flat)](http://business-api-ecosystem.readthedocs.io/en/latest/)
[![Tests Status](https://github.com/FIWARE-TMForum/business-ecosystem-charging-backend/actions/workflows/test.yml/badge.svg)](https://github.com/FIWARE-TMForum/business-ecosystem-charging-backend/actions/workflows/test.yml) [![Coverage Status](https://coveralls.io/repos/github/FIWARE-TMForum/business-ecosystem-charging-backend/badge.svg?branch=master)](https://coveralls.io/github/FIWARE-TMForum/business-ecosystem-charging-backend?branch=master)

 * [Introduction](#introduction)
 * [GEi Overall Description](#gei-overall-description)
 * [Installation](#installation)
 * [API Reference](#api-reference)
 * [Testing](#testing)
 * [Advanced Topics](#advanced-topics)

# Introduction

This is the code repository for the Business Ecosystem Charging Backend, one of the components that made up the [Business API Ecosystem GE](https://github.com/FIWARE-TMForum/Business-API-Ecosystem). The Business API Ecosystem is part of [FIWARE](https://www.fiware.org), and has been developed in collaboration with the [TM Forum](https://www.tmforum.org/)

Any feedback is highly welcome, including bugs, typos or things you think should be included but aren't. You can use [GitHub Issues](https://github.com/FIWARE-TMForum/business-ecosystem-charging-backend/issues/new) to provide feedback.

| :books: [Documentation](http://business-api-ecosystem.readthedocs.io) | :whale: [Docker](https://registry.hub.docker.com/r/fiware/biz-ecosystem-charging-backend) | <img style="height:1em" src="https://quay.io/static/img/quay_favicon.png"/> [quay.io](https://quay.io/repository/fiware/biz-ecosystem-charging-backend) |
 | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- | --- |

# GEi Overall Description

The Business API Ecosystem is a joint component made up of the FIWARE Business Framework and a set of APIs (and its reference implementations) provided by the TMForum. This component allows the monetization of different kind of assets (both digital and physical) during the whole service life cycle, from offering creation to its charging, accounting and revenue settlement and sharing. The Business API Ecosystem exposes its complete functionality through TMForum standard APIs; concretely, it includes the catalog management, ordering management, inventory management, usage management, billing, customer, and party APIs.

In this context, the Business Ecosystem Charging Backend is the component in charge of processing the different pricing models, the accounting information, and the revenue sharing reports. With this information, the  Business Ecosystem Charging Backend is able to calculate amounts to be charged, charge customers, and pay sellers.

# Installation

The Business Ecosystem Charging Backend is installed as part of the Business API Ecosystem, so the instructions to install it can be found at [the Business API Ecosystem Installation Guide](http://business-api-ecosystem.readthedocs.io/en/latest/installation-administration-guide.html). You can install the software in two different ways:

* Using a [Docker Container](https://hub.docker.com/r/fiware/biz-ecosystem-charging-backend/)
* Manually

# API Reference

For further documentation, you can check the API Reference available at:

* [Apiary](http://docs.fiwaretmfbizecosystem.apiary.io)
* [GitHub Pages](https://fiware-tmforum.github.io/Business-API-Ecosystem/)

# Recurring payment recovery

For local recurring payments, `BAE_CB_PAYMENT_RECOVERY_GRACE_HOURS` sets the
recovery window from the first confirmed payment failure (default: `72` hours).
Use a positive value shorter than every applicable billing cycle; for example,
configure fewer than 24 hours for daily subscriptions. The termination path does
not fetch rates or validate billing cycles before acting. The first failure time is
stored on the PaymentRecord as `first_failed_at` and retained across retries and
scheduler runs. Bill dates do not determine recovery deadlines. Existing payment
records without a failure timestamp start their window when a failure is first
observed; historical failure dates are not inferred from bill or attempt creation.

Products remain active during recovery. After expiry, an unsuccessful completed
attempt causes whole-product termination through the existing plugin cleanup and
termination recovery flow. A bill without a payment record follows the existing
first-payment flow regardless of its age; expiry applies only to a confirmed
failed payment attempt. Pending attempts continue through the existing status
checks; success settles the bill without changing billing periods. An indefinitely
pending attempt can therefore extend access beyond the window and into another
billing cycle; it requires operational investigation.

After termination, unpaid bills move to the billing API's `onHold` state to stop
automatic collection. Bill amounts and applied rates remain unchanged. The
administrator can interpret unpaid charges using the types and coverage recorded
in the ACBRs; this software does not adjust or collect debt after termination.
The existing first-payment request flow is unchanged.

# Testing

To execute the unit tests, just run:

```
python manage.py test
```

## Advanced Topics

* [User & Programmers Guide](https://github.com/FIWARE-TMForum/Business-API-Ecosystem/blob/master/doc/user-programmer-guide.rst)
* [Installation & Administration Guide](https://github.com/FIWARE-TMForum/Business-API-Ecosystem/blob/master/doc/installation-administration-guide.rst)

You can also find this documentation on [ReadTheDocs](http://business-api-ecosystem.readthedocs.io)
