"""Middleware that captures calls to 'eth_sign'.

Description:
This middleware intercepts all calls to 'eth_sign and enforces all sign
messages to be signed with a local private key.
"""

from functools import singledispatch
from eth_account import Account, messages
from eth_account.local import LocalAccount
from eth_keys.datatypes import PrivateKey
from hexbytes import HexBytes


@singledispatch
def _to_account(private_key_or_account):
    """Get a `LocalAccount` instance from a private_key or a `LocalAccount`.

    Note that this function is overloaded based on the type on input. This
    implementation is the base case where none of the supported types are
    matched and we throw an exception.
    """
    raise TypeError(
        "key must be one of the types:"
        "eth_keys.datatype.PrivateKey, "
        "eth_account.local.LocalAccount, "
        "or raw private key as a hex string or byte string. "
        "Was of type {0}".format(type(private_key_or_account))
    )


def _private_key_to_account(private_key):
    """Get the account associated with the private key."""
    if isinstance(private_key, PrivateKey):
        private_key = private_key.to_hex()
    else:
        private_key = HexBytes(private_key).hex()
    return Account().privateKeyToAccount(private_key)


_to_account.register(LocalAccount, lambda x: x)
_to_account.register(PrivateKey, _private_key_to_account)
_to_account.register(str, _private_key_to_account)
_to_account.register(bytes, _private_key_to_account)


def construct_local_message_signer(private_key_or_account):
    """Construct a middleware to force `eth_sign` to use local private key.

    :param private_key_or_account: a single private key or a tuple,
        list, or set of private keys. Keys can be any of the following
        formats:

            - An `eth_account.LocalAccount` object
            - An `eth_keys.PrivateKey` object
            - A raw private key as a hex `string` or `bytes`

    :returns: callable local_message_signer_middleware
    """
    if not isinstance(private_key_or_account, (list, tuple, set)):
        private_key_or_account = [private_key_or_account]
    accounts = [_to_account(pkoa) for pkoa in private_key_or_account]
    accounts = {account.address: account for account in accounts}

    def local_message_signer_middleware(
        make_request, web3
    ):  # pylint: disable=unused-argument
        def middleware(method, params):
            if method != "eth_sign":
                return make_request(method, params)
            account_address, message = params[:2]
            account = accounts[account_address]
            # We will assume any string which looks like a hex is expected
            # to be converted to hex. Non-hexable strings are forcibly
            # converted by encoding them to utf-8
            try:
                message = HexBytes(message)
            except Exception:  # pylint: disable=broad-except
                message = HexBytes(message.encode("utf-8"))
            msg_hash_hexbytes = messages.defunct_hash_message(message)
            ec_signature = account.signHash(msg_hash_hexbytes)
            return {"result": ec_signature.signature}

        return middleware

    return local_message_signer_middleware
