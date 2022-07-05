import smartpy as sp

INITIAL_LIQUIDITY =  1000

class ContractLibrary(sp.Contract):
    
    def TransferFATwoTokens(sender,receiver,amount,tokenAddress,id):

        arg = [
            sp.record(
                from_ = sender,
                txs = [
                    sp.record(
                        to_         = receiver,
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


    def TransferFATokens(sender,receiver,amount,tokenAddress):

        TransferParam = sp.record(
            from_ = sender, 
            to_ = receiver,
            value = amount
        )

        transferHandle = sp.contract(
            sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value"))),
            tokenAddress,
            "transfer"
            ).open_some()

        sp.transfer(TransferParam, sp.mutez(0), transferHandle)

    def TransferToken(sender, receiver, amount, tokenAddress, id, faTwoFlag):

        sp.verify(amount > 0 , ErrorMessages.ZeroTransfer)

        sp.if faTwoFlag: 

            ContractLibrary.TransferFATwoTokens(sender, receiver, amount , tokenAddress, id )

        sp.else: 

            ContractLibrary.TransferFATokens(sender, receiver, amount, tokenAddress)

    @sp.global_lambda
    def square_root(x): 
        sp.verify(x >= 0, message = ErrorMessages.NegativeValue)
        y = sp.local('y', x)
        sp.while y.value * y.value > x:
            y.value = (x // y.value + y.value) // 2
        sp.verify((y.value * y.value <= x) & (x < (y.value + 1) * (y.value + 1)))
        sp.result(y.value)

class ErrorMessages:
    def make(s): 
        """Generates standard error messages prepending contract name (PlentySwap_)
        Args:
            s: error message string
        Returns:
            standardized error message
        """
        return ("FlatSwap_" + s)
     
    NotAdmin = make("Not_Admin")

    LqtSet = make("LQT_Address_Already_Set")

    Insufficient = make("Insufficient_Balance")

    NotInitialized = make("Not_Initialized")

    Paused = make("Paused_State")

    InvalidRatio = make("Invalid_LP_Ratio")

    InsufficientTokenOut = make("Higher_Slippage")

    NegativeValue = make("Negative_Value")

    ZeroTransfer = make("Zero_Amount_Transfer")
    
    MaxCash = make("Max_Cash_Error")

    InvalidPair = make("Invalid_Pair")

    LqtMinted = make("Min_Lqt_Minted_Error")

    MinTez = make("Min_Tez_Error")

    MinCash = make("Min_Cash_Error")

    LqtBurned = make("Lqt_Burned_Error")

    CashExceed = make("Cash_Bought_Exceeds_Pool")

    TezExceed = make("Tez_Bought_Exceeds_Pool")

# set precision of higher decimal token as 1 and lower token precision as 10 to the power of difference of both token's decimals.
class FlatCurve(ErrorMessages, ContractLibrary):
    def __init__(self, token1Pool, token2Pool, token1Id, token2Id, token1Check, token2Check, token1Precision, token2Precision, token1Address, token2Address, lqtTotal, lpFee, lqtAddress, admin):

        self.init(token1Pool= token1Pool, token2Pool= token2Pool, token1Id= token1Id, token2Id= token2Id,
                  token1Check= token1Check, token2Check= token2Check, token1Precision= token1Precision, token2Precision= token2Precision,
                  token1Address = token1Address, token2Address= token2Address,
                  lqtTotal= lqtTotal, lpFee= lpFee, lqtAddress=lqtAddress, admin = admin, paused = False)

    def burn(self,burnData):
        c = sp.contract(sp.TRecord(address = sp.TAddress, value = sp.TNat), self.data.lqtAddress, entry_point="burn").open_some()
        sp.transfer(burnData,sp.mutez(0),c)

    def mint(self,mintData):
        c = sp.contract(sp.TRecord(address = sp.TAddress, value = sp.TNat), self.data.lqtAddress, entry_point="mint").open_some()
        sp.transfer(mintData,sp.mutez(0),c)
    
    def util(self, x, y):
        sp.set_type(x, sp.TNat)
        sp.set_type(y, sp.TNat)
        plus = x + y
        minus = x - y
        plus_2 = plus * plus 
        plus_4 = plus_2 *plus_2
        plus_8 = plus_4 * plus_4
        plus_7 = plus_4 * plus_2 * plus 
        minus_2 = minus * minus
        minus_4 = minus_2 * minus_2
        minus_8 = minus_4 * minus_4
        minus_7 = minus_4 * minus_2 * minus
        return sp.record(first=abs(sp.to_int(plus_8) - minus_8), second = 8 * abs(minus_7 + sp.to_int(plus_7)))

    def newton(self, params):
        rounds = sp.local('rounds', params.n)
        dy = sp.local('dy', params.dy)
        new_util = sp.local('new_util', self.util((params.x+params.dx), abs(params.y - dy.value)))
        new_u = sp.local('new_u', new_util.value.first)
        new_du_dy = sp.local('new_du_dy', new_util.value.second)
        sp.while rounds.value != 0:
            new_util.value = self.util((params.x+params.dx), abs(params.y - dy.value))
            new_u.value = new_util.value.first
            new_du_dy.value = new_util.value.second
            dy.value = dy.value + (abs(new_u.value - params.u) / new_du_dy.value)
            rounds.value = rounds.value - 1
        return dy.value

    def newton_dx_to_dy(self, params):
        sp.set_type(params,sp.TRecord(x = sp.TNat, y = sp.TNat, dx = sp.TNat, rounds = sp.TInt))
        utility = self.util(params.x, params.y)
        u = utility.first
        dy = self.newton(sp.record(x = params.x, y = params.y, dx = params.dx, dy = sp.nat(0), u = u, n = params.rounds))
        return dy

    @sp.entry_point 
    def add_liquidity(self,params): 
        """Allows users to add liquidity to the pool and gain LP tokens
        
        Args:
            token1_max: max amount of token1 that the user wants to supply to the pool 
            token2_max: max amount of token2 that the user wants to supply to the pool 
            recipient: account address that will be credited with the LP tokens
        """
        sp.set_type(params, sp.TRecord(token1_max = sp.TNat, token2_max = sp.TNat, recipient = sp.TAddress))
        token1Amount = sp.local('token1Amount', sp.nat(0))
        token2Amount = sp.local('token2Amount', sp.nat(0))
        liquidity = sp.local('liquidity', sp.nat(0))
        sp.if self.data.lqtTotal != sp.nat(0): 
            sp.if (params.token1_max * self.data.token2Pool) / self.data.token1Pool <= params.token2_max: 
                token1Amount.value = params.token1_max
                token2Amount.value = (params.token1_max * self.data.token2Pool ) / self.data.token1Pool
            sp.if (params.token2_max * self.data.token1Pool) / self.data.token2Pool <= params.token1_max: 
                token2Amount.value = params.token2_max
                token1Amount.value = (params.token2_max * self.data.token1Pool) / self.data.token2Pool
            sp.verify(token1Amount.value > 0, ErrorMessages.InvalidRatio )
            sp.verify(token2Amount.value > 0, ErrorMessages.InvalidRatio )
            sp.if ( token1Amount.value * self.data.lqtTotal ) / self.data.token1Pool < ( token2Amount.value * self.data.lqtTotal) / self.data.token2Pool: 
                liquidity.value = ( token1Amount.value * self.data.lqtTotal ) / self.data.token1Pool
            sp.else: 
                liquidity.value = ( token2Amount.value * self.data.lqtTotal) / self.data.token2Pool
        sp.else: 
            
            sp.verify(params.token1_max*self.data.token1Precision == params.token2_max*self.data.token2Precision,  ErrorMessages.InvalidRatio)
            
            liquidity.value = sp.as_nat( 2 * self.square_root( params.token1_max * params.token2_max ) - INITIAL_LIQUIDITY )
            
            self.data.lqtTotal += 1000
            token1Amount.value = params.token1_max
            token2Amount.value = params.token2_max
            
        sp.verify(liquidity.value > 0 )
        sp.verify(token1Amount.value <= params.token1_max )
        sp.verify(token2Amount.value <= params.token2_max )

        # Transfer Funds to Exchange 
        ContractLibrary.TransferToken(sp.sender, sp.self_address, token1Amount.value, self.data.token1Address, self.data.token1Id, self.data.token1Check)
        ContractLibrary.TransferToken(sp.sender, sp.self_address, token2Amount.value, self.data.token2Address, self.data.token2Id, self.data.token2Check)
        self.data.token1Pool += token1Amount.value
        self.data.token2Pool += token2Amount.value

        # Mint LP Tokens
        self.data.lqtTotal += liquidity.value
        self.mint(sp.record(address=params.recipient, value = liquidity.value))

    @sp.entry_point 
    def remove_liquidity(self,params): 
        """Allows users to remove their liquidity from the pool by burning their LP tokens
        
        Args:
            lpAmount: amount of LP tokens to be burned
            token1_min: minimum amount of token1 expected by the user upon burning given LP tokens
            token2_min: minimum amount of token2 expected by the user upon burning given LP tokens
            recipient: address of the user that will get the tokens
        """
        sp.set_type(params, sp.TRecord(lpAmount = sp.TNat ,token1_min = sp.TNat, token2_min = sp.TNat, recipient = sp.TAddress))
        sp.verify(self.data.lqtTotal != sp.nat(0), message = ErrorMessages.NotInitialized)
        sp.verify(params.lpAmount <= self.data.lqtTotal, message = ErrorMessages.Insufficient)

        token1Amount = sp.local('token1Amount', sp.nat(0))
        token2Amount = sp.local('token2Amount', sp.nat(0))

        token1Amount.value = (params.lpAmount * self.data.token1Pool) / self.data.lqtTotal
        token2Amount.value = (params.lpAmount * self.data.token2Pool) / self.data.lqtTotal
        sp.verify(token1Amount.value >= params.token1_min)
        sp.verify(token2Amount.value >= params.token2_min)

        # Subtracting Values  
        self.data.token1Pool = sp.as_nat(self.data.token1Pool - token1Amount.value)
        self.data.token2Pool = sp.as_nat(self.data.token2Pool - token2Amount.value)  
        self.data.lqtTotal = sp.as_nat(self.data.lqtTotal - params.lpAmount)
        
        # Burning LP Tokens  
        self.burn(sp.record(address=sp.sender, value= params.lpAmount))

        # Sending Tokens 
        ContractLibrary.TransferToken(sp.self_address, params.recipient, token1Amount.value, self.data.token1Address, self.data.token1Id, self.data.token1Check)
        ContractLibrary.TransferToken(sp.self_address, params.recipient, token2Amount.value, self.data.token2Address, self.data.token2Id, self.data.token2Check)

    @sp.entry_point
    def swap(self,params):
        """ Function for Users to Swap their assets to get the required Token 
        
        Args:
            tokenAmountIn: amount of tokens sent by user that needs to be swapped
            minTokenOut: minimum amount of token expected by user after swap 
            recipient: address that will receive the swapped out tokens 
            requiredTokenAddress: contract address of the token that is expected to be returned after swap
            requiredTokenId: id of the token that is expected to be returned after swap
        """
        sp.set_type(params,sp.TRecord(minTokenOut = sp.TNat, recipient = sp.TAddress, tokenAmountIn = sp.TNat, requiredTokenAddress = sp.TAddress, requiredTokenId = sp.TNat))
        sp.verify(~self.data.paused, ErrorMessages.Paused)
        sp.verify(params.tokenAmountIn >sp.nat(0), ErrorMessages.ZeroTransfer)
        sp.verify(((params.requiredTokenAddress == self.data.token1Address) & (params.requiredTokenId == self.data.token1Id)) | 
        ((params.requiredTokenAddress == self.data.token2Address) & (params.requiredTokenId == self.data.token2Id)), ErrorMessages.InvalidPair)
        token1PoolNew = sp.local("token1PoolNew", self.data.token1Pool * self.data.token1Precision)
        token2PoolNew = sp.local("token2PoolNew", self.data.token2Pool * self.data.token2Precision)
        sp.if (params.requiredTokenAddress == self.data.token1Address) & (params.requiredTokenId == self.data.token1Id): 
            tokenBoughtWithoutFee = self.newton_dx_to_dy(sp.record(x = token2PoolNew.value, y = token1PoolNew.value, dx = params.tokenAmountIn * self.data.token2Precision, rounds = 5))
            fee = sp.local("fee", tokenBoughtWithoutFee/self.data.lpFee)
            tokenBought = abs(tokenBoughtWithoutFee - fee.value) / self.data.token1Precision
            sp.verify(tokenBought>=params.minTokenOut , ErrorMessages.MinCash)
            sp.verify(tokenBought<self.data.token1Pool, ErrorMessages.CashExceed)
            self.data.token1Pool= abs(self.data.token1Pool - tokenBought)
            self.data.token2Pool= self.data.token2Pool + params.tokenAmountIn
            ContractLibrary.TransferToken(sp.sender, sp.self_address, params.tokenAmountIn, self.data.token2Address, self.data.token2Id, self.data.token2Check)
            ContractLibrary.TransferToken(sp.self_address, params.recipient, tokenBought, self.data.token1Address, self.data.token1Id, self.data.token1Check)
        sp.else :
            tokenBoughtWithoutFee = self.newton_dx_to_dy(sp.record(x = token1PoolNew.value, y = token2PoolNew.value, dx = params.tokenAmountIn * self.data.token1Precision, rounds = 5))
            fee = sp.local("fee", tokenBoughtWithoutFee/self.data.lpFee)
            tokenBought = abs(tokenBoughtWithoutFee - fee.value) / self.data.token2Precision
            sp.verify(tokenBought>=params.minTokenOut, ErrorMessages.MinCash)
            sp.verify(tokenBought<self.data.token2Pool, ErrorMessages.CashExceed)
            self.data.token2Pool= abs(self.data.token2Pool - tokenBought)
            self.data.token1Pool= self.data.token1Pool + params.tokenAmountIn
            ContractLibrary.TransferToken(sp.sender, sp.self_address, params.tokenAmountIn, self.data.token1Address, self.data.token1Id, self.data.token1Check)
            ContractLibrary.TransferToken(sp.self_address, params.recipient, tokenBought, self.data.token2Address, self.data.token2Id, self.data.token2Check)

    @sp.entry_point 
    def ChangeState(self):
        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)
        self.data.paused = ~ self.data.paused

    @sp.entry_point
    def ChangeAdmin(self,adminAddress): 
        sp.set_type(adminAddress, sp.TAddress)
        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)
        self.data.admin = adminAddress

    @sp.onchain_view()
    def getReserveBalance(self): 
        reserve = sp.record(
            token1Pool = self.data.token1Pool, 
            token2Pool = self.data.token2Pool
        )
        sp.result(reserve)


if "templates" not in __name__:
    @sp.add_test(name = "FlatCurve")
    def test():
    
        adminAddress = sp.address("tz1NbDzUQCcV2kp3wxdVHVSZEDeq2h97mweW")
        bob = sp.test_account("Bob")
        cat = sp.test_account("Cat")
        scenario = sp.test_scenario()

        token1Address = sp.address("KT1E4FW4W768ZjYYKmMJwNnZgGvtPHQfFRVi")
        token2Address = sp.address("KT1Bjfjuwfpgm5R3iXq8PBM9zqd3jEK2jiy5")

        lqtTokenAddress = sp.address("KT1SNb6r5X7CnDU7C7PAcbNK7Tu7Srj9p3Jz")

        c1 = FlatCurve(token1Pool= sp.nat(0), token2Pool= sp.nat(0), 
        token1Id= sp.nat(0), token2Id= sp.nat(0), 
        token1Check= True, token2Check= True, 
        token1Precision = sp.nat(1), token2Precision= sp.nat(1), 
        token1Address = token1Address, token2Address= token2Address, 
        lpFee = sp.nat(500),  lqtTotal= sp.nat(0), lqtAddress= lqtTokenAddress, admin = adminAddress)

        scenario.h1("Token to token flat curve")
        
        scenario += c1