"""Integration with the DormMatchBooking Soroban contract (see blockchain/).

Students pay from their own Stellar wallet: the server builds an unsigned
`book` transaction, the browser signs it with Freighter, and the server
submits it and confirms the booking on-chain. Admin actions (approve,
waitlist, decline, list dorm) are signed with STELLAR_ADMIN_SECRET.
"""
import time
from decimal import Decimal

from django.conf import settings
from stellar_sdk import Address, Keypair, SorobanServer, StrKey, TransactionEnvelope, scval
from stellar_sdk import xdr as stellar_xdr
from stellar_sdk.contract import ContractClient
from stellar_sdk.soroban_rpc import GetTransactionStatus, SendTransactionStatus

STROOPS_PER_XLM = Decimal("10000000")
OPEN_STATUSES = ("Verify", "Waitlisted", "Approved")


class StellarError(Exception):
    """Raised when a contract call or transaction fails."""


def is_enabled():
    return bool(settings.STELLAR_CONTRACT_ID)


def admin_enabled():
    return is_enabled() and bool(settings.STELLAR_ADMIN_SECRET)


def is_valid_address(address):
    return isinstance(address, str) and StrKey.is_valid_ed25519_public_key(address)


def xlm_to_stroops(amount):
    return int(Decimal(amount) * STROOPS_PER_XLM)


def explorer_tx_url(tx_hash):
    return f"{settings.STELLAR_EXPLORER_URL}/tx/{tx_hash}"


def _client():
    return ContractClient(
        settings.STELLAR_CONTRACT_ID, settings.STELLAR_RPC_URL, settings.STELLAR_NETWORK_PASSPHRASE
    )


def _read(function_name, parameters):
    try:
        return _client().invoke(function_name, parameters, parse_result_xdr_fn=scval.to_native).result()
    except Exception as exc:
        raise StellarError(f"Could not read {function_name} from the contract: {exc}") from exc


def _admin_call(function_name, parameters):
    if not admin_enabled():
        raise StellarError("STELLAR_ADMIN_SECRET is not configured.")
    admin = Keypair.from_secret(settings.STELLAR_ADMIN_SECRET)
    try:
        tx = _client().invoke(
            function_name, parameters, source=admin.public_key, signer=admin, parse_result_xdr_fn=scval.to_native
        )
        return tx.sign_and_submit()
    except Exception as exc:
        raise StellarError(f"Contract call {function_name} failed: {exc}") from exc


# ----------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------


def get_booking(chain_booking_id):
    booking = _read("get_booking", [scval.to_uint64(chain_booking_id)])
    return {
        "dorm_id": booking["dorm_id"],
        "student": booking["student"].address,
        "amount": booking["amount"],
        "status": booking["status"][0],
    }


def get_student_bookings(address):
    return _read("get_student_bookings", [scval.to_address(address)])


# ----------------------------------------------------------------------
# Student booking flow
# ----------------------------------------------------------------------


def build_booking_transaction(student_address, chain_dorm_id):
    """Return the unsigned, simulated `book` transaction XDR for the wallet to sign."""
    try:
        tx = _client().invoke(
            "book",
            [scval.to_address(student_address), scval.to_uint32(chain_dorm_id)],
            source=student_address,
        )
        return tx.to_xdr()
    except Exception as exc:
        raise StellarError(f"Could not prepare the booking transaction: {exc}") from exc


def _check_booking_envelope(envelope, student_address, chain_dorm_id):
    """Make sure the signed transaction is exactly the `book` call we prepared."""
    tx = envelope.transaction
    if tx.source.account_id != student_address or len(tx.operations) != 1:
        raise StellarError("The signed transaction does not match this booking.")

    host_function = getattr(tx.operations[0], "host_function", None)
    if host_function is None or host_function.type != stellar_xdr.HostFunctionType.HOST_FUNCTION_TYPE_INVOKE_CONTRACT:
        raise StellarError("The signed transaction is not a contract call.")

    call = host_function.invoke_contract
    contract_id = Address.from_xdr_sc_address(call.contract_address).address
    function_name = call.function_name.sc_symbol.decode()
    args = [scval.to_native(arg) for arg in call.args]
    if (
        contract_id != settings.STELLAR_CONTRACT_ID
        or function_name != "book"
        or len(args) != 2
        or args[0].address != student_address
        or args[1] != chain_dorm_id
    ):
        raise StellarError("The signed transaction does not match this booking.")


def submit_booking_transaction(signed_xdr, student_address, chain_dorm_id, timeout=60):
    """Submit a wallet-signed `book` transaction and return (chain_booking_id, tx_hash)."""
    try:
        envelope = TransactionEnvelope.from_xdr(signed_xdr, settings.STELLAR_NETWORK_PASSPHRASE)
    except Exception as exc:
        raise StellarError("The signed transaction could not be decoded.") from exc
    _check_booking_envelope(envelope, student_address, chain_dorm_id)

    server = SorobanServer(settings.STELLAR_RPC_URL)
    sent = server.send_transaction(envelope)
    if sent.status == SendTransactionStatus.ERROR:
        raise StellarError("The Stellar network rejected the transaction.")

    deadline = time.monotonic() + timeout
    while True:
        result = server.get_transaction(sent.hash)
        if result.status == GetTransactionStatus.SUCCESS:
            break
        if result.status == GetTransactionStatus.FAILED:
            raise StellarError("The booking transaction failed on-chain.")
        if time.monotonic() > deadline:
            raise StellarError("Timed out waiting for the transaction to confirm.")
        time.sleep(1)

    # The contract allows one open booking per student per dorm, so the
    # newest matching booking is the one this transaction created.
    for chain_booking_id in reversed(get_student_bookings(student_address)):
        booking = get_booking(chain_booking_id)
        if booking["dorm_id"] == chain_dorm_id and booking["status"] in OPEN_STATUSES:
            return chain_booking_id, sent.hash
    raise StellarError("The booking was not found on-chain.")


# ----------------------------------------------------------------------
# Admin actions
# ----------------------------------------------------------------------


def list_dorm(dorm):
    """List a DormAccommodation on-chain and return its contract dorm ID."""
    return _admin_call(
        "list_dorm",
        [
            scval.to_string(dorm.dorm_name),
            scval.to_string(dorm.dorm_loc),
            scval.to_enum(dorm.room_type, None),
            scval.to_uint32(dorm.resident_capacity),
            scval.to_int128(xlm_to_stroops(dorm.price_xlm)),
        ],
    )


def approve_solo(chain_booking_id):
    _admin_call("approve_solo", [scval.to_uint64(chain_booking_id)])


def waitlist(chain_booking_id):
    _admin_call("waitlist", [scval.to_uint64(chain_booking_id)])


def decline(chain_booking_id):
    _admin_call("decline", [scval.to_uint64(chain_booking_id)])
