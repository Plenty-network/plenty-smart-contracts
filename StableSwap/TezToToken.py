import smartpy as sp

INITIAL_LIQUIDITY = 1000

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

    InsufficientTokenOut = make("Higher_Slippage")

    NegativeValue = make("Negative_Value")

    ZeroTransfer = make("Zero_Amount_Transfer")
    
    MaxCash = make("Max_Cash_Error")

    LqtMinted = make("Min_Lqt_Minted_Error")

    MinTez = make("Min_Tez_Error")

    MinCash = make("Min_Cash_Error")

    LqtBurned = make("Lqt_Burned_Error")

    CashExceed = make("Cash_Bought_Exceeds_Pool")

    TezExceed = make("Tez_Bought_Exceeds_Pool")

    InvalidRatio = make("Invalid_LP_Ratio")


class TezToCtez(sp.Contract, ErrorMessages):
    def __init__(self, tezPool, ctezPool, lqtTotal, ctezAddress, lpFee, lqtAddress, admin, ctez_admin):
        self.init(tezPool = tezPool, ctezPool = ctezPool, lqtTotal= lqtTotal, ctezAddress=ctezAddress,
                  lpFee=lpFee, lqtAddress=lqtAddress, admin = admin, paused = False, Locked = False,
                  ctez_admin = ctez_admin, recipient = sp.none, tradeAmount = sp.none, minAmount = sp.none)

    def tez_transfer(self, to, amount):
        sp.set_type(to,sp.TAddress)
        sp.set_type(amount, sp.TMutez)
        sp.send(to, amount, message = None)

    def cash_transfer(self, transferData):
        c = sp.contract(sp.TRecord(from_ = sp.TAddress , to_ = sp.TAddress ,value = sp.TNat).layout(("from_ as from", ("to_ as to", "value"))), self.data.ctezAddress, entry_point="transfer").open_some()
        sp.transfer(transferData,sp.mutez(0),c)

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
        rounds = sp.local('local', params.n)
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

    def trade_dtez_for_dcash(self, params):
        sp.set_type(params,sp.TRecord(tez = sp.TNat, cash = sp.TNat, dx = sp.TOption(sp.TNat), target = sp.TNat))
        dy_approx = sp.local("dy_approx",self.newton_dx_to_dy (sp.record(x = params.tez<<48, y = params.target * params.cash, dx = params.dx.open_some()<<48, rounds = 5)))
        dcash_approx = sp.local("dcash_approx",dy_approx.value / params.target)
        return dcash_approx.value

    def trade_dcash_for_dtez(self, params):
        sp.set_type(params,sp.TRecord(tez = sp.TNat, cash = sp.TNat, dx = sp.TOption(sp.TNat), target = sp.TNat))
        dy_approx = sp.local("dy_approx",self.newton_dx_to_dy(sp.record(x = params.target * params.cash, y= params.tez<<48, dx = params.target * params.dx.open_some(), rounds = 5)))
        return dy_approx.value>>48

    @sp.global_lambda
    def square_root(x): 
        sp.verify(x >= 0, message = ErrorMessages.NegativeValue)
        y = sp.local('y', x)
        sp.while y.value * y.value > x:
            y.value = (x // y.value + y.value) // 2
        sp.verify((y.value * y.value <= x) & (x < (y.value + 1) * (y.value + 1)))
        sp.result(y.value)

        
    @sp.entry_point
    def default(self):

        sp.send(self.data.admin, sp.amount)

    @sp.entry_point
    def add_liquidity(self,params):
        """Allows users to add liquidity to the pool and gain LP tokens
        
        Args:
            maxCashDeposited: max amount of ctez that the user wants to supply to the pool 
            owner: account address that will be credited with the LP tokens
            minLqtMinted: Minimum amount of LP tokens to be minted
        """
        sp.set_type(params,sp.TRecord(owner = sp.TAddress, minLqtMinted = sp.TNat, maxCashDeposited = sp.TNat))
        tezDeposited = sp.local("tezDeposited", sp.nat(0))
        cashDeposited = sp.local("cashDeposited", sp.nat(0))
        lqtMinted = sp.local("lqtMinted", sp.nat(0))
        sp.if self.data.lqtTotal != sp.nat(0): 
            tezDeposited.value = sp.utils.mutez_to_nat(sp.amount)
            lqtMinted.value = sp.fst(sp.ediv((tezDeposited.value * self.data.lqtTotal), self.data.tezPool).open_some())
            cashDeposited.value = (tezDeposited.value * self.data.ctezPool) / (self.data.tezPool)
            sp.verify(tezDeposited.value > 0, ErrorMessages.InvalidRatio )
            sp.verify(cashDeposited.value > 0, ErrorMessages.InvalidRatio )
        sp.else:
            lqtMinted.value = sp.as_nat(2 * self.square_root(sp.utils.mutez_to_nat(sp.amount) * params.maxCashDeposited) - INITIAL_LIQUIDITY )
            self.data.lqtTotal += 1000
            tezDeposited.value = sp.utils.mutez_to_nat(sp.amount)
            cashDeposited.value = params.maxCashDeposited
        
        sp.verify(lqtMinted.value > 0)
        sp.verify(cashDeposited.value <= params.maxCashDeposited, ErrorMessages.MaxCash)
        sp.verify(lqtMinted.value >= params.minLqtMinted, ErrorMessages.LqtMinted)

        self.data.tezPool = self.data.tezPool + tezDeposited.value
        self.data.ctezPool = self.data.ctezPool + cashDeposited.value
        self.cash_transfer(sp.record(from_ = sp.sender, to_ = sp.self_address, value = cashDeposited.value))
        self.mint(sp.record(address=params.owner, value= lqtMinted.value))
        self.data.lqtTotal = self.data.lqtTotal + lqtMinted.value
        

    @sp.entry_point
    def remove_liquidity(self,params):
        """Allows users to remove their liquidity from the pool by burning their LP tokens
        
        Args:
            lqtBurned: amount of LP tokens to be burned
            minTezWithdrawn: minimum amount of tez expected by the user upon burning given LP tokens
            minCashWithdrawn: minimum amount of ctez expected by the user upon burning given LP tokens 
        """
        sp.set_type(params,sp.TRecord(lqtBurned = sp.TNat, minTezWithdrawn = sp.TNat, minCashWithdrawn = sp.TNat))
        tezWithdrawn = sp.local("tezWithdrawn", params.lqtBurned * self.data.tezPool / self.data.lqtTotal)
        cashWithdrawn = sp.local("cashWithdrawn", params.lqtBurned * self.data.ctezPool / self.data.lqtTotal)
        sp.verify(tezWithdrawn.value >= params.minTezWithdrawn, ErrorMessages.MinTez)
        sp.verify(cashWithdrawn.value >= params.minCashWithdrawn, ErrorMessages.MinCash)
        sp.verify(params.lqtBurned < self.data.lqtTotal,ErrorMessages.LqtBurned)
        sp.verify(tezWithdrawn.value < self.data.tezPool, ErrorMessages.TezExceed)
        sp.verify(cashWithdrawn.value < self.data.ctezPool, ErrorMessages.CashExceed)
        self.data.tezPool = abs(self.data.tezPool - tezWithdrawn.value)
        self.data.ctezPool = abs(self.data.ctezPool - cashWithdrawn.value)
        self.data.lqtTotal = abs(self.data.lqtTotal - params.lqtBurned)
        self.burn(sp.record(address=sp.sender, value= params.lqtBurned))
        self.cash_transfer(sp.record(from_ = sp.self_address, to_ = sp.sender, value = cashWithdrawn.value))
        self.tez_transfer(sp.sender, sp.utils.nat_to_mutez(tezWithdrawn.value))

    @sp.entry_point
    def tez_to_ctez(self,params):
        """Allows users to swap their tez for ctez
        
        Args:
            minCashBought: minimum amount of ctez to be bought
            recipient: address of ther user that will be getting the ctez
        """
        sp.set_type(params,sp.TRecord(minCashBought = sp.TNat, recipient = sp.TAddress))
        sp.verify( ~self.data.paused, ErrorMessages.Paused)
        sp.verify(sp.amount>sp.mutez(0), ErrorMessages.ZeroTransfer)

        self.data.recipient = sp.some(params.recipient)
        self.data.minAmount = sp.some(params.minCashBought)
        self.data.tradeAmount = sp.some(sp.utils.mutez_to_nat(sp.amount))
        self.data.Locked = ~ self.data.Locked

        param = sp.self_entry_point(entry_point = "tez_to_ctez_callback")

        contractHandle = sp.contract(
            sp.TContract(sp.TNat),
            self.data.ctez_admin,
            "get_target",      
        ).open_some()
    
        sp.transfer(param, sp.mutez(0), contractHandle)

    
    @sp.entry_point
    def tez_to_ctez_callback(self, target):
        sp.set_type(target, sp.TNat)
        sp.verify(self.data.Locked)
        sp.verify(self.data.recipient.is_some())
        sp.verify(self.data.tradeAmount.is_some())
        sp.verify(self.data.minAmount.is_some())
        cashBoughtWithoutFee = self.trade_dtez_for_dcash(sp.record(tez = self.data.tezPool, cash = self.data.ctezPool, dx = self.data.tradeAmount, target = target))
        fee = sp.local("fee", cashBoughtWithoutFee / self.data.lpFee)
        cashBought = abs(cashBoughtWithoutFee - fee.value)
        sp.verify(cashBought>=self.data.minAmount.open_some(), ErrorMessages.MinCash)
        sp.verify(cashBought<self.data.ctezPool, ErrorMessages.CashExceed)
        self.data.tezPool = self.data.tezPool + self.data.tradeAmount.open_some()
        self.data.ctezPool = abs(self.data.ctezPool - cashBought)
        self.cash_transfer(sp.record(from_ = sp.self_address, to_ = self.data.recipient.open_some(), value = cashBought))

        self.data.recipient = sp.none
        self.data.minAmount = sp.none
        self.data.tradeAmount = sp.none
        self.data.Locked = ~ self.data.Locked


    @sp.entry_point
    def ctez_to_tez(self,params):
        """Allows users to swap their ctez for tez
        
        Args:
            cashSold: amount of ctez tokens to be swapped
            minTezBought: minimum amount of tez to be bought
            recipient: address of the user that will be getting the tez
        """
        sp.set_type(params,sp.TRecord(cashSold = sp.TNat, minTezBought = sp.TNat, recipient = sp.TAddress))
        sp.verify(params.cashSold>0, ErrorMessages.ZeroTransfer)
        sp.verify(~self.data.paused, ErrorMessages.Paused)

        self.data.recipient = sp.some(params.recipient)
        self.data.minAmount = sp.some(params.minTezBought)
        self.data.tradeAmount = sp.some(params.cashSold)
        self.data.Locked = ~ self.data.Locked

        param = sp.self_entry_point(entry_point = "ctez_to_tez_callback")

        contractHandle = sp.contract(
            sp.TContract(sp.TNat),
            self.data.ctez_admin,
            "get_target",      
        ).open_some()
    
        sp.transfer(param, sp.mutez(0), contractHandle)


    @sp.entry_point
    def ctez_to_tez_callback(self, target):
        sp.set_type(target, sp.TNat)
        sp.verify(self.data.Locked)
        sp.verify(self.data.recipient.is_some())
        sp.verify(self.data.tradeAmount.is_some())
        sp.verify(self.data.minAmount.is_some())
        tezBoughtWithoutFee = self.trade_dcash_for_dtez(sp.record(cash = self.data.ctezPool, tez = self.data.tezPool, dx = self.data.tradeAmount, target= target))
        fee = sp.local("fee", tezBoughtWithoutFee / self.data.lpFee)
        tezBought = abs(tezBoughtWithoutFee - fee.value)
        sp.verify(tezBought>= self.data.minAmount.open_some(), ErrorMessages.MinTez)
        sp.verify(tezBought<self.data.tezPool, ErrorMessages.TezExceed)
        self.data.tezPool = abs(self.data.tezPool - tezBought)
        self.data.ctezPool = self.data.ctezPool + self.data.tradeAmount.open_some()
        self.cash_transfer(sp.record(from_ = self.data.recipient.open_some(), to_ = sp.self_address, value = self.data.tradeAmount.open_some()))
        self.tez_transfer(self.data.recipient.open_some(), sp.utils.nat_to_mutez(tezBought))

        self.data.recipient = sp.none
        self.data.minAmount = sp.none
        self.data.tradeAmount = sp.none
        self.data.Locked = ~ self.data.Locked


    @sp.entry_point 
    def ChangeState(self):
        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)
        self.data.paused = ~ self.data.paused

    @sp.entry_point
    def ChangeAdmin(self,adminAddress): 
        sp.set_type(adminAddress, sp.TAddress)
        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)
        self.data.admin = adminAddress

    @sp.entry_point
    def ChangeBakerAddress(self,newBakerAddress):

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        sp.set_delegate(newBakerAddress)

    @sp.entry_point
    def ChangeLockState(self):

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        self.data.Locked = ~ self.data.Locked

    @sp.onchain_view()
    def getReserveBalance(self): 
        reserve = sp.record(
            tezPool = self.data.tezPool, 
            ctezPool = self.data.ctezPool
        )
        sp.result(reserve)


if "templates" not in __name__:
    @sp.add_test(name = "TezToCtez")
    def test():
        TOKEN_DECIMALS = 10 ** 6
        alice = sp.test_account("Alice")
        bob = sp.test_account("Bob")
        cat = sp.test_account("Cat")
        scenario = sp.test_scenario()

        c1 = TezToCtez(tezPool= sp.nat(0), ctezPool= sp.nat(0),
            lqtTotal= sp.nat(0), ctezAddress = sp.address("KT1HZW9FWJt6aU8x4nr6UiBry2eUCA7xEFb1"), 
            lqtAddress= sp.address("KT1Rp1fLJPFiR3w5iYSB1zxz4aDWL3Biiqhy"), 
            lpFee= sp.nat(2000), admin = sp.address("tz1V7ZKKWf5mQEasxodL8iLkefBAznHrXrEA"), 
            ctez_admin = sp.address("KT19xSuHb2A86eSbKVsduY8mZv4UVEBPwQ17"))

        scenario.h1("Tez To Ctez flat curve")
        
        scenario += c1