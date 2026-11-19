from importlib import reload

from django.conf import settings
from django.test import TestCase
from parameterized import parameterized
from mock import patch
import wstore.store_commons.utils.http as http_utils
import wstore.rss.views as rss_views
from django.test.client import Client
from json import loads

GET_TESTS = [
    {
        "name": "correct_basic",
        "response_code": 200,
        "expected": [
            {
                "id": "FIXED_PERCENTAGE",
                "name": "Fixed Percentage Algorithm",
                "description": "Distributes the revenue based on fixed percentages for each party",
            }
        ],
    }
]


class AlgorithmViewsTestCase(TestCase):
    tags = "rss", "rs-algorithms"

    @classmethod
    def tearDownClass(cls):
        super(AlgorithmViewsTestCase, cls).tearDownClass()

    def setUp(self):
        settings.WSTOREMAIL = "testmail@mail.com"
        settings.RSS = "http://testhost.com/rssHost/"
        settings.STORE_NAME = "wstore"

        with patch.object(http_utils, "authentication_required", lambda x: x):
            reload(rss_views)
        # Create Mocks
        TestCase.setUp(self)

    @parameterized.expand([test.values() for test in GET_TESTS])
    def test_list_algorithms(self, name, response_code, expected=None):
        client = Client()
        response = client.get(
            "/charging/api/revenueSharing/algorithms/",
            content_type="application/json",
            headers={"HTTP_ACCEPT": "aplication/json"},
        )

        self.assertEquals(response.status_code, response_code)
        if response.status_code == 200:
            self.assertEquals(loads(response.content), expected)
        else:
            print(response.content)
            self.assertEquals(response.content, expected)
