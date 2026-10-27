<div align="center">

# DormMatch

**Find, book and share student dormitories, without the stress.**

A Django web app for browsing solo rooms and shared dorms, joining a waitlist to be matched with roommates, and tracking every booking from payment to approval.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-4.0-092E20?logo=django&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5-7952B3?logo=bootstrap&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)

[Features](#features) · [Quick start](#quick-start) · [How booking works](#how-booking-works) · [Project structure](#project-structure) · [Admin guide](#admin-guide)

</div>

---

## Overview

DormMatch gives students one place to find housing near their school. Students sign up with their school and degree program, browse available rooms, and book with a payment reference. Shared rooms use a **waitlist**: students who book the same shared dorm are grouped as roommates, and the room is approved for everyone once it reaches capacity. Admins verify payments and manage listings from the Django admin.

## Features

| | |
| --- | --- |
| 🏠 **Solo dorms** | Browse private rooms that are still available and book one directly. |
| 👥 **Shared dorms and waitlist** | Join a shared room's waitlist, see who else is waitlisted, and get approved together when the room fills. |
| 💳 **Payment reference booking** | Each booking records the dorm price and a payment reference for the admin to verify. |
| 📋 **Booking status** | Signed-in students see each of their bookings with its date, time, amount and status. |
| 🎓 **Student profiles** | A custom user model with school, degree program, gender, birthday (age is computed) and contact number. |
| 🛠️ **Admin dashboard** | Manage dorms, photos, capacity and bookings, with validation that keeps room status consistent. |

## Tech stack

- **Backend:** Python, Django 4.0 (class-based views, custom user model)
- **Database:** SQLite (default Django setup)
- **Frontend:** Django templates, Bootstrap 5, custom CSS
- **Media:** Pillow for dorm photos
- **Config:** python-dotenv for environment variables

## Quick start

**Prerequisites:** Python 3.10+ and Git.

```sh
# 1. Clone
git clone https://github.com/kimmmontana/dormmatchapp.git
cd dormmatchapp

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure the secret key
cp .env.example .env               # Windows: copy .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# paste the printed value after DJANGO_SECRET_KEY= in .env

# 5. Set up the database and an admin account
python manage.py migrate
python manage.py createsuperuser

# 6. Run
python manage.py runserver
```

Open **http://127.0.0.1:8000**. The admin panel is at **http://127.0.0.1:8000/admin/**. Add a few dorms there first so the listings have something to show.

### Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Yes | Django's secret key. The app refuses to start without it. |

## How booking works

```
Student                                   Admin
───────                                   ─────
Sign up / log in
Browse Solo dorms or Shared dorms
Open a dorm → submit payment reference
        │
        ▼
   Booking: Verify  ───────────────────►  Checks the payment
                                              │
             ┌────────────────────────────────┴───────────────────────┐
             ▼ Solo room                                              ▼ Shared room
   Admin sets Approved                                   Admin sets Waitlisted
   → dorm marked occupied                                → dorm waitlist count goes up
                                                         → dorm status becomes "Waiting"
                                                         → when waitlist = capacity:
                                                            every waitlisted booking → Approved
                                                            dorm marked occupied
```

**Rules the app enforces**

- A solo room always has a capacity of 1, and its bookings can't be waitlisted.
- A shared booking can't be approved by hand. It's approved automatically when the room fills.
- A dorm can't take more approved bookings than its capacity.
- Deleting a booking reverses its effect: a solo room becomes available again, and a full shared room returns its bookings to the waitlist and recounts it.
- Fully occupied dorms are hidden from the listings.

## Pages

| Route | Page | Sign-in |
| --- | --- | --- |
| `/` | Home | No |
| `/solodorm/` | Available solo dorms | No |
| `/solodorm/<id>/` | Solo dorm details and booking | Yes |
| `/waitlist/` | Available shared dorms | No |
| `/waitlist/<id>/` | Shared dorm details, current waitlist and booking | Yes |
| `/booking-status/` | Your bookings | Yes |
| `/aboutus/` | About DormMatch | No |
| `/accounts/signup/`, `/accounts/login/`, `/accounts/logout/` | Authentication | |
| `/admin/` | Django admin | Staff |

## Data model

| Model | Key fields |
| --- | --- |
| `CustomUser` (`accounts`) | `username`, `first_name`, `last_name`, `suffix`, `birthday`, `gender`, `contact_number`, `email`, `school`, `degree_program` |
| `DormAccommodation` (`dormmatch`) | `dorm_name`, `dorm_loc`, `room_type` (Solo / Shared), `resident_capacity`, `occupied_status` (No / Waiting / Yes), `price`, `description`, `num_waitlist`, `image` |
| `BookingStatus` (`dormmatch`) | `user_id`, `dorm_id`, `amount`, `reference_payment`, `book_status` (Verify / Waitlisted / Approved / Declined), `booking_date`, `booking_time` |

## Project structure

```
dormmatchapp/
├── accounts/          Custom user model, sign-up form and views
├── dormmatch/         Dorms, bookings, waitlist logic, views and admin
├── django_project/    Settings, root URLs, WSGI/ASGI
├── templates/         Page templates (home, listings, details, booking status, auth)
├── static/            CSS and vendored Bootstrap
├── manage.py
├── requirements.txt
└── .env.example
```

## Admin guide

1. Log in at `/admin/` with the superuser account.
2. **Add a dorm** under *Dorm accommodations*. Choose Solo (capacity 1) or Shared, set the price and upload a photo.
3. **Review bookings** under *Booking statuses*. New bookings arrive as **Verify**.
   - Solo: set **Approved** once the payment checks out, or **Declined**.
   - Shared: set **Waitlisted**. The app approves the whole group when the room fills.

## Author

**Kim M. Montana** · [@kimmmontana](https://github.com/kimmmontana)
