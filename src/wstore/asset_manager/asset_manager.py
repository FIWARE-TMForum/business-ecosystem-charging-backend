# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S. L.

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

import base64
import json
import os
import threading
from logging import getLogger
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from wstore.models import Resource, ResourcePlugin, ResourceVersion
from wstore.store_commons.database import DocumentLock
from wstore.store_commons.errors import ConflictError
from wstore.store_commons.rollback import downgrade_asset, downgrade_asset_pa, rollback
from wstore.store_commons.utils.name import is_valid_file
from wstore.store_commons.utils.url import is_valid_url, url_fix
import boto3
from wstore.asset_manager import service_specification_manager

logger = getLogger("wstore.default_logger")


class AssetManager:
    def __init__(self):
        # AWS credentials
        if settings.AWS_ENABLED:
            self.s3 = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )

    def _save_resource_file(self, provider, file_, isPublic):
        logger.debug(f"Saving resource file {file_['name']}")
        # Load file contents
        if isinstance(file_, dict):
            file_name = file_["name"]
            content = base64.b64decode(file_["data"])
        else:
            file_name = file_.name
            file_.seek(0)
            content = file_.read()
        # Check file name
        if not is_valid_file(file_name):
            logger.debug(f"`{file_name}` is not a valid file name")
            raise ValueError("Invalid file name format: Unsupported character")
        if isPublic is True and settings.AWS_ENABLED:
            return self.__save_resource_aws(file_name, content)
        else:
            return self.__save_resource_local(provider, file_name, content)
        

    def __save_resource_aws(self,  file_name, content):

        # Create temp dir for assets if it does not exist
        provider_dir = os.path.join(settings.MEDIA_ROOT, "assets", "temp")

        if not os.path.isdir(provider_dir):
            os.makedirs(provider_dir, exist_ok=True)
        # Local file path for the asset file 
        file_path = os.path.join(provider_dir, file_name)
        logger.debug(f"File path for asset file: {file_path}")
        # Key of s3
        resource_path = os.path.join(settings.MEDIA_DIR, file_name)

        if resource_path.startswith("/"):
            resource_path = resource_path[1:]

        # Check if the file already exists
        if os.path.exists(file_path):
            logger.error(f"The asset file `{file_name}` already exists")
            raise ConflictError(f"The provided digital asset file ({file_name}) already exists")

        logger.debug("Paths needed for saving temp resource file OK")
        
        # Create file
        with open(file_path, "wb") as f:
            f.write(content)

        self.rollback_logger["files"].append(file_path)

        logger.debug("Asset temp file created")
        # upload the file to S3
        acl = {'ACL': 'public-read'} if settings.ACL_ENABLED else None
        self.s3.upload_file(file_path, settings.BUCKET_NAME, resource_path, ExtraArgs=acl)

        logger.debug(f'The file {file_name} is uploaded to {resource_path} in s3')

        # delete file in local
        try:
            logger.debug(f"Deleting file {file_path}")
            os.remove(file_path)
            logger.debug(f"Deleting file {file_path}2")
        except:
            raise ConflictError(f"The provided digital asset file ({file_name}) cannot be removed")
        site = settings.SITE
        location = self.s3.get_bucket_location(Bucket=settings.BUCKET_NAME)['LocationConstraint']
        logger.debug(location)
        url = "https://s3-%s.amazonaws.com/%s/%s" % (location, settings.BUCKET_NAME, resource_path)
        logger.debug(url)
        return resource_path, url_fix(url)

    def __save_resource_local(self, provider, file_name, content):

        # Create provider dir for assets if it does not exist
        provider_dir = os.path.join(settings.MEDIA_ROOT, "assets", provider)

        if not os.path.isdir(provider_dir):
            os.makedirs(provider_dir, exist_ok=True)

        file_path = os.path.join(provider_dir, file_name)
        resource_path = file_path[file_path.index(settings.MEDIA_DIR) :]

        if resource_path.startswith("/"):
            resource_path = resource_path[1:]

        # Check if the file already exists
        if os.path.exists(file_path):
            res = Resource.objects.get(resource_path=resource_path)
            if res.service_id is not None:
                # If the resource has service_id field, it means that a product
                # spec has been created, so it cannot be overridden
                logger.error(f"The asset file `{file_name}` already exists")
                raise ConflictError(f"The provided digital asset file ({file_name}) already exists")
            res.delete()

        logger.debug("Paths needed for saving resource file OK")

        # Create file
        with open(file_path, "wb") as f:
            f.write(content)

        self.rollback_logger["files"].append(file_path)

        logger.debug("Asset file created")
        site = settings.SITE
        return resource_path, url_fix(urljoin(site, "/charging/" + resource_path))

    def _create_resource_model(self, provider, resource_data):
        logger.debug("Creating resource model")

        # Create the resource
        resource = Resource.objects.create(
            provider=provider,
            version=resource_data["version"],
            download_link=resource_data["link"],
            resource_path=resource_data["content_path"],
            content_type=resource_data["content_type"].lower(),
            resource_type=resource_data["resource_type"],
            state=resource_data["state"],
            is_public=resource_data["is_public"],
            meta_info=resource_data["metadata"],
        )

        self.rollback_logger["models"].append(resource)

        logger.debug("Created resource model")
        return resource

    def _validate_asset_type(self, resource_type, content_type, provided_as, metadata):
        logger.debug(f"Validating asset type {resource_type}")

        if not resource_type and metadata:
            raise ValueError("You have to specify a valid asset type for providing meta data")

        if not resource_type:
            return

        plugins = ResourcePlugin.objects.filter(name=resource_type)
        if not len(plugins):
            logger.error(f"The asset type {resource_type} does not exist")
            raise ObjectDoesNotExist(f"The asset type {resource_type} does not exist")

        asset_type = plugins[0]  #Os asset_types son os plugins

        # Validate content type
        if len(asset_type.media_types) and content_type not in asset_type.media_types:
            logger.error(f"The content type {content_type} is not valid for the specified asset type")
            raise ValueError(f"The content type {content_type} is not valid for the specified asset type")

        # Validate providing method
        if provided_as not in asset_type.formats:
            logger.error("Invalid format for given asset type")
            raise ValueError(
                f"The format used for providing the digital asset ({provided_as}) "
                "is not valid for the given asset type"
            )

        # Validate that the included metadata is valid according to the form field
        if metadata and not asset_type.form:
            logger.error(f"The specified asset type does not allow meta data")
            raise ValueError("The specified asset type does not allow meta data")

        if asset_type.form:
            for k, v in asset_type.form.items():
                # Validate mandatory fields
                if "mandatory" in v and v["mandatory"] and "default" not in v and k not in metadata:
                    logger.error(f"Missing mandatory field {k} in metadata")
                    raise ValueError(f"Missing mandatory field {k} in metadata")

                # Validate metadata types
                if k in metadata and v["type"] != "checkbox" and not (isinstance(metadata[k], str)):
                    logger.error(f"Metadata field {k} must be a string")
                    raise TypeError(f"Metadata field {k} must be a string")

                if k in metadata and v["type"] == "checkbox" and not isinstance(metadata[k], bool):
                    logger.error(f"Metadata field {k} must be a boolean")
                    raise TypeError(f"Metadata field {k} must be a boolean")

                if (
                    k in metadata
                    and v["type"] == "select"
                    and metadata[k].lower() not in [option["value"].lower() for option in v["options"]]
                ):
                    logger.error(f"Metadata field {k} value is not one of the available options")
                    raise ValueError(f"Metadata field {k} value is not one of the available options")

                # Include default values
                if k not in metadata and "default" in v:
                    metadata[k] = v["default"]

        logger.debug("Validated asset type {resource_type} OK")

    def _load_resource_info(self, provider, data, file_=None):
        if "contentType" not in data:
            logger.error(f"Error loading resource info: Missing required field `contentType`")
            raise ValueError("Missing required field: contentType")

        resource_data = {
            "content_type": data["contentType"],
            "version": "",
            "resource_type": data.get("resourceType", ""),
            "state": "",
            "is_public": data.get("isPublic", False),
            "content_path": "",
        }

        logger.debug(f"Loading resource info for {resource_data['content_type']}")

        current_organization = provider.userprofile.current_organization

        resource_data["metadata"] = data.get("metadata", {})

        # Check if the asset is a file upload or a service registration
        provided_as = "FILE"
        if "content" in data:
            if isinstance(data["content"], str):
                download_link = data["content"]
                provided_as = "URL"

            elif isinstance(data["content"], dict):
                resource_data["content_path"], download_link = self._save_resource_file(
                    current_organization.name, data["content"], data["isPublic"]
                )

            else:
                logger.error("`content` field has an unsupported type, expected string or object")
                raise TypeError("`content` field has an unsupported type, expected string or object")

        elif file_ is not None:
            resource_data["content_path"], download_link = self._save_resource_file(current_organization.name, file_, data["isPublic"])

        else:
            logger.error("The digital asset has not been provided")
            raise ValueError("The digital asset has not been provided")

        if not is_valid_url(download_link):
            logger.error("The provided content is not a valid URL")
            raise ValueError("The provided content is not a valid URL")

        resource_data["link"] = download_link

        # Validate asset according to its type
        self._validate_asset_type(
            resource_data["resource_type"],
            resource_data["content_type"],
            provided_as,
            resource_data["metadata"],
        )

        #####################

        #####################

        logger.debug(f"Loaded resource info for {resource_data['content_type']} OK")
        return resource_data, current_organization

    @rollback()
    def upload_asset(self, provider, data, file_=None):
        """
        Uploads a new digital asset that will be used to create a product Specification
        :param provider: User uploading the digital asset
        :param data: Information of the asset
        :param file_: Digital asset file, in case it has been provided as multipart/form-data
        :return: The href of the digital asset
        """

        resource_data, current_organization = self._load_resource_info(provider, data, file_=file_)
        resource = self._create_resource_model(current_organization, resource_data)

        ########################
        #sp_manager = service_specification_manager.ServiceSpecificationManager()
        #sp_manager.create_service_spec_cand(resource)
        ########################

        logger.info(f"Uploaded asset: {resource}")
        return resource

    def _save_current_asset_version(self, asset):
        # Save current version info
        curr_version = ResourceVersion(
            version=asset.version,
            resource_path=asset.resource_path,
            download_link=asset.download_link,
            content_type=asset.content_type,
            meta_info=asset.meta_info,
        )

        asset.old_versions.append(curr_version)
        asset.version = ""
        asset.download_link = ""
        asset.meta_info = {}

        asset.save()
        logger.debug(f"Saved asset version: {asset.version}")

    def _upgrade_timer(self):
        lock = DocumentLock("wstore_resource", self._to_downgrade.pk, "asset")
        lock.wait_document()

        # Refresh asset info
        asset = Resource.objects.get(pk=self._to_downgrade.pk)

        # If the asset is in upgrading state when the timer ends, rollback is called
        if asset.state == "upgrading":
            downgrade_asset(asset)

        lock.unlock_document()

    @rollback(downgrade_asset_pa)
    def upgrade_asset(self, asset_id, provider, data, file_=None):
        """
        Upgrades a digital asset in order to enable the creation of a new product version
        :param asset_id: Id of the asset to be upgraded
        :param provider: User upgrading the digital asset
        :param data:
        :param file_:
        :return:
        """
        logger.debug(f"Start upgrading asset: {asset_id}")

        assets = Resource.objects.filter(pk=asset_id)

        if not len(assets):
            logger.error(f"The specified asset does not exist")
            raise ObjectDoesNotExist("The specified asset does not exist")

        asset = assets[0]

        if asset.is_public or data.get("isPublic", False):
            logger.error(f"It is not allowed to upgrade public assets, create a new one instead")
            raise ValueError("It is not allowed to upgrade public assets, create a new one instead")

        if asset.service_id is None:
            logger.error(f"It is not possible to upgrade an asset not included in a product specification")
            raise ValueError("It is not possible to upgrade an asset not included in a product specification")

        if asset.state == "upgrading":
            logger.error(f"The provided asset is already in upgrading state")
            raise ValueError("The provided asset is already in upgrading state")

        self._save_current_asset_version(asset)
        self._to_downgrade = asset

        resource_data, current_organization = self._load_resource_info(provider, data, file_=file_)

        asset.download_link = resource_data["link"]
        asset.resource_path = resource_data["content_path"]
        asset.meta_info = resource_data["metadata"]
        asset.content_type = resource_data["content_type"]
        asset.state = "upgrading"
        asset.save()

        # If the upgrading process is not completed in 15 seconds the upgrade is canceled
        # in order to avoid an inconsistent state
        t = threading.Timer(15, self._upgrade_timer)
        t.start()

        ######################
        # Necisto mirar lo del rollback porque si falla el api entonces
        # Necesitamos borrarlo en local
        #sp_manager = service_specification_manager.ServiceSpecificationManager()
        #sp_manager.update_service_spec_cand(asset)
        ######################
        
        logger.info(f"Upgrading asset: {asset_id} OK")
        return asset

    def get_resource_info(self, resource):
        return {
            "id": str(resource.pk),
            "version": resource.version,
            "contentType": resource.content_type,
            "state": resource.state,
            "href": resource.get_uri(),
            "location": resource.get_url(),
            "resourceType": resource.resource_type,                           
            "metadata": resource.meta_info,
        }

    def get_asset_info(self, asset_id):
        try:
            asset = Resource.objects.get(pk=asset_id)
        except:
            raise ObjectDoesNotExist("The specified digital asset does not exist")

        return self.get_resource_info(asset)

    def get_product_assets(self, service_id):
        assets = Resource.objects.filter(service_id=service_id)

        return [self.get_resource_info(asset) for asset in assets]

    def get_provider_assets_info(self, provider, pagination=None):
        if pagination and ("offset" not in pagination or "size" not in pagination):
            raise ValueError("Missing required parameter in pagination")

        if pagination and (not int(pagination["offset"]) >= 0 or not int(pagination["size"]) > 0):
            raise ValueError("Invalid pagination limits")

        response = []

        resources = Resource.objects.filter(provider=provider.current_organization)

        if pagination:
            x = int(pagination["offset"])
            y = x + int(pagination["size"])

            resources = resources[x:y]

        for res in resources:
            response.append(self.get_resource_info(res))

        return response
