#![cfg(test)]

use super::*;
use soroban_sdk::{
    testutils::Address as _,
    token::{StellarAssetClient, TokenClient},
    Address, Env, String,
};

const PRICE: i128 = 5_000_000; // 0.5 XLM in stroops

fn contract_error(e: Error) -> soroban_sdk::Error {
    soroban_sdk::Error::from_contract_error(e as u32)
}

struct Setup<'a> {
    env: Env,
    client: DormMatchBookingClient<'a>,
    token: TokenClient<'a>,
    treasury: Address,
    alice: Address,
    bob: Address,
    solo: u32,
    shared: u32,
}

fn setup<'a>() -> Setup<'a> {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let treasury = Address::generate(&env);
    let alice = Address::generate(&env);
    let bob = Address::generate(&env);

    let sac = env.register_stellar_asset_contract_v2(admin.clone());
    let token = TokenClient::new(&env, &sac.address());
    let minter = StellarAssetClient::new(&env, &sac.address());
    minter.mint(&alice, &(PRICE * 10));
    minter.mint(&bob, &(PRICE * 10));

    let contract_id = env.register(DormMatchBooking, (&admin, &sac.address(), &treasury));
    let client = DormMatchBookingClient::new(&env, &contract_id);

    let solo = client.list_dorm(
        &String::from_str(&env, "Class A Solo"),
        &String::from_str(&env, "Manila"),
        &RoomType::Solo,
        &1,
        &PRICE,
    );
    let shared = client.list_dorm(
        &String::from_str(&env, "Class B Shared"),
        &String::from_str(&env, "Quezon City"),
        &RoomType::Shared,
        &2,
        &PRICE,
    );

    Setup { env, client, token, treasury, alice, bob, solo, shared }
}

#[test]
fn stores_dorm_details() {
    let s = setup();
    let dorm = s.client.get_dorm(&s.shared);
    assert_eq!(dorm.name, String::from_str(&s.env, "Class B Shared"));
    assert_eq!(dorm.capacity, 2);
    assert_eq!(dorm.occupied, OccupiedStatus::No);
    assert_eq!(s.client.dorm_count(), 2);
}

#[test]
fn rejects_solo_dorm_with_capacity_other_than_one() {
    let s = setup();
    let res = s.client.try_list_dorm(
        &String::from_str(&s.env, "Bad"),
        &String::from_str(&s.env, "X"),
        &RoomType::Solo,
        &2,
        &PRICE,
    );
    assert_eq!(res, Err(Ok(contract_error(Error::InvalidCapacity))));
}

#[test]
fn booking_holds_payment_in_escrow() {
    let s = setup();
    let id = s.client.book(&s.alice, &s.solo);
    assert_eq!(s.token.balance(&s.client.address), PRICE);
    assert_eq!(s.token.balance(&s.alice), PRICE * 9);
    assert_eq!(s.client.get_booking(&id).status, BookingStatus::Verify);
}

#[test]
fn rejects_second_open_booking_for_same_dorm() {
    let s = setup();
    s.client.book(&s.alice, &s.solo);
    assert_eq!(s.client.try_book(&s.alice, &s.solo), Err(Ok(contract_error(Error::AlreadyBooked))));
}

#[test]
fn student_can_cancel_and_get_refund() {
    let s = setup();
    let id = s.client.book(&s.alice, &s.solo);
    s.client.cancel(&s.alice, &id);
    assert_eq!(s.token.balance(&s.alice), PRICE * 10);
    assert_eq!(s.client.get_booking(&id).status, BookingStatus::Cancelled);
}

#[test]
fn only_booking_owner_can_cancel() {
    let s = setup();
    let id = s.client.book(&s.alice, &s.solo);
    assert_eq!(s.client.try_cancel(&s.bob, &id), Err(Ok(contract_error(Error::NotStudent))));
}

#[test]
fn solo_approval_releases_payment_and_fills_dorm() {
    let s = setup();
    let id = s.client.book(&s.alice, &s.solo);
    s.client.approve_solo(&id);

    assert_eq!(s.token.balance(&s.treasury), PRICE);
    assert_eq!(s.token.balance(&s.client.address), 0);
    assert_eq!(s.client.get_dorm(&s.solo).occupied, OccupiedStatus::Yes);
    assert_eq!(s.client.try_book(&s.bob, &s.solo), Err(Ok(contract_error(Error::DormFull))));
}

#[test]
fn solo_booking_cannot_be_waitlisted() {
    let s = setup();
    let id = s.client.book(&s.alice, &s.solo);
    assert_eq!(s.client.try_waitlist(&id), Err(Ok(contract_error(Error::InvalidStatus))));
}

#[test]
fn shared_room_approves_all_once_capacity_reached() {
    let s = setup();
    let a = s.client.book(&s.alice, &s.shared);
    let b = s.client.book(&s.bob, &s.shared);

    s.client.waitlist(&a);
    assert_eq!(s.client.get_dorm(&s.shared).occupied, OccupiedStatus::Waiting);
    assert_eq!(s.client.get_booking(&a).status, BookingStatus::Waitlisted);
    assert_eq!(s.token.balance(&s.treasury), 0);

    s.client.waitlist(&b);
    let dorm = s.client.get_dorm(&s.shared);
    assert_eq!(dorm.occupied, OccupiedStatus::Yes);
    assert_eq!(dorm.approved, 2);
    assert_eq!(s.client.get_booking(&a).status, BookingStatus::Approved);
    assert_eq!(s.client.get_booking(&b).status, BookingStatus::Approved);
    assert_eq!(s.token.balance(&s.treasury), PRICE * 2);
}

#[test]
fn shared_booking_cannot_be_approved_directly() {
    let s = setup();
    let id = s.client.book(&s.alice, &s.shared);
    assert_eq!(s.client.try_approve_solo(&id), Err(Ok(contract_error(Error::InvalidStatus))));
}

#[test]
fn declining_waitlisted_booking_refunds_and_reopens_dorm() {
    let s = setup();
    let id = s.client.book(&s.alice, &s.shared);
    s.client.waitlist(&id);
    s.client.decline(&id);

    assert_eq!(s.token.balance(&s.alice), PRICE * 10);
    let dorm = s.client.get_dorm(&s.shared);
    assert_eq!(dorm.waitlisted, 0);
    assert_eq!(dorm.occupied, OccupiedStatus::No);
}

#[test]
fn admin_can_change_treasury() {
    let s = setup();
    s.client.set_treasury(&s.bob);
    assert_eq!(s.client.treasury(), s.bob);
}

#[test]
#[should_panic]
fn non_admin_cannot_list_dorms() {
    let env = Env::default();
    let admin = Address::generate(&env);
    let treasury = Address::generate(&env);
    let sac = env.register_stellar_asset_contract_v2(admin.clone());
    let contract_id = env.register(DormMatchBooking, (&admin, &sac.address(), &treasury));
    let client = DormMatchBookingClient::new(&env, &contract_id);

    // No auths mocked: the admin signature is missing.
    client.list_dorm(
        &String::from_str(&env, "X"),
        &String::from_str(&env, "Y"),
        &RoomType::Shared,
        &2,
        &PRICE,
    );
}
