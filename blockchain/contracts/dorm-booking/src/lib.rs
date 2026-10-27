//! DormMatch booking escrow on Stellar (Soroban).
//!
//! Mirrors the booking rules of the Django app (`dormmatch/models.py`):
//! - Solo rooms have a capacity of 1 and are approved directly by the admin.
//! - Shared rooms collect waitlisted residents; once the waitlist reaches the
//!   room's capacity, every waitlisted booking is approved together.
//!
//! Payments are made in a Stellar token (e.g. the native XLM asset contract or
//! USDC) and held in escrow by this contract until a booking is approved
//! (released to the treasury) or declined/cancelled (refunded to the student).
#![no_std]

use soroban_sdk::{
    contract, contracterror, contractevent, contractimpl, contracttype, panic_with_error, token, Address, Env,
    String, Vec,
};

const DAY_IN_LEDGERS: u32 = 17_280;
const TTL_THRESHOLD: u32 = 30 * DAY_IN_LEDGERS;
const TTL_EXTEND_TO: u32 = 120 * DAY_IN_LEDGERS;

#[contracttype]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RoomType {
    Solo,
    Shared,
}

#[contracttype]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum OccupiedStatus {
    No,
    Yes,
    Waiting,
}

#[contracttype]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BookingStatus {
    Verify,
    Waitlisted,
    Approved,
    Declined,
    Cancelled,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Dorm {
    pub name: String,
    pub location: String,
    pub room_type: RoomType,
    pub capacity: u32,
    pub waitlisted: u32,
    pub approved: u32,
    pub price: i128,
    pub occupied: OccupiedStatus,
    pub active: bool,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Booking {
    pub dorm_id: u32,
    pub student: Address,
    pub amount: i128,
    pub status: BookingStatus,
    pub created_at: u64,
}

#[contracttype]
#[derive(Clone)]
enum DataKey {
    Admin,
    Token,
    Treasury,
    DormCount,
    BookingCount,
    Dorm(u32),
    Booking(u64),
    DormBookings(u32),
    StudentBookings(Address),
}

#[contracterror]
#[derive(Clone, Copy, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum Error {
    InvalidCapacity = 1,
    InvalidPrice = 2,
    DormNotFound = 3,
    DormInactive = 4,
    DormFull = 5,
    AlreadyBooked = 6,
    BookingNotFound = 7,
    InvalidStatus = 8,
    NotStudent = 9,
}

#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DormListed {
    #[topic]
    pub dorm_id: u32,
    pub room_type: RoomType,
    pub capacity: u32,
    pub price: i128,
}

#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BookingRequested {
    #[topic]
    pub booking_id: u64,
    #[topic]
    pub dorm_id: u32,
    pub student: Address,
    pub amount: i128,
}

#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BookingStatusChanged {
    #[topic]
    pub booking_id: u64,
    pub status: BookingStatus,
}

#[contractevent]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DormStatusChanged {
    #[topic]
    pub dorm_id: u32,
    pub status: OccupiedStatus,
}

#[contract]
pub struct DormMatchBooking;

#[contractimpl]
impl DormMatchBooking {
    /// `token` is the Stellar asset contract used for payments.
    /// `treasury` receives payments for approved bookings.
    pub fn __constructor(env: Env, admin: Address, token: Address, treasury: Address) {
        let s = env.storage().instance();
        s.set(&DataKey::Admin, &admin);
        s.set(&DataKey::Token, &token);
        s.set(&DataKey::Treasury, &treasury);
        s.set(&DataKey::DormCount, &0u32);
        s.set(&DataKey::BookingCount, &0u64);
    }

    // ------------------------------------------------------------------
    // Admin: dorm management
    // ------------------------------------------------------------------

    pub fn list_dorm(
        env: Env,
        name: String,
        location: String,
        room_type: RoomType,
        capacity: u32,
        price: i128,
    ) -> u32 {
        require_admin(&env);
        if capacity == 0 || (room_type == RoomType::Solo && capacity != 1) {
            panic_with_error!(&env, Error::InvalidCapacity);
        }
        if price <= 0 {
            panic_with_error!(&env, Error::InvalidPrice);
        }

        let dorm_id: u32 = env.storage().instance().get(&DataKey::DormCount).unwrap_or(0) + 1;
        env.storage().instance().set(&DataKey::DormCount, &dorm_id);
        bump_instance(&env);

        let dorm = Dorm {
            name,
            location,
            room_type,
            capacity,
            waitlisted: 0,
            approved: 0,
            price,
            occupied: OccupiedStatus::No,
            active: true,
        };
        save_dorm(&env, dorm_id, &dorm);

        DormListed { dorm_id, room_type, capacity, price }.publish(&env);
        dorm_id
    }

    pub fn update_dorm(env: Env, dorm_id: u32, price: i128, active: bool) {
        require_admin(&env);
        if price <= 0 {
            panic_with_error!(&env, Error::InvalidPrice);
        }
        let mut dorm = load_dorm(&env, dorm_id);
        dorm.price = price;
        dorm.active = active;
        save_dorm(&env, dorm_id, &dorm);
    }

    // ------------------------------------------------------------------
    // Student: booking
    // ------------------------------------------------------------------

    /// Request a booking by paying the dorm price into escrow.
    pub fn book(env: Env, student: Address, dorm_id: u32) -> u64 {
        student.require_auth();

        let dorm = load_dorm(&env, dorm_id);
        if !dorm.active {
            panic_with_error!(&env, Error::DormInactive);
        }
        if dorm.occupied == OccupiedStatus::Yes {
            panic_with_error!(&env, Error::DormFull);
        }
        if Self::has_open_booking(env.clone(), dorm_id, student.clone()) {
            panic_with_error!(&env, Error::AlreadyBooked);
        }

        token_client(&env).transfer(&student, &env.current_contract_address(), &dorm.price);

        let booking_id: u64 = env.storage().instance().get(&DataKey::BookingCount).unwrap_or(0) + 1;
        env.storage().instance().set(&DataKey::BookingCount, &booking_id);
        bump_instance(&env);

        let booking = Booking {
            dorm_id,
            student: student.clone(),
            amount: dorm.price,
            status: BookingStatus::Verify,
            created_at: env.ledger().timestamp(),
        };
        save_booking(&env, booking_id, &booking);
        push_id(&env, DataKey::DormBookings(dorm_id), booking_id);
        push_id(&env, DataKey::StudentBookings(student.clone()), booking_id);

        BookingRequested { booking_id, dorm_id, student, amount: dorm.price }.publish(&env);
        booking_id
    }

    /// Cancel a booking the admin has not verified yet. Refunds the student.
    pub fn cancel(env: Env, student: Address, booking_id: u64) {
        student.require_auth();
        let mut booking = load_booking(&env, booking_id);
        if booking.student != student {
            panic_with_error!(&env, Error::NotStudent);
        }
        if booking.status != BookingStatus::Verify {
            panic_with_error!(&env, Error::InvalidStatus);
        }
        set_status(&env, booking_id, &mut booking, BookingStatus::Cancelled);
        refund(&env, booking_id, &mut booking);
    }

    // ------------------------------------------------------------------
    // Admin: verification
    // ------------------------------------------------------------------

    /// Approve a Solo booking. Releases the payment and marks the dorm occupied.
    pub fn approve_solo(env: Env, booking_id: u64) {
        require_admin(&env);
        let mut booking = load_booking(&env, booking_id);
        let mut dorm = load_dorm(&env, booking.dorm_id);
        if dorm.room_type != RoomType::Solo || booking.status != BookingStatus::Verify {
            panic_with_error!(&env, Error::InvalidStatus);
        }
        if dorm.approved >= dorm.capacity {
            panic_with_error!(&env, Error::DormFull);
        }

        dorm.approved = 1;
        set_occupied(&env, booking.dorm_id, &mut dorm, OccupiedStatus::Yes);
        save_dorm(&env, booking.dorm_id, &dorm);

        set_status(&env, booking_id, &mut booking, BookingStatus::Approved);
        release(&env, booking_id, &mut booking);
    }

    /// Move a verified Shared booking onto the waitlist. When the waitlist
    /// reaches capacity, all waitlisted bookings are approved and paid out.
    pub fn waitlist(env: Env, booking_id: u64) {
        require_admin(&env);
        let mut booking = load_booking(&env, booking_id);
        let dorm_id = booking.dorm_id;
        let mut dorm = load_dorm(&env, dorm_id);
        if dorm.room_type != RoomType::Shared || booking.status != BookingStatus::Verify {
            panic_with_error!(&env, Error::InvalidStatus);
        }
        if dorm.waitlisted >= dorm.capacity {
            panic_with_error!(&env, Error::DormFull);
        }

        set_status(&env, booking_id, &mut booking, BookingStatus::Waitlisted);
        dorm.waitlisted += 1;

        if dorm.waitlisted == dorm.capacity {
            set_occupied(&env, dorm_id, &mut dorm, OccupiedStatus::Yes);
            let ids: Vec<u64> = env
                .storage()
                .persistent()
                .get(&DataKey::DormBookings(dorm_id))
                .unwrap_or(Vec::new(&env));
            for id in ids.iter() {
                let mut b = load_booking(&env, id);
                if b.status == BookingStatus::Waitlisted {
                    dorm.approved += 1;
                    set_status(&env, id, &mut b, BookingStatus::Approved);
                    release(&env, id, &mut b);
                }
            }
        } else {
            set_occupied(&env, dorm_id, &mut dorm, OccupiedStatus::Waiting);
        }
        save_dorm(&env, dorm_id, &dorm);
    }

    /// Decline a booking that has not been approved yet. Refunds the student.
    pub fn decline(env: Env, booking_id: u64) {
        require_admin(&env);
        let mut booking = load_booking(&env, booking_id);
        match booking.status {
            BookingStatus::Verify => {}
            BookingStatus::Waitlisted => {
                let mut dorm = load_dorm(&env, booking.dorm_id);
                dorm.waitlisted -= 1;
                let status = if dorm.waitlisted == 0 { OccupiedStatus::No } else { OccupiedStatus::Waiting };
                set_occupied(&env, booking.dorm_id, &mut dorm, status);
                save_dorm(&env, booking.dorm_id, &dorm);
            }
            _ => panic_with_error!(&env, Error::InvalidStatus),
        }
        set_status(&env, booking_id, &mut booking, BookingStatus::Declined);
        refund(&env, booking_id, &mut booking);
    }

    // ------------------------------------------------------------------
    // Configuration
    // ------------------------------------------------------------------

    pub fn set_admin(env: Env, new_admin: Address) {
        require_admin(&env);
        env.storage().instance().set(&DataKey::Admin, &new_admin);
    }

    pub fn set_treasury(env: Env, new_treasury: Address) {
        require_admin(&env);
        env.storage().instance().set(&DataKey::Treasury, &new_treasury);
    }

    // ------------------------------------------------------------------
    // Views
    // ------------------------------------------------------------------

    pub fn admin(env: Env) -> Address {
        env.storage().instance().get(&DataKey::Admin).unwrap()
    }

    pub fn token(env: Env) -> Address {
        env.storage().instance().get(&DataKey::Token).unwrap()
    }

    pub fn treasury(env: Env) -> Address {
        env.storage().instance().get(&DataKey::Treasury).unwrap()
    }

    pub fn dorm_count(env: Env) -> u32 {
        env.storage().instance().get(&DataKey::DormCount).unwrap_or(0)
    }

    pub fn booking_count(env: Env) -> u64 {
        env.storage().instance().get(&DataKey::BookingCount).unwrap_or(0)
    }

    pub fn get_dorm(env: Env, dorm_id: u32) -> Dorm {
        load_dorm(&env, dorm_id)
    }

    pub fn get_booking(env: Env, booking_id: u64) -> Booking {
        load_booking(&env, booking_id)
    }

    pub fn get_dorm_bookings(env: Env, dorm_id: u32) -> Vec<u64> {
        env.storage().persistent().get(&DataKey::DormBookings(dorm_id)).unwrap_or(Vec::new(&env))
    }

    pub fn get_student_bookings(env: Env, student: Address) -> Vec<u64> {
        env.storage().persistent().get(&DataKey::StudentBookings(student)).unwrap_or(Vec::new(&env))
    }

    pub fn has_open_booking(env: Env, dorm_id: u32, student: Address) -> bool {
        Self::get_student_bookings(env.clone(), student).iter().any(|id| {
            let b = load_booking(&env, id);
            b.dorm_id == dorm_id
                && matches!(b.status, BookingStatus::Verify | BookingStatus::Waitlisted | BookingStatus::Approved)
        })
    }
}

// ----------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------

fn require_admin(env: &Env) {
    let admin: Address = env.storage().instance().get(&DataKey::Admin).unwrap();
    admin.require_auth();
}

fn token_client(env: &Env) -> token::Client<'_> {
    let token: Address = env.storage().instance().get(&DataKey::Token).unwrap();
    token::Client::new(env, &token)
}

fn bump_instance(env: &Env) {
    env.storage().instance().extend_ttl(TTL_THRESHOLD, TTL_EXTEND_TO);
}

fn save_persistent<V: soroban_sdk::IntoVal<Env, soroban_sdk::Val>>(env: &Env, key: &DataKey, value: &V) {
    env.storage().persistent().set(key, value);
    env.storage().persistent().extend_ttl(key, TTL_THRESHOLD, TTL_EXTEND_TO);
}

fn load_dorm(env: &Env, dorm_id: u32) -> Dorm {
    env.storage()
        .persistent()
        .get(&DataKey::Dorm(dorm_id))
        .unwrap_or_else(|| panic_with_error!(env, Error::DormNotFound))
}

fn save_dorm(env: &Env, dorm_id: u32, dorm: &Dorm) {
    save_persistent(env, &DataKey::Dorm(dorm_id), dorm);
}

fn load_booking(env: &Env, booking_id: u64) -> Booking {
    env.storage()
        .persistent()
        .get(&DataKey::Booking(booking_id))
        .unwrap_or_else(|| panic_with_error!(env, Error::BookingNotFound))
}

fn save_booking(env: &Env, booking_id: u64, booking: &Booking) {
    save_persistent(env, &DataKey::Booking(booking_id), booking);
}

fn push_id(env: &Env, key: DataKey, id: u64) {
    let mut ids: Vec<u64> = env.storage().persistent().get(&key).unwrap_or(Vec::new(env));
    ids.push_back(id);
    save_persistent(env, &key, &ids);
}

fn set_status(env: &Env, booking_id: u64, booking: &mut Booking, status: BookingStatus) {
    booking.status = status;
    save_booking(env, booking_id, booking);
    BookingStatusChanged { booking_id, status }.publish(env);
}

fn set_occupied(env: &Env, dorm_id: u32, dorm: &mut Dorm, status: OccupiedStatus) {
    if dorm.occupied != status {
        dorm.occupied = status;
        DormStatusChanged { dorm_id, status }.publish(env);
    }
}

fn release(env: &Env, booking_id: u64, booking: &mut Booking) {
    let treasury: Address = env.storage().instance().get(&DataKey::Treasury).unwrap();
    let amount = booking.amount;
    booking.amount = 0;
    save_booking(env, booking_id, booking);
    token_client(env).transfer(&env.current_contract_address(), &treasury, &amount);
}

fn refund(env: &Env, booking_id: u64, booking: &mut Booking) {
    let amount = booking.amount;
    booking.amount = 0;
    save_booking(env, booking_id, booking);
    token_client(env).transfer(&env.current_contract_address(), &booking.student, &amount);
}

#[cfg(test)]
mod test;
