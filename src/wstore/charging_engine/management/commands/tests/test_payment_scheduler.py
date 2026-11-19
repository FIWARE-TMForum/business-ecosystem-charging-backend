import datetime

from django.test import SimpleTestCase, TestCase, override_settings
from mock import MagicMock, call, patch

from wstore.charging_engine.management.commands import payment_scheduler


class PaymentSchedulerTestCase(TestCase):
    tags = ("payment-scheduler",)

    def setUp(self):
        self.command = payment_scheduler.Command()
        self.command._billing_client = MagicMock()
        self.command._inventory_client = MagicMock()
        self.command._get_payment_info_from_cb = MagicMock(
            return_value=("redsys", "pre-auth-id")
        )
        self.command._billing_client.get_product_id_by_cb.return_value = None

        self.client = MagicMock()
        self.client.NAME = "redsys"
        self.client_class = MagicMock(return_value=self.client)

        self.real_does_not_exist = payment_scheduler.PaymentRecord.DoesNotExist

        self.payment_record = MagicMock()
        self.payment_record.DoesNotExist = self.real_does_not_exist

        self.payment_record_patch = patch.object(
            payment_scheduler,
            "PaymentRecord",
            self.payment_record,
        )
        self.payment_client_patch = patch.object(
            payment_scheduler.PaymentClient,
            "get_payment_client_class",
            return_value=self.client_class,
        )

        self.payment_record_patch.start()
        self.payment_client_patch.start()
        self.addCleanup(self.payment_record_patch.stop)
        self.addCleanup(self.payment_client_patch.stop)

        self.cb = {
            "id": "cb-1",
            "taxIncludedAmount": {
                "value": 18.39,
                "unit": "EUR",
            },
        }

    def test_new_cb_passes_none_and_client_creates_record(self):
        record = MagicMock(
            customerBill_id="cb-1", payment_type="redsys", payment_reference="redsys-payment-1", retry_count=0, pk=None
        )
        self.payment_record.get_by_customer_bill_id.side_effect = [self.real_does_not_exist, record]
        self.client.charge_recurring.return_value = ("redsys-payment-1", "succeeded")

        self.command._process_cb(self.cb)

        self.client.charge_recurring.assert_called_once_with(self.cb, None, "pre-auth-id", 18.39, "EUR")
        self.payment_record.update_payment_reference.assert_not_called()
        self.command._billing_client.set_customer_bill.assert_called_once_with("settled", "cb-1")

    @override_settings(PAYMENT_RECOVERY_GRACE_HOURS=72)
    def test_failed_payment_retries_with_pre_auth_and_updates_reference(self):
        record = MagicMock(
            customerBill_id="cb-1", payment_type="redsys", payment_reference="redsys-payment-old", retry_count=1,
            first_failed_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
        )
        self.payment_record.get_by_customer_bill_id.return_value = record
        self.client.check_payment_status.return_value = "failed"
        self.client.charge_recurring.return_value = ("redsys-payment-new", "succeeded")

        self.command._process_cb(self.cb)

        self.client.check_payment_status.assert_called_once_with("redsys-payment-old")
        self.client.charge_recurring.assert_called_once_with(self.cb, record, "pre-auth-id", 18.39, "EUR")
        self.payment_record.update_payment_reference.assert_not_called()

    def test_pending_payment_is_checked_without_starting_another_payment(self):
        record = MagicMock(customerBill_id="cb-1", payment_type="redsys", payment_reference="redsys-payment-1")
        self.payment_record.get_by_customer_bill_id.return_value = record
        self.client.check_payment_status.return_value = "pending"

        self.command._process_cb(self.cb)

        self.client.check_payment_status.assert_called_once_with("redsys-payment-1")
        self.client.charge_recurring.assert_not_called()
        self.command._get_payment_info_from_cb.assert_not_called()
        self.command._billing_client.set_customer_bill.assert_not_called()

    def test_succeeded_payment_is_settled_without_starting_another_payment(self):
        record = MagicMock(customerBill_id="cb-1", payment_type="redsys", payment_reference="redsys-payment-1")
        self.payment_record.get_by_customer_bill_id.return_value = record
        self.client.check_payment_status.return_value = "succeeded"

        self.command._process_cb(self.cb)

        self.client.check_payment_status.assert_called_once_with("redsys-payment-1")
        self.client.charge_recurring.assert_not_called()
        self.command._billing_client.set_customer_bill.assert_called_once_with("settled", "cb-1")

    def test_attempt_without_reference_does_not_increment_retry(self):
        self.payment_record.get_by_customer_bill_id.side_effect = self.real_does_not_exist
        self.client.charge_recurring.return_value = (None, "failed")

        self.command._process_cb(self.cb)

        self.client.charge_recurring.assert_called_once_with(self.cb, None, "pre-auth-id", 18.39, "EUR")
        self.payment_record.increment_retry_count.assert_not_called()
        self.command._billing_client.set_customer_bill.assert_not_called()

    def test_get_payment_info_reads_redsys_pre_authorization(self):
        command = payment_scheduler.Command()
        command._billing_client = MagicMock()
        command._inventory_client = MagicMock()
        command._billing_client.get_product_id_by_cb.return_value = "product-1"
        command._inventory_client.get_product.return_value = {
            "productCharacteristic": [
                {
                    "name": "redsysPreAuthorizationId",
                    "value": "redsys-token:cof-transaction",
                }
            ]
        }

        payment_type, pre_auth_id = command._get_payment_info_from_cb("cb-1")

        self.assertEqual(payment_type, "redsys")
        self.assertEqual(pre_auth_id, "redsys-token:cof-transaction")


@override_settings(PAYMENT_RECOVERY_GRACE_HOURS=72)
class PaymentRecoveryTestCase(SimpleTestCase):
    def setUp(self):
        PaymentSchedulerTestCase.setUp(self)
        pending = patch.object(payment_scheduler.PendingTermination, 'objects')
        self.pending = pending.start()
        self.addCleanup(pending.stop)
        self.pending.filter.return_value.exists.return_value = False
        self.command._billing_client.get_product_id_by_cb.return_value = "product-1"
        self.command._inventory_client.get_product.return_value = {"id": "product-1", "status": "active"}
        self.cb['billDate'] = '2020-01-01T00:00:00Z'
        self.record = MagicMock(
            payment_type='redsys', payment_reference='payment-1',
            first_failed_at=datetime.datetime(2026, 6, 1),
        )
        def mark_failed(failed_at):
            if self.record.first_failed_at is None:
                self.record.first_failed_at = failed_at
        self.record.mark_failed.side_effect = mark_failed
        self.payment_record.get_by_customer_bill_id.return_value = self.record
        self.client.check_payment_status.return_value = 'failed'
        self.client.charge_recurring.return_value = ('payment-2', 'succeeded')
        clock = patch.object(payment_scheduler.datetime, 'datetime', wraps=datetime.datetime)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        self.clock.now.return_value = datetime.datetime(2026, 6, 4, tzinfo=datetime.timezone.utc)

    def test_failed_payment_at_deadline_terminates_whole_product_then_closes_bill(self):
        operations = MagicMock()
        operations.attach_mock(self.command._inventory_client.terminate_product, 'terminate')
        operations.attach_mock(self.command._billing_client.close_unpaid_customer_bill, 'close')
        self.command._process_cb(self.cb)
        self.assertEqual(operations.mock_calls, [
            call.terminate('product-1'),
            call.close(self.cb),
        ])
        self.client.charge_recurring.assert_not_called()
        self.command._billing_client.set_customer_bill.assert_not_called()

    def test_failed_payment_before_deadline_uses_existing_retry(self):
        self.clock.now.return_value -= datetime.timedelta(seconds=1)
        self.command._process_cb(self.cb)
        self.client.charge_recurring.assert_called_once_with(self.cb, self.record, 'pre-auth-id', 18.39, 'EUR')
        self.command._inventory_client.terminate_product.assert_not_called()

    def test_pending_after_deadline_only_checks_existing_attempt(self):
        self.client.check_payment_status.return_value = 'pending'
        self.command._process_cb(self.cb)
        self.command._inventory_client.get_product.assert_not_called()
        self.command._inventory_client.terminate_product.assert_not_called()
        self.command._billing_client.close_unpaid_customer_bill.assert_not_called()
        self.client.charge_recurring.assert_not_called()
        self.record.mark_failed.assert_not_called()

    def test_pending_attempt_must_finish_before_expired_recovery_terminates(self):
        self.client.check_payment_status.side_effect = ['pending', 'failed']
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_not_called()
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_called_once_with('product-1')
        self.client.charge_recurring.assert_not_called()

    def test_success_after_deadline_settles_without_termination(self):
        self.client.check_payment_status.return_value = 'succeeded'
        self.command._process_cb(self.cb)
        self.command._billing_client.set_customer_bill.assert_called_once_with('settled', 'cb-1')
        self.command._inventory_client.terminate_product.assert_not_called()
        self.record.mark_failed.assert_not_called()

    def test_overdue_bill_without_attempt_requests_payment_without_expiring_recovery(self):
        self.payment_record.get_by_customer_bill_id.side_effect = [self.real_does_not_exist, self.record]
        self.command._process_cb(self.cb)
        self.client.charge_recurring.assert_called_once_with(self.cb, None, 'pre-auth-id', 18.39, 'EUR')
        self.client.check_payment_status.assert_not_called()
        self.command._inventory_client.get_product.assert_not_called()
        self.command._inventory_client.terminate_product.assert_not_called()
        self.command._billing_client.get_acbrs_by_cb.assert_not_called()
        self.command._billing_client.close_unpaid_customer_bill.assert_not_called()

    def test_expired_failure_terminates_without_reading_rates(self):
        self.command._billing_client.get_acbrs_by_cb.side_effect = AssertionError('Rates must not be fetched')
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_called_once_with('product-1')
        self.command._billing_client.close_unpaid_customer_bill.assert_called_once_with(self.cb)

    def test_termination_failure_preserves_bill_for_recovery(self):
        self.command._inventory_client.terminate_product.side_effect = RuntimeError('inventory operation failed')
        with self.assertRaises(RuntimeError):
            self.command._process_cb(self.cb)
        self.command._billing_client.close_unpaid_customer_bill.assert_not_called()
        self.client.charge_recurring.assert_not_called()

    def test_already_terminated_product_finishes_bill_cleanup_without_retermination(self):
        self.command._inventory_client.get_product.return_value['status'] = 'terminated'
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_not_called()
        self.command._billing_client.close_unpaid_customer_bill.assert_called_once()
        self.command._billing_client.get_acbrs_by_cb.assert_not_called()
        self.client.charge_recurring.assert_not_called()

    def test_existing_pending_termination_closes_bill_without_duplicate_termination(self):
        self.pending.filter.return_value.exists.return_value = True
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_not_called()
        self.command._billing_client.close_unpaid_customer_bill.assert_called_once_with(self.cb)
        self.client.charge_recurring.assert_not_called()

    def test_bill_cleanup_failure_is_retried_without_reterminating_product(self):
        self.command._billing_client.close_unpaid_customer_bill.side_effect = RuntimeError('billing unavailable')
        with self.assertRaises(RuntimeError):
            self.command._process_cb(self.cb)
        self.command._inventory_client.get_product.return_value['status'] = 'terminated'
        self.command._billing_client.close_unpaid_customer_bill.side_effect = None
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_called_once()
        self.assertEqual(self.command._billing_client.close_unpaid_customer_bill.call_count, 2)

    def test_expired_recurring_payment_does_not_require_active_product_status(self):
        self.command._inventory_client.get_product.return_value['status'] = 'created'
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_called_once_with('product-1')
        self.client.charge_recurring.assert_not_called()

    def test_bill_without_date_still_uses_payment_failure_time(self):
        del self.cb['billDate']
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_called_once()
        self.client.charge_recurring.assert_not_called()

    def test_old_bill_first_observed_failure_gets_full_recovery_window(self):
        self.record.first_failed_at = None
        self.command._process_cb(self.cb)
        self.assertEqual(self.record.first_failed_at, datetime.datetime(2026, 6, 4))
        self.record.mark_failed.assert_called_once_with(datetime.datetime(2026, 6, 4))
        self.command._inventory_client.terminate_product.assert_not_called()
        self.client.charge_recurring.assert_called_once()

    def test_immediately_failed_first_attempt_records_failure_time(self):
        self.record.first_failed_at = None
        self.payment_record.get_by_customer_bill_id.side_effect = [self.real_does_not_exist, self.record]
        self.client.charge_recurring.return_value = ('payment-1', 'failed')
        self.command._process_cb(self.cb)
        self.assertEqual(self.record.first_failed_at, datetime.datetime(2026, 6, 4))
        self.record.mark_failed.assert_called_once_with(datetime.datetime(2026, 6, 4))
        self.command._inventory_client.terminate_product.assert_not_called()

    def test_immediately_pending_first_attempt_does_not_start_failure_window(self):
        self.record.first_failed_at = None
        self.payment_record.get_by_customer_bill_id.side_effect = [self.real_does_not_exist, self.record]
        self.client.charge_recurring.return_value = ('payment-1', 'pending')
        self.command._process_cb(self.cb)
        self.record.mark_failed.assert_not_called()
        self.assertIsNone(self.record.first_failed_at)

    def test_failed_retries_do_not_reset_failure_window(self):
        self.record.first_failed_at = None
        self.client.charge_recurring.return_value = ('payment-2', 'failed')
        self.command._process_cb(self.cb)
        self.clock.now.return_value = datetime.datetime(2026, 6, 5, tzinfo=datetime.timezone.utc)
        self.command._process_cb(self.cb)
        self.assertEqual(self.record.first_failed_at, datetime.datetime(2026, 6, 4))
        self.clock.now.return_value = datetime.datetime(2026, 6, 7, tzinfo=datetime.timezone.utc)
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_called_once()
        self.assertEqual(self.client.charge_recurring.call_count, 2)

    @override_settings(PAYMENT_RECOVERY_GRACE_HOURS=12)
    def test_configured_shorter_window_is_applied(self):
        self.clock.now.return_value = datetime.datetime(2026, 6, 1, 12, tzinfo=datetime.timezone.utc)
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_called_once()

    def test_recovery_compares_naive_utc_timestamps(self):
        self.record.first_failed_at = datetime.datetime(2026, 6, 1)
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_called_once()

    def test_bill_date_is_not_used_for_recovery_deadline(self):
        self.cb['billDate'] = 'not-a-date'
        self.command._process_cb(self.cb)
        self.command._inventory_client.terminate_product.assert_called_once()

    def test_all_bill_pages_are_read_before_states_are_changed(self):
        first_page = [{'id': str(index)} for index in range(100)]
        last_page = [{'id': 'last'}]
        self.command._billing_client.get_customer_bills_by_state.side_effect = [first_page, last_page]
        def process(cb):
            self.assertEqual(self.command._billing_client.get_customer_bills_by_state.call_count, 2)
        self.command._process_cb = MagicMock(side_effect=process)
        self.command.handle()
        self.assertEqual(self.command._process_cb.call_count, 101)
