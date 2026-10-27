from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand

from dormmatch.models import BookingStatus, DormAccommodation

# chain_dorm_id matches the dorms already listed on the testnet contract
# (blockchain/deployments/testnet.json).
DORMS = [
    {"dorm_name": "Class A Solo", "dorm_loc": "Manila", "room_type": "Solo", "resident_capacity": 1,
     "price": "8500.00", "price_xlm": "0.5", "chain_dorm_id": 1, "image": "class-a-solo.jpg",
     "description": "A private air-conditioned room with its own study desk, closet, and bathroom."},
    {"dorm_name": "Class B Solo", "dorm_loc": "Sampaloc, Manila", "room_type": "Solo", "resident_capacity": 1,
     "price": "6500.00", "price_xlm": None, "chain_dorm_id": None, "image": "class-b-solo.jpg",
     "description": "A cozy single room with a shared bathroom, a short walk from the university belt."},
    {"dorm_name": "Class A Shared", "dorm_loc": "Katipunan, Quezon City", "room_type": "Shared", "resident_capacity": 4,
     "price": "4500.00", "price_xlm": None, "chain_dorm_id": None, "image": "class-a-shared.jpg",
     "description": "A spacious four-person room with individual lockers and a common study area."},
    {"dorm_name": "Class B Shared", "dorm_loc": "Quezon City", "room_type": "Shared", "resident_capacity": 2,
     "price": "3500.00", "price_xlm": "0.5", "chain_dorm_id": 2, "image": "class-b-shared.png",
     "description": "An affordable two-person room, ideal for friends or classmates."},
]

STUDENTS = [
    {"username": "maria", "first_name": "Maria", "last_name": "Santos", "gender": "Cisgender Female",
     "birthday": date(2004, 3, 14), "school": "University of Santo Tomas", "degree_program": "BS Nursing"},
    {"username": "paolo", "first_name": "Paolo", "last_name": "Reyes", "gender": "Cisgender Male",
     "birthday": date(2003, 8, 2), "school": "Ateneo de Manila University", "degree_program": "BS Computer Science"},
]


class Command(BaseCommand):
    help = "Load sample dorms, students, and bookings for local development and demos."

    def handle(self, *args, **options):
        images = settings.BASE_DIR / "static" / "images"
        dorms = {}
        for data in DORMS:
            data = dict(data)
            image = data.pop("image")
            dorm, created = DormAccommodation.objects.get_or_create(
                dorm_name=data["dorm_name"],
                defaults={**data, "price": Decimal(data["price"]),
                          "price_xlm": Decimal(data["price_xlm"]) if data["price_xlm"] else None},
            )
            if created:
                with open(images / image, "rb") as fh:
                    dorm.image.save(image, File(fh), save=True)
            dorms[dorm.dorm_name] = dorm
            self.stdout.write(f"{'Created' if created else 'Exists '} dorm {dorm.dorm_name}")

        User = get_user_model()
        for data in STUDENTS:
            user, created = User.objects.get_or_create(
                username=data["username"],
                defaults={**data, "email": f"{data['username']}@example.com", "contact_number": "09170000000"},
            )
            if created:
                user.set_password("demo-pass-123")
                user.save()
                BookingStatus.objects.create(
                    user_id=user, dorm_id=dorms["Class A Shared"], amount=dorms["Class A Shared"].price,
                    book_status="Waitlisted", reference_payment="DEMO01",
                )
            self.stdout.write(f"{'Created' if created else 'Exists '} student {user.username}")

        self.stdout.write(self.style.SUCCESS("Demo data ready. Student logins use the password demo-pass-123."))
