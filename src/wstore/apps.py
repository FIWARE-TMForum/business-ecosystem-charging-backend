from django.apps import AppConfig
import logging

logger = logging.getLogger("wstore.default_logger")


def register_signals():
    from django.contrib.auth.models import User
    from django.db.models.signals import post_save
    from django.dispatch import receiver

    @receiver(post_save, sender=User, dispatch_uid="user_profile")
    def create_user_profile(sender, instance, created, **kwargs):
        from wstore.models import Organization, UserProfile

        if created:
            # Create a private organization for the user
            default_organization = Organization.objects.get_or_create(name=instance.username)
            default_organization[0].managers.append(instance.pk)
            default_organization[0].save()

            profile, created = UserProfile.objects.get_or_create(
                user=instance,
                current_roles=["customer"],
                current_organization=default_organization[0],
            )
            if instance.first_name and instance.last_name:
                profile.complete_name = instance.first_name + " " + instance.last_name
                profile.save()


class WstoreConfig(AppConfig):
    name = "wstore"
    verbose_name = "WStore"

    def ready(self):
        import sys

        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        from wstore.models import Context
        from wstore.store_commons.utils.url import is_valid_url

        # Creates a new user profile when an user is created
        # post_save.connect(create_user_profile, sender=User)
        register_signals()

        testing = sys.argv[1:2] == ["test"] or sys.argv[1:2] == ["migrate"]
        if not testing:
            # Validate that a correct site and local_site has been provided
            if not is_valid_url(settings.SITE) or not is_valid_url(settings.LOCAL_SITE):
                raise ImproperlyConfigured("SITE and LOCAL_SITE settings must be a valid URL")

            # Create context object if it does not exists
            if not len(Context.objects.all()):
                Context.objects.create(failed_cdrs=[], failed_upgrades=[])

            self._create_indexes()
            self._start_webhook_listener()

    def _create_indexes(self):
        """Create MongoDB indexes for performance optimization"""
        try:
            from wstore.store_commons.database import get_database_connection

            db = get_database_connection()

            existing_indexes = db.wstore_order.index_information()

            if 'customer_bill_idx' not in existing_indexes:
                # index the customerBill element inside Order.contract to speed up the searching
                db.wstore_order.create_index(
                [("contracts.customer_bill.id", 1)],
                name="customer_bill_idx"
                )
                logger.info("Created customer_bill_idx index on wstore_order")

        except Exception as e:
            # Don't fail startup if index creation fails
            logger.warning(f"Could not create indexes: {e}")

    def _start_webhook_listener(self):
        """Initialize customer bill webhook listener and workers"""
        try:
            from wstore.charging_engine.cb_webhook.cb_workers_service import CBWorkersService

            service = CBWorkersService()
            service.start()
            service.listen()

            logger.info("Customer bill webhook listener started successfully")

        except Exception as e:
            logger.warning(f"FAILED starting customer bill webhook listener: {e}")
            raise Exception("Webhook startup failure")
