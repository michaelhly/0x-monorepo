"""Base wrapper class for accessing ethereum smart contracts."""
from typing import List, Optional, Union
import attr
from eth_utils import to_checksum_address
from web3 import Web3
from web3.providers.base import BaseProvider


@attr.s(kw_only=True)
class TxParams:
    """Transaction Params Structure.

    :param from_: default None, string of account address to initiate tx from
    :param value: default None, integer of amount of ETH in Wei for transfer
    :param gas: default None, integer maximum amount of ETH in Wei for gas
    :param grasPrice: default None, integer price of unit of gas
    :param nonce: default None, integer nonce for account
    """

    from_: Optional[str] = attr.ib(default=None)
    value: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int)
    )
    gas: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int)
    )
    gasPrice: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int)
    )
    nonce: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int)
    )

    def as_dict(self):
        """Get transaction params as dict appropriate for web3."""
        res = {k: v for k, v in attr.asdict(self).items() if v is not None}
        if "from_" in res:
            res["from"] = res["from_"]
            del res["from_"]
        return res


class ContractWrapper:
    """Base class for wrapping ethereum smart contracts.

    It provides functionality for instantiating a contract instance,
    calling view functions, and calling functions which require
    transactions.

    :param provider: instance of :class:`web3.providers.base.BaseProvider`
    :param account_address: default None, str of account address
    :param private_key: default None, str of private_key
    """

    def __init__(
        self,
        provider: BaseProvider,
        account_address: str = None,
        private_key: str = None,
    ):
        """Create an instance of ContractWrapper."""
        self._provider = provider
        self._account_address = account_address
        self._private_key = private_key
        self._web3 = Web3(provider)
        self._web3_eth = self._web3.eth  # pylint: disable=no-member

        if self._web3_eth.defaultAccount or self._web3_eth.accounts:
            self._can_send_tx = True
        else:
            middleware_stack = getattr(self._web3, "middleware_stack")
            if middleware_stack.get("sign_and_send_raw_middleware"):
                if account_address:
                    self._web3_eth.defaultAccount = to_checksum_address(
                        account_address
                    )
                    self._can_send_tx = True
                else:
                    raise Exception(
                        "Please provide the wallet address associated"
                        " with your private key to use the"
                        " sign_and_send_raw_middleware"
                    )
            elif private_key:
                self._private_key = private_key
                self._web3_eth.defaultAccount = to_checksum_address(
                    self._web3_eth.account.privateKeyToAccount(
                        private_key
                    ).address
                )
                self._can_send_tx = True
            else:
                self._can_send_tx = False

    def _contract_instance(self, address: str, abi: dict):
        """Get a contract instance.

        :param address: string address of contract
        :param abi: dict contract ABI

        :returns: instance of contract
        """
        return self._web3_eth.contract(
            address=to_checksum_address(address), abi=abi
        )

    def _validate_and_checksum_address(self, address: str):
        if not self._web3.isAddress(address):
            raise TypeError("Invalid address provided: {}".format(address))
        return to_checksum_address(address)

    def _invoke_function_call(self, func, tx_params, view_only):
        if view_only or not self._can_send_tx:
            return func.call()
        if not tx_params:
            tx_params = TxParams()
        if not tx_params.from_:
            tx_params.from_ = self.get_default_account()
        tx_params.from_ = self._validate_and_checksum_address(tx_params.from_)
        if self._private_key:
            res = self._sign_and_send_raw_direct(func, tx_params)
        else:
            res = func.transact(tx_params.as_dict())
        return res

    def _sign_and_send_raw_direct(self, func, tx_params):
        transaction = func.buildTransaction(tx_params.as_dict())
        signed_tx = self._web3_eth.account.signTransaction(
            transaction, private_key=self._private_key
        )
        return self._web3_eth.sendRawTransaction(signed_tx.rawTransaction)

    def execute_method(
        self,
        address: str,
        abi: dict,
        method: str,
        args: Optional[Union[list, tuple]] = (),
        tx_params: Optional[TxParams] = None,
        view_only: bool = False,
    ) -> str:
        """Execute the method on a contract instance.

        :param address: string of contract address
        :param abi: dict of contract ABI
        :param method: string name of method to call
        :param args: default None, list or tuple of arguments for the method
        :param tx_params: default None, :class:`TxParams` transaction params
        :param view_only: default False, boolean of whether the transaction
            should only be validated.

        :returns: str of transaction hash
        """
        contract_instance = self._contract_instance(address=address, abi=abi)
        if hasattr(contract_instance.functions, method):
            func = getattr(contract_instance.functions, method)(*args)
            return self._invoke_function_call(
                func=func, tx_params=tx_params, view_only=view_only
            )
        raise Exception(
            "No method {} found on contract {}.".format(address, method)
        )

    def get_accounts(self) -> List[str]:
        """Get a list of all accounts associated with the Web3 instance."""
        return self._web3_eth.accounts

    def get_default_account(self) -> str:
        """Get the default account associated with the Web3 instance."""
        return self._web3_eth.defaultAccount or self.get_accounts()[0]
