# Fungible Assets - FA12
# Inspired by https://gitlab.com/tzip/tzip/blob/master/A/FA1.2.md

import smartpy as sp

DECIMAL = 1000000000000000000 # 18 Decimals 

# The metadata below is just an example, it serves as a base,
# the contents are used to build the metadata JSON that users
# can copy and upload to IPFS.
TZIP16_Metadata_Base = {
    "name"          : "xPLENTY",
    "description"   : "Flash Loan Resistant Governance Token for Plenty DeFi DAO",
    "authors"       : [
        "Plenty DeFi DAO"
    ],
    "homepage"      : "https://plentydefi.com",
    "interfaces"    : [
        "TZIP-007-2021-04-17",
        "TZIP-016-2021-04-17"
    ],
}

# A collection of error messages used in the contract.
class FA12_Error:
    def make(s): return ("xPlenty_" + s)

    NotAdmin                        = make("NotAdmin")
    InsufficientBalance             = make("InsufficientBalance")
    UnsafeAllowanceChange           = make("UnsafeAllowanceChange")
    Paused                          = make("Paused")
    NotAllowed                      = make("NotAllowed")
    ZeroTransfer                    = make("Zero_Transfer")
    SameAddressTransfer             = make("Same_Address_Transfer")
    NotExchange                     = make("NotExchange")
    ExchangeChange                  = make("CannotUpdate")
    NotAllowed                      = make("Not_Allowed")
    BlockLevel                      = make("Block_Level_Too_Soon")

##
## ## Meta-Programming Configuration
##
## The `FA12_config` class holds the meta-programming configuration.
##
class FA12_config:
    def __init__(
        self,
        support_upgradable_metadata         = False,
        use_token_metadata_offchain_view    = True,
    ):
        self.support_upgradable_metadata = support_upgradable_metadata
        # Whether the contract metadata can be upgradable or not.
        # When True a new entrypoint `change_metadata` will be added.

        self.use_token_metadata_offchain_view = use_token_metadata_offchain_view
        # Include offchain view for accessing the token metadata (requires TZIP-016 contract metadata)

class FA12_common:
    def normalize_metadata(self, metadata):
        """
            Helper function to build metadata JSON (string => bytes).
        """
        for key in metadata:
            metadata[key] = sp.utils.bytes_of_string(metadata[key])

        return metadata

class FA12_core(sp.Contract, FA12_common):
    def __init__(self, config, **extra_storage):
        self.config = config

        self.init(
            balances = sp.big_map(
                tkey = sp.TAddress,
                tvalue = sp.TNat,
            ),
            approvals = sp.big_map(
                tkey = sp.TAddress,
                tvalue = sp.TMap(sp.TAddress, sp.TNat)
            ),
            # CHANGED: Add Checkpoints
            checkpoints = sp.big_map(
                l = {},
                tkey = sp.TPair(sp.TAddress, sp.TNat),
                tvalue = sp.TRecord(fromBlock = sp.TNat, balance = sp.TNat).layout(("fromBlock", "balance"))
            ),
            # CHANGED: Add numCheckpoints
            numCheckpoints = sp.big_map(
                l = {},
                tkey = sp.TAddress,
                tvalue = sp.TNat
            ),
            totalSupply = 0,
            securityCheck = False,
            **extra_storage
        )


     # CHANGED: Add method to write checkpoints.
    @sp.sub_entry_point
    def writeCheckpoint(self, params):
        sp.set_type(params, sp.TRecord(checkpointedAddress = sp.TAddress, numCheckpoints = sp.TNat, newBalance = sp.TNat).layout(("checkpointedAddress", ("numCheckpoints", "newBalance"))))

        # If there are no checkpoints, write data.
        sp.if params.numCheckpoints == 0:
            self.data.checkpoints[(params.checkpointedAddress, 0)] = sp.record(fromBlock = sp.level, balance = params.newBalance)
            self.data.numCheckpoints[params.checkpointedAddress] = params.numCheckpoints + 1
        sp.else:
            # Otherwise, if this update occurred in the same block, overwrite
            sp.if self.data.checkpoints[(params.checkpointedAddress, sp.as_nat(params.numCheckpoints - 1))].fromBlock == sp.level: 
                self.data.checkpoints[(params.checkpointedAddress, sp.as_nat(params.numCheckpoints - 1))] = sp.record(fromBlock = sp.level, balance = params.newBalance)
            sp.else:
                # Only write an additional checkpoint if the balance has changed.
                sp.if self.data.checkpoints[(params.checkpointedAddress, sp.as_nat(params.numCheckpoints - 1))].balance != params.newBalance:
                    self.data.checkpoints[(params.checkpointedAddress, params.numCheckpoints)] = sp.record(fromBlock = sp.level, balance = params.newBalance)
                    self.data.numCheckpoints[params.checkpointedAddress] = params.numCheckpoints + 1

    # CHANGED: Add view to get balance from checkpoints
    @sp.utils.view(sp.TRecord(result = sp.TNat, address = sp.TAddress, level = sp.TNat))
    def getPriorBalance(self, params):
        sp.set_type(params, sp.TRecord(
            address = sp.TAddress,
            level = sp.TNat,
        ).layout(("address", "level")))

        sp.verify(params.level < sp.level, FA12_Error.BlockLevel)

        # If there are no checkpoints, return 0.
        sp.if self.data.numCheckpoints.get(params.address, 0) == 0:
            sp.result(sp.record(result = 0, address = params.address, level = params.level))
        sp.else:
            # First check most recent balance.
            sp.if self.data.checkpoints[(params.address, sp.as_nat(self.data.numCheckpoints[params.address] - 1))].fromBlock <= params.level:
                sp.result(sp.record(
                    result = self.data.checkpoints[(params.address, sp.as_nat(self.data.numCheckpoints[params.address] - 1))].balance,
                    address = params.address,
                    level = params.level
                ))
            sp.else:
                # Next, check for an implicit zero balance.
                sp.if self.data.checkpoints[(params.address, sp.nat(0))].fromBlock > params.level:
                    sp.result(sp.record(result = 0, address = params.address, level = params.level))
                sp.else:
                    # A boolean that indicates that the current center is the level we are looking for.
                    # This extra variable is required because SmartPy does not have a way to break from
                    # a while loop. 
                    centerIsNeedle = sp.local('centerIsNeedle', False)

                    # Otherwise perform a binary search.
                    center = sp.local('center', 0)
                    lower = sp.local('lower', 0)
                    upper = sp.local('upper', sp.as_nat(self.data.numCheckpoints[params.address] - 1))   
                                        
                    sp.while (upper.value > lower.value) & (centerIsNeedle.value == False):
                        # A complicated way to get the ceiling.
                        center.value = sp.as_nat(upper.value - (sp.as_nat(upper.value - lower.value) / 2))
                        
                        # Check that center is the exact block we are looking for.
                        sp.if self.data.checkpoints[(params.address, center.value)].fromBlock == params.level:
                            centerIsNeedle.value = True
                        sp.else:
                            sp.if self.data.checkpoints[(params.address, center.value)].fromBlock < params.level:
                                lower.value = center.value
                            sp.else:
                                upper.value = sp.as_nat(center.value - 1)

                    # If the center is the needle, return the value at center.
                    sp.if centerIsNeedle.value == True:
                        sp.result(
                            sp.record(
                                result = self.data.checkpoints[(params.address, center.value)].balance,
                                address = params.address, 
                                level = params.level
                            )
                        )
                    # Otherwise return the result.
                    sp.else:
                        sp.result(
                            sp.record(
                                result = self.data.checkpoints[(params.address, lower.value)].balance, 
                                address = params.address, 
                                level = params.level
                            )
                        )

    @sp.entry_point
    def transfer(self, params):
        sp.set_type(params, sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value"))))
        sp.verify(
            (~self.is_paused() &
                ((params.from_ == sp.sender) |
                 (self.data.approvals[params.from_][sp.sender] >= params.value))), FA12_Error.NotAllowed)


        self.addAddressIfNecessary(params.to_)
        self.addAddressIfNecessary(params.from_)

        sp.verify(self.data.balances[params.from_] >= params.value, FA12_Error.InsufficientBalance)
        self.data.balances[params.from_] = sp.as_nat(self.data.balances[params.from_] - params.value)
        self.data.balances[params.to_] += params.value
        sp.if (params.from_ != sp.sender):
            self.data.approvals[params.from_][sp.sender] = sp.as_nat(self.data.approvals[params.from_][sp.sender] - params.value)
            
        # CHANGED: Write checkpoints.
        # Write a checkpoint for the sender.
        self.writeCheckpoint(
            sp.record(
                checkpointedAddress = params.from_,
                numCheckpoints = self.data.numCheckpoints.get(params.from_, 0),
                newBalance = self.data.balances[params.from_]
            )
        )
        # Write a checkpoint for the receiver
        self.writeCheckpoint(
            sp.record(
                checkpointedAddress = params.to_,
                numCheckpoints = self.data.numCheckpoints.get(params.to_, 0),
                newBalance = self.data.balances[params.to_]
            )
        )

    @sp.entry_point
    def approve(self, params):

        sp.set_type(params, sp.TRecord(spender = sp.TAddress, value = sp.TNat).layout(("spender", "value")))
        
        self.addAddressIfNecessary(sp.sender)
        
        sp.verify(~self.is_paused(), FA12_Error.Paused)
        
        alreadyApproved = self.data.approvals[sp.sender].get(params.spender, 0)
        sp.verify((alreadyApproved == 0) | (params.value == 0), FA12_Error.UnsafeAllowanceChange)
        self.data.approvals[sp.sender][params.spender] = params.value

    def addAddressIfNecessary(self, address):
        sp.if ~ self.data.balances.contains(address):
            self.data.balances[address] = 0
            self.data.approvals[address] = {}

    @sp.utils.view(sp.TNat)
    def getBalance(self, params):
        self.addAddressIfNecessary(params)

        sp.result(self.data.balances[params])

    @sp.utils.view(sp.TNat)
    def getAllowance(self, params):
        # CHANGED: Add address if needed.
        self.addAddressIfNecessary(params.owner)

        sp.result(self.data.approvals[params.owner].get(params.spender, sp.nat(0)))

    @sp.utils.view(sp.TNat)
    def getTotalSupply(self, params):
        sp.set_type(params, sp.TUnit)
        sp.result(self.data.totalSupply)

    # this is not part of the standard but can be supported through inheritance.
    def is_paused(self):
        return sp.bool(False)

    # this is not part of the standard but can be supported through inheritance.
    def is_administrator(self, sender):
        return sp.bool(False)

class ContractLibrary(sp.Contract):


    def TransferFATwoTokens(sender,reciever,amount,tokenAddress,id):

        arg = [
            sp.record(
                from_ = sender,
                txs = [
                    sp.record(
                        to_         = reciever,
                        token_id    = id , 
                        amount      = amount 
                    )
                ]
            )
        ]

        transferHandle = sp.contract(
            sp.TList(sp.TRecord(from_=sp.TAddress, txs=sp.TList(sp.TRecord(amount=sp.TNat, to_=sp.TAddress, token_id=sp.TNat).layout(("to_", ("token_id", "amount")))))), 
            tokenAddress,
            entry_point='transfer').open_some()

        sp.transfer(arg, sp.mutez(0), transferHandle)


    def TransferFATokens(sender,reciever,amount,tokenAddress): 

        TransferParam = sp.record(
            from_ = sender, 
            to_ = reciever, 
            value = amount
        )

        transferHandle = sp.contract(
            sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value"))),
            tokenAddress,
            "transfer"
            ).open_some()

        sp.transfer(TransferParam, sp.mutez(0), transferHandle)

    def TransferToken(sender, reciver, amount, tokenAddress,id, faTwoFlag): 

        sp.if faTwoFlag: 

            ContractLibrary.TransferFATwoTokens(sender, reciver, amount , tokenAddress, id )

        sp.else: 

            ContractLibrary.TransferFATokens(sender, reciver, amount, tokenAddress)

    
class FA12_mint_burn(FA12_core, ContractLibrary):

    @sp.entry_point
    def mint(self,params):

        sp.set_type(params, sp.TRecord(address = sp.TAddress, value = sp.TNat))

        sp.verify(sp.sender == self.data.exchangeAddress, FA12_Error.NotExchange)

        self.addAddressIfNecessary(params.address)

        self.data.balances[params.address] += params.value
        self.data.totalSupply += params.value
        
        # CHANGED
        # Write a checkpoint for the receiver
        self.writeCheckpoint(
            sp.record(
                checkpointedAddress = params.address,
                numCheckpoints = self.data.numCheckpoints.get(params.address, 0),
                newBalance = self.data.balances[params.address]
            )
        )

    @sp.entry_point
    def burn(self, params):

        sp.set_type(params, sp.TRecord(address = sp.TAddress, value = sp.TNat))

        sp.verify(sp.sender == self.data.exchangeAddress, FA12_Error.NotExchange)

        sp.verify(self.data.balances[params.address] >= params.value, FA12_Error.InsufficientBalance)
        
        self.data.balances[params.address] = sp.as_nat(self.data.balances[params.address] - params.value)
        self.data.totalSupply = sp.as_nat(self.data.totalSupply - params.value)

        # CHANGED
        # Write a checkpoint for the receiver
        self.writeCheckpoint(
            sp.record(
                checkpointedAddress = params.address,
                numCheckpoints = self.data.numCheckpoints.get(params.address, 0),
                newBalance = self.data.balances[params.address]
            )
        )

    @sp.entry_point
    def updateExchangeAddress(self,address): 

        sp.set_type(address, sp.TAddress)
        
        sp.verify(self.is_administrator(sp.sender), FA12_Error.NotAdmin)

        sp.verify(self.data.securityCheck == False, FA12_Error.ExchangeChange)
        
        self.data.exchangeAddress = address

        self.data.securityCheck = True 

    @sp.entry_point
    def RecoverExcessToken(self,params): 

        sp.set_type(params, sp.TRecord( tokenAddress = sp.TAddress, reciever = sp.TAddress, tokenId = sp.TNat, amount = sp.TNat, faTwoCheck = sp.TBool ))

        sp.verify(self.is_administrator(sp.sender), FA12_Error.NotAdmin)

        ContractLibrary.TransferToken(sp.self_address, params.reciever, params.amount, params.tokenAddress, params.tokenId, params.faTwoCheck)

class FA12_administrator(FA12_core):
    def is_administrator(self, sender):
        return sender == self.data.administrator

    @sp.entry_point
    def setAdministrator(self, params):
        sp.set_type(params, sp.TAddress)
        sp.verify(self.is_administrator(sp.sender), FA12_Error.NotAdmin)
        self.data.administrator = params

    @sp.utils.view(sp.TAddress)
    def getAdministrator(self, params):
        sp.set_type(params, sp.TUnit)
        sp.result(self.data.administrator)

class FA12_pause(FA12_core):
    def is_paused(self):
        return self.data.paused

    @sp.entry_point
    def setPause(self, params):
        sp.set_type(params, sp.TBool)
        sp.verify(self.is_administrator(sp.sender), FA12_Error.NotAdmin)
        self.data.paused = params

class FA12_token_metadata(FA12_core):
    """
        SPEC: https://gitlab.com/tzip/tzip/-/blob/master/proposals/tzip-12/tzip-12.md#token-metadata
        Token-specific metadata is stored/presented as a Michelson value of type (map string bytes).
        A few of the keys are reserved and predefined:
        >>    ""          : Should correspond to a TZIP-016 URI which points to a JSON representation of the token
                            metadata.
        >>    "name"      : Should be a UTF-8 string giving a “display name” to the token.
        >>    "symbol"    : Should be a UTF-8 string for the short identifier of the token (e.g. XTZ, EUR, …).
        >>    "decimals"  : Should be an integer (converted to a UTF-8 string in decimal) which defines the position of                   the decimal point in token balances for displaypurposes.
    """
    def set_token_metadata(self, metadata):
        """
            Store the token_metadata values in a big-map annotated %token_metadata
            of type (big_map nat (pair (nat %token_id) (map %token_info string bytes))).
        """
        self.update_initial_storage(
            token_metadata = sp.big_map(
                {
                    0: sp.record(token_id = 0, token_info = self.normalize_metadata(metadata))
                },
                tkey = sp.TNat,
                tvalue = sp.TRecord(token_id = sp.TNat, token_info = sp.TMap(sp.TString, sp.TBytes))
            )
        )
class FA12_contract_metadata(FA12_core):
    """
        SPEC: https://gitlab.com/tzip/tzip/-/blob/master/proposals/tzip-16/tzip-16.md
        This class offers utilities to define and set TZIP-016 contract metadata.
    """
    def generate_tzip16_metadata(self):
        views = []

        def token_metadata(self, token_id):
            """
                This method will become an offchain view if the contract uses TZIP-016 metadata
                and the config `use_token_metadata_offchain_view` is set to TRUE.
                Return the token-metadata URI for the given token. (token_id must be 0)
                For a reference implementation, dynamic-views seem to be the
                most flexible choice.
            """
            sp.set_type(token_id, sp.TNat)
            sp.result(self.data.token_metadata[token_id])

        if self.usingTokenMetadata and self.config.use_token_metadata_offchain_view:
            self.token_metadata = sp.offchain_view(pure = True, doc = "Get Token Metadata")(token_metadata)
            views += [self.token_metadata]

        metadata = {
            **TZIP16_Metadata_Base,
            "views"         : views
        }

        self.init_metadata("metadata", metadata)

    def set_contract_metadata(self, metadata):
        """
           Set contract metadata
        """
        self.update_initial_storage(
            metadata = sp.big_map(self.normalize_metadata(metadata))
        )

        if self.config.support_upgradable_metadata:
            def update_metadata(self, key, value):
                """
                    An entry-point to allow the contract metadata to be updated.
                    Can be removed with `FA12_config(support_upgradable_metadata = False, ...)`
                """
                sp.verify(self.is_administrator(sp.sender), FA12_Error.NotAdmin)
                self.data.metadata[key] = value
            self.update_metadata = sp.entry_point(update_metadata)

class FA12(
    FA12_mint_burn,
    FA12_administrator,
    FA12_pause,
    FA12_token_metadata,
    FA12_contract_metadata,
    FA12_core
):
    def __init__(self, admin, config, token_metadata = None, contract_metadata = None):

        FA12_core.__init__(self, config, paused = False, administrator = admin, exchangeAddress = admin)

        if token_metadata is None and contract_metadata is None:
            raise Exception(
            """\n
                Contract must contain at least of the following:
                    \t- TZIP-016 %metadata big-map,
                    \t- Token-specific-metadata through the %token_metadata big-map
                More info: https://gitlab.com/tzip/tzip/blob/master/proposals/tzip-7/tzip-7.md#token-metadata
            """
            )

        self.usingTokenMetadata = False
        if token_metadata is not None:
            self.usingTokenMetadata = True
            self.set_token_metadata(token_metadata)
        if contract_metadata is not None:
            self.set_contract_metadata(contract_metadata)

        # This is only an helper, it produces metadata in the output panel
        # that users can copy and upload to IPFS.
        self.generate_tzip16_metadata()

class Viewer(sp.Contract):
    def __init__(self, t):
        self.init(last = sp.none)
        self.init_type(sp.TRecord(last = sp.TOption(t)))
    @sp.entry_point
    def target(self, params):
        self.data.last = sp.some(params)

# Used to test offchain views
class TestOffchainView(sp.Contract):
    def __init__(self, f):
        self.f = f.f
        self.init(result = sp.none)

    @sp.entry_point
    def compute(self, data, params):
        b = sp.bind_block()
        with b:
            self.f(sp.record(data = data), params)
        self.data.result = sp.some(b.value)

if "templates" not in __name__:
    @sp.add_test(name = "FA12")
    def test():

        scenario = sp.test_scenario()
        scenario.h1("Plenty FA1.2 Token Template")

        scenario.table_of_contents()

        # sp.test_account generates ED25519 key-pairs deterministically:
        admin = sp.address("tz1ZKmUUz5ujAvfurBnpmo4ugziQigQKo2EG")
        alice = sp.test_account("Alice")
        bob   = sp.test_account("Robert")

        # Let's display the accounts:
        scenario.h1("Accounts")
        scenario.show([alice, bob])

        scenario.h1("Contract")
        token_metadata = {
            "decimals"    : "18",               # Mandatory by the spec
            "name"        : "xPLENTY",   # Recommended
            "symbol"      : "xPLENTY",              # Recommended
            # Extra fields
            "icon"        : 'https://raw.githubusercontent.com/Plenty-DeFi/Plenty-Logo/main/xPlenty.png'
        }
        contract_metadata = {
            "" : "ipfs://bafkreicpstxib2vfup4yf7vxsulnwlwp3774agelle6u4nw7ztajwnfaxy",
        }
        c1 = FA12(
            admin,
            config              = FA12_config(support_upgradable_metadata = True),
            token_metadata      = token_metadata,
            contract_metadata   = contract_metadata
        )
        scenario += c1

        scenario.h1("Offchain view - token_metadata")
        # Test token_metadata view
        offchainViewTester = TestOffchainView(c1.token_metadata)
        scenario.register(offchainViewTester)
        offchainViewTester.compute(data = c1.data, params = 0)
        scenario.verify_equal(
            offchainViewTester.data.result,
            sp.some(
                sp.record(
                    token_id = 0,
                    token_info = sp.map({
                        "decimals"    : sp.utils.bytes_of_string("18"),
                        "name"        : sp.utils.bytes_of_string("xPLENTY"),
                        "symbol"      : sp.utils.bytes_of_string("xPLENTY"),
                        "icon"        : sp.utils.bytes_of_string('https://raw.githubusercontent.com/Plenty-DeFi/Plenty-Logo/main/xPlenty.png')
                    })
                )
            )
        )

        scenario.h1("Attempt to update metadata")
        scenario.verify(
            c1.data.metadata[""] == sp.utils.bytes_of_string("ipfs://bafkreicpstxib2vfup4yf7vxsulnwlwp3774agelle6u4nw7ztajwnfaxy")
        )
        c1.update_metadata(key = "", value = sp.bytes("0x00")).run(sender = admin)
        scenario.verify(c1.data.metadata[""] == sp.bytes("0x00"))

        scenario.h1("Entry points")
        scenario.h2("Admin mints a few coins")

        c1.mint(address = admin, value = 100 * DECIMAL ).run(sender = admin)
        
        scenario.verify(c1.data.balances[admin] == 100 * DECIMAL)    

        scenario.h2("Alice transfers to Bob")
        
        c1.transfer(from_ = admin, to_ = alice.address, value = 20 * DECIMAL).run(sender = admin)

        c1.transfer(from_ = alice.address, to_ = bob.address, value = 4 * DECIMAL ).run(sender = alice)
        
        scenario.verify(c1.data.balances[alice.address] == 16 * DECIMAL )

        scenario.h2("Bob tries to transfer from Alice but he doesn't have her approval")
        c1.transfer(from_ = alice.address, to_ = bob.address, value = 4 * DECIMAL ).run(sender = bob, valid = False)
        scenario.h2("Alice approves Bob and Bob transfers")
        c1.approve(spender = bob.address, value = 5 * DECIMAL ).run(sender = alice)
        c1.transfer(from_ = alice.address, to_ = bob.address, value = 4 * DECIMAL).run(sender = bob)
        scenario.h2("Bob tries to over-transfer from Alice")
        c1.transfer(from_ = alice.address, to_ = bob.address, value = 4 * DECIMAL).run(sender = bob, valid = False)

        scenario.h2("Admin Can burn Bob's token")
        
        c1.burn(address = bob.address, value = 1 * DECIMAL).run(sender = admin)

        scenario.verify(c1.data.balances[alice.address] == 12 * DECIMAL)
        scenario.h2("Alice tries to burn Bob token")
        c1.burn(address = bob.address, value = 1 * DECIMAL).run(sender = alice, valid = False)

        scenario.h2("Admin pauses the contract and Alice cannot transfer anymore")
        c1.setPause(True).run(sender = admin)
        c1.transfer(from_ = alice.address, to_ = bob.address, value = 4).run(sender = alice, valid = False)

        scenario.verify(c1.data.balances[alice.address] == 12 * DECIMAL)
        scenario.h2("Admin transfers while on pause")
        c1.transfer(from_ = alice.address, to_ = bob.address, value = 1 * DECIMAL).run(sender = admin, valid = False)
        scenario.h2("Admin unpauses the contract and transferts are allowed")
        c1.setPause(False).run(sender = admin)
        scenario.verify(c1.data.balances[alice.address] == 12 * DECIMAL)
        c1.transfer(from_ = alice.address, to_ = bob.address, value = 1 * DECIMAL).run(sender = alice)

        scenario.verify(c1.data.totalSupply == 99 * DECIMAL)
        scenario.verify(c1.data.balances[alice.address] == 11 * DECIMAL)
        scenario.verify(c1.data.balances[bob.address] == 8 * DECIMAL)

        scenario.h1("Views")
        scenario.h2("Balance")
        view_balance = Viewer(sp.TNat)
        scenario += view_balance
        c1.getBalance((alice.address, view_balance.typed.target))
        scenario.verify_equal(view_balance.data.last, sp.some(11 * DECIMAL))

        scenario.h2("Administrator")
        view_administrator = Viewer(sp.TAddress)
        scenario += view_administrator
        c1.getAdministrator((sp.unit, view_administrator.typed.target))
        scenario.verify_equal(view_administrator.data.last, sp.some(admin))

        scenario.h2("Total Supply")
        view_totalSupply = Viewer(sp.TNat)
        scenario += view_totalSupply
        c1.getTotalSupply((sp.unit, view_totalSupply.typed.target))
        scenario.verify_equal(view_totalSupply.data.last, sp.some(99 * DECIMAL))

        scenario.h2("Allowance")
        view_allowance = Viewer(sp.TNat)
        scenario += view_allowance
        c1.getAllowance((sp.record(owner = alice.address, spender = bob.address), view_allowance.typed.target))
        scenario.verify_equal(view_allowance.data.last, sp.some(1 * DECIMAL))

        c1.burn(address = admin, value = 1 * DECIMAL).run(sender = admin)

        c1.burn(address = admin, value = 1000 * DECIMAL).run(sender = admin, valid = False)

        c1.setAdministrator(admin).run(sender = admin)
        
        c1.setAdministrator(admin).run(sender = alice, valid = False)