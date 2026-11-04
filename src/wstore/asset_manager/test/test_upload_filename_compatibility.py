"""Compatibility baseline for filename validation changes (no database or S3 writes)."""

import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import quote, unquote, urlsplit

from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve

from wstore.asset_manager import asset_manager, views
from wstore.store_commons.utils.name import is_valid_file
from wstore.views import ServeMedia

NEW_FILENAMES = ("document (1).pdf", "report[1]+notes.csv", "O'Brien & notes.txt", "README", ".env", "Cafe\u0301.txt")


@override_settings(SITE="http://testdomain.com/", MEDIA_DIR="media", BUCKET_NAME="test", ACL_ENABLED=False)
class UploadFilenameCompatibilityTests(SimpleTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.media_root = Path(directory.name) / "media"
        setting = override_settings(MEDIA_ROOT=str(self.media_root))
        setting.enable()
        self.addCleanup(setting.disable)
        self.factory = RequestFactory()
        self.user = SimpleNamespace(
            is_anonymous=False,
            userprofile=SimpleNamespace(current_organization=SimpleNamespace(name="seller")),
        )
        self.body = b"original file contents"
        self.resource = Mock(
            pk="123456",
            product_id="product-1",
            state="attached",
            is_public=False,
            resource_path="media/assets/seller/previous.txt",
            download_link="http://testdomain.com/charging/media/assets/seller/previous.txt",
            old_versions=[],
            version="1.0",
            meta_info={},
            content_type="text/plain",
        )
        self.resource.get_url.side_effect = lambda: self.resource.download_link
        self.resource.get_uri.return_value = "http://testdomain.com/charging/api/assetManagement/assets/123456"
        model_patch = patch.object(asset_manager, "Resource")
        self.model = model_patch.start()
        self.addCleanup(model_patch.stop)
        self.model.objects.create.side_effect = self.create_resource
        self.model.objects.filter.return_value = [self.resource]
        self.model.objects.get.return_value = self.resource
        s3_patch = patch.object(asset_manager.boto3, "client")
        self.s3 = s3_patch.start().return_value
        self.addCleanup(s3_patch.stop)
        self.s3.get_bucket_location.return_value = {"LocationConstraint": "eu-north-1"}
        self.s3.upload_file.side_effect = lambda path, *args, **kwargs: self.assertEqual(
            Path(path).read_bytes(), self.body
        )
        timer_patch = patch.object(asset_manager.threading, "Timer")
        self.timer = timer_patch.start()
        self.addCleanup(timer_patch.stop)

    def create_resource(self, **fields):
        for key, value in fields.items():
            setattr(self.resource, key, value)
        return self.resource

    def request_upload(self, filename, multipart=False, upgrade=False, public=False):
        url = "/charging/api/assetManagement/assets/"
        url += "123456/upgradeJob" if upgrade else "uploadJob"
        data = {"contentType": "text/plain", "isPublic": public}
        if multipart:
            data = {"json": json.dumps(data), "file": SimpleUploadedFile(filename, self.body)}
            request = self.factory.post(url, data, HTTP_ACCEPT="application/json")
            self.assertIsInstance(request.FILES["file"], InMemoryUploadedFile)
        else:
            data["content"] = {"name": filename, "data": base64.b64encode(self.body).decode("ascii")}
            request = self.factory.post(
                url,
                json.dumps(data),
                content_type="application/json",
                HTTP_ACCEPT="application/json",
            )
        request.user = self.user
        match = resolve(url)
        collection = views.UpgradeCollection if upgrade else views.UploadCollection
        self.assertIsInstance(match.func, collection)
        return match.func(request, **match.kwargs)

    def assert_success(self, response, expected_url):
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(response["Location"], expected_url)
        self.assertEqual(
            json.loads(response.content),
            {
                "content": expected_url,
                "contentType": "text/plain",
                "id": "123456",
                "href": self.resource.get_uri(),
            },
        )

    def test_existing_filenames_keep_local_paths_urls_and_api_for_both_formats(self):
        with override_settings(AWS_ENABLED=False):
            for multipart in (False, True):
                for filename in ("document.txt", "example file.txt", "Informe_á-東京.v1.txt"):
                    with self.subTest(multipart=multipart, filename=filename):
                        path = self.media_root / "assets" / "seller" / filename
                        response = self.request_upload(filename, multipart=multipart)
                        self.assert_success(
                            response, "http://testdomain.com/charging/media/assets/seller/" + quote(filename)
                        )
                        self.assertEqual(self.resource.resource_path, "media/assets/seller/" + filename)
                        self.assertEqual(path.read_bytes(), self.body)
                        path.unlink()

    def test_s3_uploads_keep_keys_urls_and_api_for_both_formats(self):
        with override_settings(AWS_ENABLED=True):
            for multipart in (False, True):
                for filename in ("document.txt", "example file.txt", "Informe_á-東京.v1.txt") + NEW_FILENAMES:
                    with self.subTest(multipart=multipart, filename=filename):
                        response = self.request_upload(filename, multipart=multipart, public=True)
                        self.assert_success(
                            response, "https://s3-eu-north-1.amazonaws.com/test/media/" + quote(filename)
                        )
                        self.assertEqual(self.resource.resource_path, "media/" + filename)
                        path = self.media_root / "assets" / "temp" / filename
                        self.s3.upload_file.assert_called_with(str(path), "test", "media/" + filename, ExtraArgs=None)
                        self.assertFalse(path.exists())

    def test_upgrades_keep_local_paths_urls_and_api_for_both_formats(self):
        with override_settings(AWS_ENABLED=False):
            for multipart in (False, True):
                with self.subTest(multipart=multipart):
                    self.resource.state = "attached"
                    filename = "next version [{}] (1).txt".format(multipart)
                    response = self.request_upload(filename, multipart=multipart, upgrade=True)
                    self.assert_success(
                        response, "http://testdomain.com/charging/media/assets/seller/" + quote(filename)
                    )
                    self.assertEqual(self.resource.resource_path, "media/assets/seller/" + filename)
                    self.assertEqual((self.media_root / "assets" / "seller" / filename).read_bytes(), self.body)
                    self.assertEqual(self.resource.state, "upgrading")
                    self.assertEqual(len(self.resource.old_versions), 1 + int(multipart))
                    self.timer.return_value.start.assert_called()

    def test_invalid_filename_preserves_error_contract_for_both_formats(self):
        with override_settings(AWS_ENABLED=False):
            for multipart in (False, True):
                with self.subTest(multipart=multipart):
                    response = self.request_upload("invalid?.txt", multipart=multipart)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
                    self.assertFalse(response.has_header("Location"))
                    self.assertEqual(
                        json.loads(response.content),
                        {
                            "result": "error",
                            "error": "Invalid file name format: Unsupported character",
                        },
                    )
                    self.model.objects.create.assert_not_called()
                    self.assertFalse((self.media_root / "assets").exists())

    def test_attached_duplicate_keeps_original_file_and_conflict_response(self):
        with override_settings(AWS_ENABLED=False):
            for multipart in (False, True):
                with self.subTest(multipart=multipart):
                    path = self.media_root / "assets" / "seller" / "existing.txt"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"previous contents")
                    response = self.request_upload("existing.txt", multipart=multipart)
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(
                        json.loads(response.content),
                        {
                            "result": "error",
                            "error": "The provided digital asset file (existing.txt) already exists",
                        },
                    )
                    self.assertEqual(path.read_bytes(), b"previous contents")
                    self.model.objects.get.assert_called_with(resource_path="media/assets/seller/existing.txt")
                    self.resource.delete.assert_not_called()

    def test_unattached_duplicate_can_still_be_replaced(self):
        with override_settings(AWS_ENABLED=False):
            for multipart in (False, True):
                with self.subTest(multipart=multipart):
                    self.resource.product_id = None
                    self.resource.delete.reset_mock()
                    path = self.media_root / "assets" / "seller" / "existing.txt"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"previous contents")
                    response = self.request_upload("existing.txt", multipart=multipart)
                    self.assert_success(response, "http://testdomain.com/charging/media/assets/seller/existing.txt")
                    self.assertEqual(path.read_bytes(), self.body)
                    self.resource.delete.assert_called_once_with()

    @override_settings(USE_XSENDFILE=False)
    def test_existing_local_download_urls_still_resolve_and_serve_original_bytes(self):
        for filename in ("document.txt", "example file.txt", "Informe_á-東京.v1.txt"):
            with self.subTest(filename=filename):
                path = self.media_root / "assets" / "seller" / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(self.body)
                url = "http://testdomain.com/charging/media/assets/seller/" + quote(filename)
                match = resolve(unquote(urlsplit(url).path))
                self.assertIsInstance(match.func, ServeMedia)
                self.assertEqual(match.kwargs, {"path": "assets/seller", "name": filename})
                request = self.factory.get(url)
                request.user = self.user
                with patch.object(ServeMedia, "_validate_asset_permissions", return_value=(None, None)) as permission:
                    response = match.func(request, **match.kwargs)
                    try:
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(b"".join(response.streaming_content), self.body)
                    finally:
                        response.close()
                    permission.assert_called_once_with(self.user, "assets/seller", filename)

    def test_existing_filename_edge_cases_remain_accepted(self):
        # Characterize compatibility exceptions; these are not recommendations for new names.
        for filename in ("..pdf", ".config.json", " report.txt", "x" * 256 + ".txt"):
            with self.subTest(filename=filename):
                self.assertTrue(is_valid_file(filename))

    @override_settings(AWS_ENABLED=False, USE_XSENDFILE=False)
    def test_new_filenames_upload_and_download_in_both_formats(self):
        for multipart in (False, True):
            for filename in NEW_FILENAMES:
                with self.subTest(multipart=multipart, filename=filename):
                    response = self.request_upload(filename, multipart=multipart)
                    expected_url = "http://testdomain.com/charging/media/assets/seller/" + quote(filename)
                    self.assert_success(response, expected_url)
                    self.assertEqual(self.resource.resource_path, "media/assets/seller/" + filename)
                    match = resolve(unquote(urlsplit(expected_url).path))
                    self.assertEqual(match.kwargs, {"path": "assets/seller", "name": filename})
                    request = self.factory.get(expected_url)
                    request.user = self.user
                    with patch.object(
                        ServeMedia, "_validate_asset_permissions", return_value=(None, None)
                    ) as permission:
                        download = match.func(request, **match.kwargs)
                        try:
                            self.assertEqual(download.status_code, 200)
                            self.assertEqual(b"".join(download.streaming_content), self.body)
                        finally:
                            download.close()
                        permission.assert_called_once_with(self.user, "assets/seller", filename)
                    (self.media_root / "assets" / "seller" / filename).unlink()

    @override_settings(AWS_ENABLED=False)
    def test_unsafe_names_remain_rejected_before_storage(self):
        # Test JSON names verbatim: Django already sanitizes multipart filenames.
        for filename in (
            "",
            " ",
            ".",
            "..",
            "../file.txt",
            "folder/file.txt",
            "folder\\file.txt",
            "/file.txt",
            "report?.txt",
            "report#draft.txt",
            "report%20draft.txt",
            "bad\x00name.txt",
            "bad\rname.txt",
            "bad\nname.txt",
            "bad\x7fname.txt",
            "bad\x85name.txt",
            "report.txt\n",
            "report (1).txt\n",
        ):
            with self.subTest(filename=filename):
                self.assertFalse(is_valid_file(filename))
                response = self.request_upload(filename)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    json.loads(response.content),
                    {
                        "result": "error",
                        "error": "Invalid file name format: Unsupported character",
                    },
                )
                self.model.objects.create.assert_not_called()
                self.assertFalse((self.media_root / "assets").exists())
