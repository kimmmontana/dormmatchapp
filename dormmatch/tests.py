import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from stellar_sdk import Keypair, scval

from . import stellar
from .models import BookingStatus, DormAccommodation


def make_dorm(room_type="Shared", capacity=2, **kwargs):
    return DormAccommodation.objects.create(
        dorm_name=kwargs.pop("dorm_name", f"{room_type} Dorm"),
        dorm_loc="Manila",
        room_type=room_type,
        resident_capacity=capacity,
        price=Decimal("5000.00"),
        **kwargs,
    )


def make_user(username):
    return get_user_model().objects.create_user(username=username, email=f"{username}@example.com", password="pw")


def make_booking(user, dorm, status="Verify"):
    return BookingStatus.objects.create(
        user_id=user, dorm_id=dorm, amount=dorm.price, book_status=status, reference_payment="ABC123"
    )


class DormAccommodationModelTests(TestCase):
    def test_solo_room_must_have_capacity_of_one(self):
        dorm = DormAccommodation(
            dorm_name="Solo", dorm_loc="Manila", room_type="Solo", resident_capacity=2, price=Decimal("1.00")
        )
        with self.assertRaises(ValidationError) as ctx:
            dorm.full_clean()
        self.assertIn("resident_capacity", ctx.exception.message_dict)

    def test_solo_room_cannot_be_waiting(self):
        dorm = DormAccommodation(
            dorm_name="Solo",
            dorm_loc="Manila",
            room_type="Solo",
            resident_capacity=1,
            price=Decimal("1.00"),
            occupied_status="Waiting",
        )
        with self.assertRaises(ValidationError) as ctx:
            dorm.full_clean()
        self.assertIn("occupied_status", ctx.exception.message_dict)

    def test_solo_room_waitlist_is_not_applicable(self):
        dorm = make_dorm("Solo", 1)
        self.assertEqual(dorm.num_waitlist, "NOT APPLICABLE")

    def test_str(self):
        dorm = make_dorm("Shared", 2)
        self.assertEqual(str(dorm), f"{dorm.dorm_id}-DORM-SHARED")


class SoloBookingTests(TestCase):
    def setUp(self):
        self.dorm = make_dorm("Solo", 1)
        self.user = make_user("alice")

    def test_approving_marks_dorm_occupied(self):
        make_booking(self.user, self.dorm, "Approved")
        self.dorm.refresh_from_db()
        self.assertEqual(self.dorm.occupied_status, "Yes")

    def test_deleting_booking_frees_dorm(self):
        booking = make_booking(self.user, self.dorm, "Approved")
        booking.delete()
        self.dorm.refresh_from_db()
        self.assertEqual(self.dorm.occupied_status, "No")

    def test_solo_booking_cannot_be_waitlisted(self):
        booking = make_booking(self.user, self.dorm)
        booking.book_status = "Waitlisted"
        with self.assertRaises(ValidationError):
            booking.save()

    def test_cannot_approve_beyond_capacity(self):
        make_booking(self.user, self.dorm, "Approved")
        second = make_booking(make_user("bob"), self.dorm)
        second.book_status = "Approved"
        with self.assertRaises(ValidationError):
            second.save()


class SharedBookingTests(TestCase):
    def setUp(self):
        self.dorm = make_dorm("Shared", 2)
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_first_waitlisted_booking_sets_dorm_waiting(self):
        make_booking(self.alice, self.dorm, "Waitlisted")
        self.dorm.refresh_from_db()
        self.assertEqual(self.dorm.occupied_status, "Waiting")
        self.assertEqual(self.dorm.num_waitlist, "1")

    def test_reaching_capacity_approves_all_waitlisted(self):
        make_booking(self.alice, self.dorm, "Waitlisted")
        make_booking(self.bob, self.dorm, "Waitlisted")
        self.dorm.refresh_from_db()
        self.assertEqual(self.dorm.occupied_status, "Yes")
        self.assertEqual(
            list(BookingStatus.objects.filter(dorm_id=self.dorm).values_list("book_status", flat=True)),
            ["Approved", "Approved"],
        )

    def test_admin_cannot_approve_shared_booking_directly(self):
        booking = make_booking(self.alice, self.dorm)
        booking.book_status = "Approved"
        with self.assertRaises(ValidationError):
            booking.save()

    def test_deleting_booking_reverts_others_to_waitlisted(self):
        make_booking(self.alice, self.dorm, "Waitlisted")
        second = make_booking(self.bob, self.dorm, "Waitlisted")
        BookingStatus.objects.get(pk=second.pk).delete()

        self.dorm.refresh_from_db()
        self.assertEqual(self.dorm.occupied_status, "Waiting")
        self.assertEqual(BookingStatus.objects.get(user_id=self.alice).book_status, "Waitlisted")


class DormListViewTests(TestCase):
    def test_solo_list_shows_only_available_solo_dorms(self):
        available = make_dorm("Solo", 1, dorm_name="Available")
        make_dorm("Solo", 1, dorm_name="Taken", occupied_status="Yes")
        make_dorm("Shared", 2, dorm_name="Shared")

        response = self.client.get(reverse("solodorm"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["object_list"]), [available])

    def test_waitlist_shows_only_open_shared_dorms(self):
        open_dorm = make_dorm("Shared", 2, dorm_name="Open")
        make_dorm("Shared", 2, dorm_name="Full", occupied_status="Yes")
        make_dorm("Solo", 1, dorm_name="Solo")

        response = self.client.get(reverse("waitlist"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["object_list"]), [open_dorm])

    def test_public_pages_render(self):
        for name in ("home", "aboutus", "success"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)


class BookingViewTests(TestCase):
    def setUp(self):
        self.dorm = make_dorm("Solo", 1)
        self.user = make_user("alice")

    def test_detail_requires_login(self):
        url = reverse("solo_detail", args=[self.dorm.pk])
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_booking_uses_dorm_price_and_redirects(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("solo_detail", args=[self.dorm.pk]), {"reference_payment": "XYZ789"})
        self.assertRedirects(response, reverse("success"))

        booking = BookingStatus.objects.get()
        self.assertEqual(booking.user_id, self.user)
        self.assertEqual(booking.amount, self.dorm.price)
        self.assertEqual(booking.book_status, "Verify")

    def test_waitlist_booking(self):
        shared = make_dorm("Shared", 2)
        self.client.force_login(self.user)
        response = self.client.post(reverse("waitlist_detail", args=[shared.pk]), {"reference_payment": "XYZ789"})
        self.assertRedirects(response, reverse("success"))
        self.assertEqual(BookingStatus.objects.get().dorm_id, shared)

    def test_booking_status_lists_only_own_bookings(self):
        mine = make_booking(self.user, self.dorm)
        make_booking(make_user("bob"), make_dorm("Shared", 2))

        self.client.force_login(self.user)
        response = self.client.get(reverse("booking-status"))
        self.assertEqual(list(response.context["booking_status"]), [mine])


CONTRACT_ID = "CB3PBY7GGWEZFD35YSKUT65NSDYE3AVM7C5OCFXELOY6NJKHDUGMR2FQ"


@override_settings(STELLAR_CONTRACT_ID=CONTRACT_ID)
class StellarEnvelopeCheckTests(TestCase):
    """The server must only submit the exact `book` call it prepared."""

    def setUp(self):
        self.student = Keypair.random().public_key

    def build(self, source=None, contract=CONTRACT_ID, function="book", dorm_id=2, student=None):
        from stellar_sdk import Account, Network, TransactionBuilder

        tx = (
            TransactionBuilder(Account(source or self.student, 1), Network.TESTNET_NETWORK_PASSPHRASE, base_fee=100)
            .append_invoke_contract_function_op(
                contract, function, [scval.to_address(student or self.student), scval.to_uint32(dorm_id)]
            )
            .set_timeout(30)
            .build()
        )
        return tx

    def test_accepts_matching_transaction(self):
        stellar._check_booking_envelope(self.build(), self.student, 2)

    def test_rejects_tampered_transactions(self):
        other = Keypair.random().public_key
        cases = {
            "different dorm": self.build(dorm_id=1),
            "different function": self.build(function="cancel"),
            "different contract": self.build(contract="CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC"),
            "different student": self.build(student=other),
            "different source": self.build(source=other),
        }
        for name, envelope in cases.items():
            with self.subTest(name), self.assertRaises(stellar.StellarError):
                stellar._check_booking_envelope(envelope, self.student, 2)


@override_settings(STELLAR_CONTRACT_ID=CONTRACT_ID)
class StellarBookingViewTests(TestCase):
    def setUp(self):
        self.dorm = make_dorm("Shared", 2, chain_dorm_id=2, price_xlm=Decimal("0.5"))
        self.user = make_user("alice")
        self.address = Keypair.random().public_key
        self.client.force_login(self.user)

    def post(self, name, body):
        return self.client.post(reverse(name, args=[self.dorm.pk]), json.dumps(body), content_type="application/json")

    def test_detail_page_shows_wallet_payment(self):
        response = self.client.get(reverse("waitlist_detail", args=[self.dorm.pk]))
        self.assertContains(response, 'id="stellar-pay"')

    @override_settings(STELLAR_CONTRACT_ID="")
    def test_wallet_payment_hidden_when_disabled(self):
        response = self.client.get(reverse("waitlist_detail", args=[self.dorm.pk]))
        self.assertNotContains(response, 'id="stellar-pay"')

    @patch("dormmatch.stellar.build_booking_transaction", return_value="UNSIGNED_XDR")
    def test_prepare_returns_unsigned_transaction(self, build):
        response = self.post("stellar_prepare_booking", {"address": self.address})
        self.assertEqual(response.json(), {"xdr": "UNSIGNED_XDR"})
        build.assert_called_once_with(self.address, 2)

    def test_prepare_rejects_invalid_address(self):
        response = self.post("stellar_prepare_booking", {"address": "not-an-address"})
        self.assertEqual(response.status_code, 400)

    def test_prepare_rejects_dorm_not_on_chain(self):
        self.dorm.chain_dorm_id = None
        self.dorm.save()
        response = self.post("stellar_prepare_booking", {"address": self.address})
        self.assertEqual(response.status_code, 400)

    @patch("dormmatch.stellar.submit_booking_transaction", return_value=(7, "ab" * 32))
    def test_submit_records_booking(self, submit):
        response = self.post("stellar_submit_booking", {"address": self.address, "signed_xdr": "SIGNED"})
        self.assertEqual(response.json()["redirect"], reverse("success"))
        submit.assert_called_once_with("SIGNED", self.address, 2)

        booking = BookingStatus.objects.get()
        self.assertEqual(booking.chain_booking_id, 7)
        self.assertEqual(booking.user_id, self.user)
        self.assertEqual(booking.amount, self.dorm.price)
        self.assertEqual(booking.wallet_address, self.address)
        self.assertEqual(booking.reference_payment, "ABABAB")

    @patch("dormmatch.stellar.submit_booking_transaction", side_effect=stellar.StellarError("failed on-chain"))
    def test_submit_reports_failure(self, submit):
        response = self.post("stellar_submit_booking", {"address": self.address, "signed_xdr": "SIGNED"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BookingStatus.objects.exists())

    def test_endpoints_require_login(self):
        self.client.logout()
        response = self.post("stellar_prepare_booking", {"address": self.address})
        self.assertEqual(response.status_code, 302)


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        from io import StringIO
        from tempfile import TemporaryDirectory

        from django.core.management import call_command

        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            call_command("seed_demo", stdout=StringIO())
            call_command("seed_demo", stdout=StringIO())

        self.assertEqual(DormAccommodation.objects.count(), 4)
        self.assertEqual(BookingStatus.objects.filter(book_status="Waitlisted").count(), 2)
        self.assertEqual(DormAccommodation.objects.get(dorm_name="Class A Shared").occupied_status, "Waiting")


class BookingStatusBadgeTests(TestCase):
    def test_each_status_gets_a_visible_badge(self):
        dorm = make_dorm("Shared", 5)
        user = make_user("alice")
        expected = {"Verify": "bg-warning", "Waitlisted": "bg-info", "Declined": "bg-danger"}
        for status in expected:
            make_booking(user, dorm, status)

        self.client.force_login(user)
        response = self.client.get(reverse("booking-status"))
        for status, css in expected.items():
            self.assertContains(response, f'{css}{" text-dark" if css != "bg-danger" else ""}">{status}</span>')
