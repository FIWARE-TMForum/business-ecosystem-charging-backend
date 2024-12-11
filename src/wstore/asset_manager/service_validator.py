from logging import getLogger
from bson import ObjectId
from django.conf import settings
from django.core.exceptions import PermissionDenied

from wstore.asset_manager.service_inventory_upgrader import ServiceInventoryUpgrader
from wstore.asset_manager.catalog_validator import CatalogValidator
from wstore.asset_manager.errors import ServiceError
from wstore.asset_manager.models import Resource
from wstore.asset_manager.resource_plugins.decorators import (
    on_service_spec_attachment,
    on_service_spec_validation,
    on_service_spec_upgrade
)
from wstore.store_commons.database import DocumentLock
from wstore.store_commons.errors import ConflictError
from wstore.store_commons.rollback import downgrade_asset, downgrade_asset_pa, rollback
from wstore.store_commons.utils.url import is_valid_url
from wstore.store_commons.utils.version import is_lower_version, is_valid_version
from bson.errors import InvalidId
logger = getLogger("wstore.service_validator")
class ServiceValidator(CatalogValidator):

    def _get_asset_resouces(self, asset_id):
        try:
            # Use the asset_id to retrieve the asset linked in service spec characteristic
            resource_asset = Resource.objects.get(pk=ObjectId(asset_id)) if asset_id else None
        except Resource.DoesNotExist:
            raise ServiceError("The asset id included in the service specification is not valid")
        except InvalidId:
            raise ServiceError("Invalid asset id")      
        except Exception as e:
            print(type(e).__name__)
            logger.error(f"_get_asset_resources:{e}")
            #For security we cannot pass all error messages to the user 
            raise ServiceError("Error retrieving the asset or the asset type, check charging backend for further details.")

        return resource_asset

    def _validate_service_characteristics(self, asset, provider, asset_t, media_type, location):
        print("_validate_spec_characteristic")
        if asset.provider != provider:
            raise PermissionDenied(
                "You are not authorized to use the digital asset specified in the location characteristic"
            )
        print(location)
        print(asset.download_link)
        if asset.download_link != location:
            raise ServiceError("The location specified is different from the one in the asset")

        if asset.resource_type != asset_t:
            raise ServiceError("The specified asset type does not match the asset's current type")

        if asset.content_type.lower() != media_type.lower():
            raise ServiceError("The provided media type characteristic is different from the asset one")

        if asset.is_public:
            raise ServiceError("It is not allowed to create services with public assets")

    # rp: from ResourcePlugin model, resource: from Resource model and without prefix: service spec chars
    @on_service_spec_validation
    def _validate_service(self, provider, rp_asset, media_type, url, asset_id):
        print("Entra en _validate_service 2")
        
        # Validate location format
        if not is_valid_url(url):
            raise ServiceError("The location characteristic included in the service specification is not a valid URL")

        resource_asset = self._get_asset_resouces(asset_id)

        if resource_asset:
            # Check if the asset is already registered
            print("asset dentro de mongo")
            asset = resource_asset
            if resource_asset.service_spec_id is not None:
                raise ServiceError(
                    "There is already an existing service specification defined for the given digital asset"
                )
            print("validate spec characteristic")
            # rp_asset.name is the same as asset_type from service spec, decorator checked it
            self._validate_service_characteristics(resource_asset, provider, rp_asset.name, media_type, url)
            print("start save")
            resource_asset.has_terms = self._has_terms
            resource_asset.save()
            print("end save")
        else:
            print("asset no incluido aún")
            # The asset is not yet included, this option is only valid for URL assets without metadata
            site = settings.SITE
            if "FILE" in rp_asset.formats and (
                ("URL" not in rp_asset.formats) or 
                ("URL" in rp_asset.formats and url.startswith(site))
            ):
                raise ServiceError(
                    "The URL specified in the location characteristic does not point to a valid digital asset"
                )
            # URL must be included in asset type for direct asset creation
            if "URL" not in rp_asset.formats:
                raise ServiceError("The asset should support URL format")
            
            if rp_asset.form:
                raise ServiceError("Automatic creation of digital assets with metadata is not supported")

            # Validate media type
            if len(rp_asset.media_types) and media_type.lower() not in [
                media.lower() for media in rp_asset.media_types
            ]:
                raise ServiceError(
                    "The media type characteristic included in the service specification is not valid for the given asset type"
                )

            # Create the new asset model
            asset = Resource.objects.create(
                has_terms=self._has_terms,
                resource_path="",
                download_link=url,
                provider=provider,
                content_type=media_type,
            )
        # The asset model is included to the rollback list so if an exception is raised in the plugin post validation
        # the asset model would be deleted
        print("start rollback")
        self.rollback_logger["models"].append(asset) # type: ignore
        print("return _validate_service")
        return asset

    @on_service_spec_attachment
    def _attach_service_info(self, asset, asset_t, service_spec):
        # Complete asset information
        asset.service_spec_id = service_spec["id"]
        asset.version = service_spec["version"]
        asset.resource_type = asset_t
        asset.state = "attached"
        asset.save()
        print("saved")

    @rollback()
    def attach_info(self, provider, service_spec):
        print("attach_info")
        print(service_spec)
        print("-----------------------")
        # Get the digital asset
        asset_t, media_type, url, asset_id = self.parse_spec_characteristics(service_spec)
        print(asset_t)
        print(media_type)
        print(url)
        print(asset_id)
        is_digital = asset_t is not None and media_type is not None and url is not None
        print("digital check")
        if is_digital:
            try:
                print("get asset id")
                resource_asset = Resource.objects.get(pk=ObjectId(asset_id))
                # TODO: Drop the service object from the catalog in case of error
                self.rollback_logger["models"].append(resource_asset) # type: ignore

                # The asset is a digital service
                self._attach_service_info(resource_asset, asset_t, service_spec)
            except Resource.DoesNotExist:
                raise ServiceError("The asset included doesn't exist")
            except InvalidId:
                raise ServiceError("invalid asset id")
        else:
            raise ServiceError("The asset included doesn't exist")
        print("return attach_info")

    def _get_upgrading_asset(self, asset_id):
        print(asset_id)
        resource_asset = self._get_asset_resouces( asset_id)

        if not resource_asset:
            raise ServiceError(
                "Invalid asset_id"
            )
        # Lock the access to the asset
        lock = DocumentLock("wstore_resource", resource_asset.pk, "asset")
        lock.wait_document()

        resource_asset = Resource.objects.get(pk=resource_asset.pk)

        return resource_asset, lock

    @rollback(downgrade_asset_pa)
    def validate_upgrade(self, provider, service_spec):
        print("inicio validate_upgrade")
        print("serviceSpec")
        print(service_spec)
        if "version" in service_spec and "specCharacteristic" in service_spec:
            # Extract service needed characteristics
            asset_t, media_type, url, asset_id = self.parse_spec_characteristics(service_spec)
            is_digital = asset_t is not None and media_type is not None and url is not None

            if is_digital:
                print("get_upgrading_asset")
                lock = None
                try:
                    resource_asset, lock = self._get_upgrading_asset( asset_id)
                    
                    print("validando upgrading state")
                    # Check that the asset is in upgrading state
                    if resource_asset.state != "upgrading":
                        raise ServiceError("There is not a new version of the specified digital asset")     
                    self._to_downgrade = resource_asset
                    print("validate service char")
                    self._validate_service_characteristics(resource_asset, provider, asset_t, media_type, url)

                    print("is valid version 1")
                    # Check service version
                    if not is_valid_version(service_spec["version"]):
                        raise ServiceError("The field version does not have a valid format")

                    print("is valid version 2")
                    print(resource_asset.old_versions[-1]["version"])
                    if resource_asset.old_versions and len(resource_asset.old_versions)>0 and not is_lower_version(resource_asset.old_versions[-1]["version"], service_spec["version"]):
                        raise ServiceError("The provided version is not higher that the previous one")

                    print("validando id de asset y service spec")
                    if resource_asset.service_spec_id != service_spec["id"]:
                        raise ServiceError("The specified digital asset is included in other service spec")

                    # Attach new info
                    resource_asset.version = service_spec["version"]
                    resource_asset.save()
                finally:
                    # Release asset lock
                    if lock is not None:
                        lock.unlock_document()
        print("final validate_upgrade")

    @on_service_spec_upgrade
    def _notify_service_upgrade(self, asset, asset_t, service_spec):
        # Update existing inventory services to include new version asset info
        upgrader = ServiceInventoryUpgrader(asset)
        upgrader.start()
        print("updated inventory")

        # Set the asset status to attached
        asset.state = "attached"
        asset.save()

    def attach_upgrade(self, provider, service_spec):
        print("inicio attach_upgrade")
        print(service_spec)
        asset_t, media_type, url, asset_id = self.parse_spec_characteristics(service_spec)
        is_digital = asset_t is not None and media_type is not None and url is not None

        if is_digital:
            lock=None
            try:
                print("get_upgrading_asset")
                asset, lock = self._get_upgrading_asset(asset_id)
                print("notify_upgrading_asset")
                self._notify_service_upgrade(asset, asset_t, service_spec)
            finally:
                # Release asset lock
                if lock is not None:
                    lock.unlock_document()
        print("final attach_upgrade")
        return service_spec

    def _rollback_handler(self, provider, service_spec, rollback_method):
        asset_t, media_type, url, asset_id = self.parse_spec_characteristics(service_spec)
        is_digital = asset_t is not None and media_type is not None and url is not None

        if is_digital:
            resource_asset = self._get_asset_resouces(asset_id)
            if resource_asset:
                self._validate_service_characteristics(resource_asset, provider, asset_t, media_type, url)
                rollback_method(resource_asset)
            else:
                raise ServiceError("Cannot rollback an asset with invalid id")

    def rollback_create(self, provider, service_spec):
        def rollback_method(asset):
            if asset.service_spec_id is None:
                asset.delete()

        self._rollback_handler(provider, service_spec, rollback_method)

    def rollback_upgrade(self, provider, service_spec):
        def rollback_method(asset):
            if asset.service_spec_id == service_spec["id"] and asset.state == "upgrading":
                downgrade_asset(asset)

        self._rollback_handler(provider, service_spec, rollback_method)

    @rollback()
    def validate_creation(self, provider, service_spec):
        print("Entra en validate_creation")
        # Extract service needed characteristics
        asset_t, media_type, url, asset_id = self.parse_spec_characteristics(service_spec)
        is_digital = asset_t is not None and media_type is not None and url is not None
        print(asset_t)
        print(media_type)
        print(url)
        print(asset_id)
        # Service spec bundles do not exist
        if "isBundle" in service_spec and service_spec["isBundle"]:
            print("ValidateCreation Service Error")
            raise ServiceError("Service spec bundles are not supported")
        if is_digital:
            print("Entra en _validate_service 1")
            asset = self._validate_service(provider, asset_t, media_type, url, asset_id)
            print(f"asset id validate creation: {str(asset._id)}")
            if asset_id is None:
                return {"id": str(asset._id)}
        
            