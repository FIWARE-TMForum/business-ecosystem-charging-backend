from copy import deepcopy
from importlib import reload

from django.conf import settings
from django.test import TestCase
from mock import MagicMock
from parameterized import parameterized
import wstore.store_commons.utils.http as http_utils
import wstore.rss.views as rss_views
import wstore.rss.models as rss_models
from django.test.client import Client
from json import dumps, loads
from django.core.exceptions import ObjectDoesNotExist


CREATE_TESTS = [
    {  # ---------------------------------
        "name": "correct_basic",
        "model": {
            "providerId": "provider",
            "providerShare": 70,
            "aggregatorShare": 30,
            "productClass": "class",
        },
        "response_code": 201,
        "expected": {
            "providerId": "provider",
            "providerShare": "70.00",
            "aggregatorShare": "30.00",
            "productClass": "class",
            "algorithmType": "FIXED_PERCENTAGE",
            "stakeholders": [],
        },
    },
    {  # ---------------------------------
        "name": "correct_stakeholders",
        "model": {
            "providerId": "provider",
            "providerShare": 50,
            "aggregatorShare": 30,
            "productClass": "class",
            "stakeholders": [
                {"stakeholderId": "st1", "stakeholderShare": 10},
                {"stakeholderId": "st2", "stakeholderShare": 10},
            ],
        },
        "response_code": 201,
        "expected": {
            "providerId": "provider",
            "providerShare": "50.00",
            "aggregatorShare": "30.00",
            "productClass": "class",
            "algorithmType": "FIXED_PERCENTAGE",
            "stakeholders": [
                {"stakeholderId": "st1", "stakeholderShare": "10.00"},
                {"stakeholderId": "st2", "stakeholderShare": "10.00"},
            ],
        },
    },
    {  # ---------------------------------
        "name": "missing_owner_value",
        "model": {
            "providerId": "provider",
            "aggregatorShare": 30,
            "productClass": "class",
            "stakeholders": [],
        },
        "response_code": 400,
        "expected": "Bad request: {'providerShare': ['This field cannot be null.']}",
    },
    {  # ---------------------------------
        "name": "invalid_owner_value",
        "model": {
            "providerId": "provider",
            "providerShare": "invalid",
            "aggregatorShare": 30,
            "productClass": "class",
            "stakeholders": [],
        },
        "response_code": 400,
        "expected": "Bad request: {'providerShare': ['`value` cannot be converted to Decimal']}",
    },
    {  # ---------------------------------
        "name": "missing_aggregator_value",
        "model": {
            "providerId": "provider",
            "providerShare": 70,
            "productClass": "class",
            "stakeholders": [],
        },
        "response_code": 400,
        "expected": "Bad request: {'aggregatorShare': ['This field cannot be null.']}",
    },
    {  # ---------------------------------
        "name": "invalid_aggregator_value",
        "model": {
            "providerId": "provider",
            "providerShare": 70,
            "aggregatorShare": "invalid",
            "productClass": "class",
            "stakeholders": [],
        },
        "response_code": 400,
        "expected": "Bad request: {'aggregatorShare': ['`value` cannot be converted to Decimal']}",
    },
    {  # ---------------------------------
        "name": "invalid_percentage_sum",
        "model": {
            "providerId": "provider",
            "providerShare": 70,
            "aggregatorShare": 120,
            "productClass": "class",
            "stakeholders": [],
        },
        "response_code": 400,
        "expected": "Bad request: {'aggregatorShare': ['Ensure this value is less than or equal to 100.0.']}",
    },
    {  # ---------------------------------
        "name": "invalid_percentage_stakeholders",
        "model": {
            "providerId": "provider",
            "providerShare": 60,
            "aggregatorShare": 30,
            "productClass": "class",
            "stakeholders": [
                {"stakeholderId": "st1", "stakeholderShare": 10},
                {"stakeholderId": "st2", "stakeholderShare": 10},
            ],
        },
        "response_code": 400,
        "expected": "Bad request: ['The sum of percentages for the aggregator, owner and stakeholders must equal 100. 30.00 + 60.00 + 20.00 != 100']",
    },
    {  # ---------------------------------
        "name": "missing_provider",
        "model": {"providerShare": 70, "aggregatorShare": 30, "productClass": "class", "stakeholders": []},
        "response_code": 400,
        "expected": "Bad request: {'providerId': ['This field cannot be blank.']}",
    },
    {  # ---------------------------------
        "name": "missing_class",
        "model": {"providerId": "provider", "providerShare": 70, "aggregatorShare": 30, "stakeholders": []},
        "response_code": 400,
        "expected": "Bad request: {'productClass': ['This field cannot be blank.']}",
    },
]


UPDATE_TESTS = [
    {  # ---------------------------------
        "name": "correct_basic",
        "model": {
            "providerId": "provider",
            "providerShare": "70",
            "aggregatorShare": "30",
            "productClass": "class",
            "algorithmType": "FIXED_PERCENTAGE",
            "stakeholders": [],
        },
        "update": {
            "providerId": "provider",
            "providerShare": 60,
            "aggregatorShare": 30,
            "productClass": "class",
            "stakeholders": [
                {"stakeholderId": "st1", "stakeholderShare": 5},
                {"stakeholderId": "st2", "stakeholderShare": 5},
            ],
        },
        "response_code": 200,
        "expected": {
            "providerId": "provider",
            "providerShare": "60.00",
            "aggregatorShare": "30.00",
            "productClass": "class",
            "algorithmType": "FIXED_PERCENTAGE",
            "stakeholders": [
                {"stakeholderId": "st1", "stakeholderShare": "5.00"},
                {"stakeholderId": "st2", "stakeholderShare": "5.00"},
            ],
        },
    },
    {  # ---------------------------------
        "name": "invalid_attribute",
        "model": {
            "providerId": "provider",
            "providerShare": "50",
            "aggregatorShare": "30",
            "productClass": "class",
            "algorithmType": "FIXED_PERCENTAGE",
            "stakeholders": [
                {"stakeholderId": "st1", "stakeholderShare": "10"},
                {"stakeholderId": "st2", "stakeholderShare": "10"},
            ],
        },
        "update": {
            "providerId": "provider",
            "providerShare": 50,
            "aggregatorShare": 30,
            "stakeholders": [
                {"stakeholderId": "st1", "stakeholderShare": 10},
                {"stakeholderId": "st2", "stakeholderShare": 10},
            ],
        },
        "response_code": 400,
        "expected": "Bad request: must contain fields `providerId`, `productClass`.",
    },
    {  # ---------------------------------
        "name": "invalid_update",
        "model": {
            "providerId": "provider",
            "providerShare": "50",
            "aggregatorShare": "30",
            "productClass": "class",
            "algorithmType": "FIXED_PERCENTAGE",
            "stakeholders": [
                {"stakeholderId": "st1", "stakeholderShare": "10"},
                {"stakeholderId": "st2", "stakeholderShare": "10"},
            ],
        },
        "update": {
            "providerId": "provider",
            "providerShare": 50,
            "aggregatorShare": 30,
            "productClass": "class",
            "stakeholders": [
                {"stakeholderId": "st1", "stakeholderShare": 20},
                {"stakeholderId": "st2", "stakeholderShare": 10},
            ],
        },
        "response_code": 400,
        "expected": "Bad request: ['The sum of percentages for the aggregator, owner and stakeholders must equal 100. 30.00 + 50.00 + 30.00 != 100']",
    },
    {  # ---------------------------------
        "name": "model_does_not_exist",
        "model": {"exception": ObjectDoesNotExist()},
        "update": {"providerId": "provider", "productClass": "class"},
        "response_code": 404,
        "expected": "Revenue Sharing Model does not exist",
    },
]


GET_TESTS = [
    {  # ---------------------------------
        "name": "correct_basic",
        "result": [
            {
                "providerId": "provider",
                "providerShare": "70.00",
                "aggregatorShare": "30.00",
                "productClass": "class",
                "algorithmType": "FIXED_PERCENTAGE",
                "stakeholders": [],
            }
        ],
        "filter": {},
        "response_code": 200,
    }
]


class ModelManagerTestCase(TestCase):
    tags = "rss", "rs-models"

    @classmethod
    def tearDownClass(cls):
        super(ModelManagerTestCase, cls).tearDownClass()

    def setUp(self):
        self.maxDiff = None
        settings.WSTOREMAIL = "testmail@mail.com"
        settings.RSS = "http://testhost.com/rssHost/"
        settings.STORE_NAME = "wstore"

        # Create Mocks
        def mock_save(*x, **y):
            rss_models.RSSModel.full_clean(x[0])
            rss_models.RSSModel.validate_value_sum(x[0])

        rss_models.RSSModel.save = mock_save
        http_utils.authentication_required = lambda x: x
        reload(rss_views)
        TestCase.setUp(self)

    @parameterized.expand([test.values() for test in CREATE_TESTS])
    def test_create_model(self, name, model, response_code, expected=None):
        client = Client()
        response = client.post(
            "/charging/api/revenueSharing/models/",
            dumps(model),
            content_type="application/json",
            headers={"HTTP_ACCEPT": "aplication/json"},
        )

        self.assertEquals(response.status_code, response_code)
        if response.status_code == 201:
            self.assertEquals(loads(response.content), expected)
        else:
            print(response.content)
            self.assertEquals(loads(response.content), {
                "result": "error",
                "error": expected
            })

    @parameterized.expand([test.values() for test in UPDATE_TESTS])
    def test_update_model(self, name, model, update, response_code, expected=None):
        def get_model(**query):
            if "exception" in model and isinstance(model["exception"], Exception):
                raise model["exception"]
            m = rss_models.RSSModel(**model)
            return m

        rss_models.RSSModel.objects = MagicMock(get=get_model)

        client = Client()
        response = client.put(
            "/charging/api/revenueSharing/models/",
            deepcopy(update),
            content_type="application/json",
            headers={"HTTP_ACCEPT": "aplication/json"},
        )

        self.assertEquals(response.status_code, response_code)
        if response.status_code == 200:
            self.assertEquals(loads(response.content), expected)
        else:
            self.assertEquals(loads(response.content), {
                "result": "error",
                "error": expected
            })

    @parameterized.expand([test.values() for test in GET_TESTS])
    def test_get_models(self, name, result, filter, response_code):
        def get_models(**query):
            if "exception" in result and isinstance(result["exception"], Exception):
                raise result["exception"]
            return result

        rss_models.RSSModel.objects = MagicMock()
        rss_models.RSSModel.objects.filter().__getitem__().values = get_models

        client = Client()
        response = client.get(
            "/charging/api/revenueSharing/models/", filter, headers={"HTTP_ACCEPT": "aplication/json"}
        )

        self.assertEquals(response.status_code, response_code)
        if response.status_code == 200:
            __import__("pprint").pprint(loads(response.content))
            self.assertEquals(loads(response.content), result)
        else:
            self.assertEquals(response.content, b"Error: Bad request")
