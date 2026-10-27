<div align="center">

<img src="static/images/logo.png" alt="DormMatch logo" width="280">

### Find your dorm. Match your roommates. Book with confidence.

A student housing platform for booking solo dorms and filling shared rooms through a waitlist,<br>
with optional on-chain payment escrow on the **Stellar** network.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-4.0-092E20?logo=django&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5-7952B3?logo=bootstrap&logoColor=white)
![Rust](https://img.shields.io/badge/Rust-Soroban-000000?logo=rust&logoColor=white)
![Stellar](https://img.shields.io/badge/Stellar-Smart%20Contract-7D00FF?logo=stellar&logoColor=white)

</div>

---

## Overview

Finding student housing and compatible roommates is often slow and uncertain. **DormMatch** puts it in one place:

- Students browse **solo rooms** and book them directly, or join the **waitlist for a shared room**.
- When a shared room's waitlist reaches capacity, every resident on it is **approved automatically**.
- Students pay by QR code and submit a payment reference. **Administrators** verify it and manage availability from a dashboard.
- An optional **Stellar Soroban smart contract** holds payments in escrow, so students are refunded automatically if a booking is declined.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Booking Workflow](#booking-workflow)
- [Smart Contract (Stellar / Soroban)](#smart-contract-stellar--soroban)
- [Data Model](#data-model)
- [Running Tests](#running-tests)
- [Contributing](#contributing)
- [Author](#author)

---

## Features

- **Student accounts.** Custom user model with school, degree program, contact details, and gender identity.
- **Solo dorms.** Browse available single-occupancy rooms and book them directly.
- **Shared dorms with waitlisting.** Join a shared room's waitlist. When the waitlist reaches the room's capacity, every waitlisted booking is approved automatically.
- **Payment verification.** Students submit a payment reference (via QR code payment) and the admin verifies it.
- **Booking status tracking.** Students see each booking's state: *Verify → Waitlisted → Approved / Declined*.
- **Admin dashboard.** Built on the Django admin, with validation rules that enforce room capacity and room-type constraints.
- **On-chain escrow (optional).** A Soroban contract that holds payments in a Stellar asset until a booking is approved or refunded.

## Tech Stack

| Layer          | Technology                                   |
| -------------- | -------------------------------------------- |
| Backend        | Python 3, Django 4.0                         |
| Frontend       | Django Templates, Bootstrap 5, custom CSS    |
| Database       | SQLite (development)                         |
| Media          | Pillow (dorm images)                         |
| Configuration  | python-dotenv                                |
| Smart contract | Rust, `soroban-sdk`, Stellar CLI             |

## Project Structure

```
dormmatchapp/
├── accounts/            # Custom user model, sign-up and login
├── dormmatch/           # Dorms, bookings, views, and business rules
├── django_project/      # Django settings, URLs, WSGI/ASGI
├── templates/           # HTML templates (home, listings, details, status)
├── static/              # CSS, images, Bootstrap vendor files
├── blockchain/          # Stellar Soroban smart contract workspace
│   └── contracts/
│       └── dorm-booking/
│           └── src/
│               ├── lib.rs    # DormMatchBooking contract
│               └── test.rs   # Contract unit tests
├── manage.py
├── requirements.txt
└── .env.example
```

## Getting Started

### Prerequisites

- Python 3.10+
- pip
- *(Optional, for the smart contract)* Rust via [rustup](https://rustup.rs) and the [Stellar CLI](https://developers.stellar.org/docs/tools/cli)

### 1. Clone the repository

```bash
git clone https://github.com/kimmmontana/dormmatchapp.git
cd dormmatchapp
```

### 2. Create a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Generate a secret key and paste it into `.env` as `DJANGO_SECRET_KEY`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Set up the database

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Run the development server

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000 for the site and http://127.0.0.1:8000/admin for the admin dashboard.

### Main routes

| Route                  | Description                              |
| ---------------------- | ---------------------------------------- |
| `/`                    | Home page                                |
| `/solodorm/`           | Available solo dorms                     |
| `/solodorm/<id>/`      | Solo dorm details and booking form       |
| `/waitlist/`           | Shared dorms open for waitlisting        |
| `/waitlist/<id>/`      | Shared dorm details, current residents   |
| `/booking-status/`     | The logged-in student's bookings         |
| `/aboutus/`            | About DormMatch                          |
| `/accounts/signup/`    | Student registration                     |

## Booking Workflow

```
             ┌──────────┐
 Student ──▶ │  Verify  │  (booking submitted with payment reference)
             └────┬─────┘
                  │ admin reviews payment
       ┌──────────┼───────────────┐
       ▼          ▼               ▼
  Solo room   Shared room      Declined
  Approved    Waitlisted
                  │
                  │ waitlist count == room capacity
                  ▼
           All waitlisted → Approved, dorm marked occupied
```

- **Solo rooms** always have a capacity of 1. Approval marks the dorm as occupied.
- **Shared rooms** cannot be approved directly. They move to *Waiting* while the waitlist fills, then to *occupied* once it reaches capacity.
- Deleting a shared-room booking moves approved residents back to *Waitlisted* and recalculates availability.

## Smart Contract (Stellar / Soroban)

The `blockchain/` folder contains **`DormMatchBooking`**, a Soroban smart contract for the Stellar network. It applies the same booking rules as the Django app and handles payments trustlessly.

### How it works

1. The **admin** lists dorms with a room type, capacity, and price.
2. A **student** calls `book`. The contract transfers the dorm price from the student into escrow, using any Stellar asset contract (native XLM, USDC, etc.).
3. The **admin** verifies the booking:
   - `approve_solo` approves a solo booking and releases the payment to the treasury.
   - `waitlist` moves a shared booking onto the waitlist. When the waitlist reaches capacity, every waitlisted booking is approved and paid out.
   - `decline` refunds the student.
4. A student can `cancel` a booking that hasn't been verified yet and get a full refund.

### Contract interface

| Function                                                  | Caller  | Description                                  |
| --------------------------------------------------------- | ------- | -------------------------------------------- |
| `__constructor(admin, token, treasury)`                   | deploy  | Sets the admin, payment token, and treasury  |
| `list_dorm(name, location, room_type, capacity, price)`   | admin   | Adds a dorm and returns its ID               |
| `update_dorm(dorm_id, price, active)`                     | admin   | Changes the price or availability            |
| `book(student, dorm_id)`                                  | student | Pays into escrow and returns a booking ID    |
| `cancel(student, booking_id)`                             | student | Refunds a booking that is still unverified   |
| `approve_solo(booking_id)`                                | admin   | Approves a solo booking and releases payment |
| `waitlist(booking_id)`                                    | admin   | Waitlists a shared booking                   |
| `decline(booking_id)`                                     | admin   | Declines and refunds a booking               |
| `set_admin(addr)` / `set_treasury(addr)`                  | admin   | Updates configuration                        |
| `get_dorm`, `get_booking`, `get_dorm_bookings`, `get_student_bookings`, `has_open_booking` | anyone | Read-only views |

The contract also emits events (`DormListed`, `BookingRequested`, `BookingStatusChanged`, `DormStatusChanged`) so off-chain services such as the Django backend can stay in sync.

### 🚀 Live Deployment (Stellar Testnet)

| Item              | Value |
| ----------------- | ----- |
| **Contract ID**   | [`CB3PBY7GGWEZFD35YSKUT65NSDYE3AVM7C5OCFXELOY6NJKHDUGMR2FQ`](https://stellar.expert/explorer/testnet/contract/CB3PBY7GGWEZFD35YSKUT65NSDYE3AVM7C5OCFXELOY6NJKHDUGMR2FQ) |
| Network           | Stellar Testnet (`Test SDF Network ; September 2015`) |
| Payment token     | Native XLM (`CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC`) |
| Admin / Treasury  | `GC33NJWRCPOL47LS3TGVY3OAI3E3WDWFVMP3PRMTLSMCQ3GC6HTRZVI7` |
| Deploy transaction| [`a949f50f…1705b`](https://stellar.expert/explorer/testnet/tx/a949f50fc4361342edb8af6cfb061b8b7fe0fdc981cbb75ee18a7fe26891705b) |
| Explore & invoke  | [Stellar Lab](https://lab.stellar.org/r/testnet/contract/CB3PBY7GGWEZFD35YSKUT65NSDYE3AVM7C5OCFXELOY6NJKHDUGMR2FQ) |

Two sample dorms are listed on-chain: **#1 Class A Solo** (Manila) and **#2 Class B Shared** (Quezon City, capacity 2), each priced at 0.5 XLM. Full deployment details are in [`blockchain/deployments/testnet.json`](blockchain/deployments/testnet.json).

Read a dorm from the live contract:

```bash
stellar contract invoke --id CB3PBY7GGWEZFD35YSKUT65NSDYE3AVM7C5OCFXELOY6NJKHDUGMR2FQ \
  --network testnet --source <YOUR_IDENTITY> --send=no -- get_dorm --dorm_id 2
```

### Build and test

```bash
cd blockchain

# Run unit tests
cargo test

# Build the WASM (requires: rustup target add wasm32v1-none)
stellar contract build
```

### Deploy to Testnet

```bash
# Create and fund a testnet identity
stellar keys generate admin --network testnet --fund

# Address of the native XLM asset contract on testnet
stellar contract id asset --asset native --network testnet

# Deploy, passing constructor arguments after `--`
stellar contract deploy \
  --wasm target/wasm32v1-none/release/dorm_booking.wasm \
  --source admin \
  --network testnet \
  -- \
  --admin admin \
  --token <XLM_ASSET_CONTRACT_ID> \
  --treasury <TREASURY_ADDRESS>
```

Example invocation:

```bash
stellar contract invoke --id <CONTRACT_ID> --source admin --network testnet -- \
  list_dorm --name "Class A Solo" --location "Manila" --room_type Solo --capacity 1 --price 5000000
```

## Data Model

**`CustomUser`** (`accounts`): username, name and suffix, birthday (with a computed age), gender, contact number, email, school, degree program.

**`DormAccommodation`** (`dormmatch`): name, location, room type (Solo/Shared), resident capacity, occupied status (No/Yes/Waiting), price, description, waitlist count, image.

**`BookingStatus`** (`dormmatch`): student, dorm, booking date and time, amount, status (Verify/Waitlisted/Approved/Declined), payment reference.

## Running Tests

```bash
# Django app
python manage.py test

# Smart contract
cd blockchain && cargo test
```

## Contributing

1. Fork the repository and create a feature branch: `git checkout -b feature/my-change`
2. Make your changes and run the tests (`python manage.py test` and `cargo test` in `blockchain/`).
3. Commit with a clear message and open a pull request against `main`.

Never commit `.env` files or secret keys. Use `.env.example` as the template.

## Author

**Kim M. Montana** · [@kimmmontana](https://github.com/kimmmontana)

<div align="center">

Made for students, by students. 🏠

</div>
