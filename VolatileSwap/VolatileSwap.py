import smartpy as sp 

INITIAL_LIQUIDITY = 1000

class ErrorMessages:
    """Specifies the different Error Types in the contracts
    """
    def make(s): 
        """Generates standard error messages prepending contract name (PlentySwap_)
        Args:
            s: error message string
        Returns:
            standardized error message
        """

        return ("PLentySwap_" + s)

    
    NotAdmin = make("Not_Admin")

    Insufficient = make("Insufficient_Balance")

    NotInitialized = make("Not_Initialized")

    Paused = make("Paused_State")

    InsufficientTokenOut = make("Higher_Slippage")

    InvalidFee = make("Zero System Fee")

    InvalidFeeAmount = make("Invalid_Fee_Value")

    InvalidPair = make("Invalid_Pair")

    NegativeValue = make("Negative_Value")

    SwapLimitExceed = make("SwapLimitExceed")

    InvalidRatio = make("Invalid_LP_Ratio")

    ZeroTransfer = make("Zero_Amount_Transfer")

class ContractLibrary(sp.Contract,ErrorMessages):
    """Provides utility functions 
    """

    def TransferFATwoTokens(sender,receiver,amount,tokenAddress,id):
        """Transfers FA2 tokens
        
        Args:
            sender: sender address
            receiver: receiver address
            amount: amount of tokens to be transferred
            tokenAddress: address of the FA2 contract
            id: id of token to be transferred
        """

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


    def TransferFATokens(sender,reciever,amount,tokenAddress): 
        """Transfers FA1.2 tokens
        
        Args:
            sender: sender address
            reciever: reciever address
            amount: amount of tokens to be transferred
            tokenAddress: address of the FA1.2 contract
        """

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

    def TransferToken(sender, receiver, amount, tokenAddress,id, faTwoFlag): 
        """Generic function to transfer any type of tokens
        
        Args:
            sender: sender address
            reciever: reciever address
            amount: amount of tokens to be transferred
            tokenAddress: address of the token contract
            id: id of token to be transfered (for FA2 tokens)
            faTwoFlag: boolean describing whether the token contract is FA2 or not
        """

        sp.verify(amount > 0 , ErrorMessages.ZeroTransfer)

        sp.if faTwoFlag: 

            ContractLibrary.TransferFATwoTokens(sender, receiver, amount , tokenAddress, id )

        sp.else: 

            ContractLibrary.TransferFATokens(sender, receiver, amount, tokenAddress)

        
    @sp.global_lambda
    def square_root(x): 
        """Calculates the square root of a given integer
        
        Args:
            x : integer whose square root is to be determined
        Returns:
            square root of x
        """

        sp.verify(x >= 0, message = ErrorMessages.NegativeValue)
        
        y = sp.local('y', x)
        
        sp.while y.value * y.value > x:
        
            y.value = (x // y.value + y.value) // 2
        
        sp.verify((y.value * y.value <= x) & (x < (y.value + 1) * (y.value + 1)))

        sp.result(y.value)

class AMM(ContractLibrary):

    def __init__(self,_admin,_token1Address,_token1Id,_token1Check,_token2Address,_token2Id,_token2Check,_lpFee,_systemFee,_lpTokenAddress):

        """Initialize the contract storage
        
        Storage:
            admin: amm admin address
            token1Address: contract address for first token used in the amm
            token1Id: token id for first token used in the amm
            token1Check: boolean describing whether first token used in the amm is FA2
            token2Address: contract address for second token used in the amm
            token2Id: token id for second token used in the amm
            token2Check: boolean describing whether second token used in the amm is FA2
            lpTokenAddress: contract address for the LP tokens used in the amm
            lpFee: % fee for the LP 
            systemFee: % fee for the AMM System
            token1_pool: total liquidity of token 1
            token2_pool: total liquidity of token 2
            totalSupply: total supply of LP tokens
            paused: boolean describing whether contract is paused
            token1_Fee: total system fee accumulated in token 1
            token2_Fee: total system fee accumulated in token 2
            maxSwapLimit: max % of total liquidity that can be swapped in one go
        """

        self.init(
            admin = _admin, 
            token1Address = _token1Address, 
            token1Id = _token1Id,
            token1Check = _token1Check,
            token2Address = _token2Address,
            token2Id = _token2Id,
            token2Check = _token2Check,
            lpTokenAddress = _lpTokenAddress,
            lpFee = _lpFee, 
            systemFee  = _systemFee,
            token1_pool = sp.nat(0), 
            token2_pool = sp.nat(0), 
            totalSupply = sp.nat(0),
            paused = False,
            token1_Fee = sp.nat(0), 
            token2_Fee = sp.nat(0),
            maxSwapLimit = sp.nat(40)
        )


    @sp.entry_point
    def Swap(self,params): 
        """ Function for Users to Swap their assets to get the required Token 
        
        Args:
            tokenAmountIn: amount of tokens sent by user that needs to be swapped
            MinimumTokenOut: minimum amount of token expected by user after swap 
            recipient: address that will receive the swapped out tokens 
            requiredTokenAddress: contract address of the token that is expected to be returned after swap
            requiredTokenId: id of the token that is expected to be returned after swap
        """

        sp.set_type(params, sp.TRecord(tokenAmountIn = sp.TNat, MinimumTokenOut = sp.TNat, recipient = sp.TAddress, requiredTokenAddress = sp.TAddress, requiredTokenId = sp.TNat))

        sp.verify( ~self.data.paused, ErrorMessages.Paused)

        sp.verify( ( (params.requiredTokenAddress == self.data.token1Address) & (params.requiredTokenId == self.data.token1Id)) | 
        ( (params.requiredTokenAddress == self.data.token2Address)  & (params.requiredTokenId == self.data.token2Id)), ErrorMessages.InvalidPair)

        requiredTokenAmount = sp.local('requiredTokenAmount', sp.nat(0))
        SwapTokenPool = sp.local('SwapTokenPool', sp.nat(0))

        lpfee = sp.local('lpfee', sp.nat(0))
        systemfee = sp.local('systemfee', sp.nat(0))

        tokenTransfer = sp.local('tokenTransfer', sp.nat(0))

        sp.if (params.requiredTokenAddress == self.data.token1Address) & (params.requiredTokenId == self.data.token1Id): 

            requiredTokenAmount.value = self.data.token2_pool
            SwapTokenPool.value = self.data.token1_pool

        sp.else: 

            requiredTokenAmount.value = self.data.token1_pool
            SwapTokenPool.value = self.data.token2_pool


        sp.verify(params.tokenAmountIn * 100 <= requiredTokenAmount.value * self.data.maxSwapLimit, ErrorMessages.SwapLimitExceed)

        lpfee.value = params.tokenAmountIn / self.data.lpFee

        systemfee.value = params.tokenAmountIn / self.data.systemFee
        
        Invariant = sp.local('Invariant', self.data.token1_pool * self.data.token2_pool)

        Invariant.value = Invariant.value / sp.as_nat( (requiredTokenAmount.value + params.tokenAmountIn) - ( lpfee.value + systemfee.value) )

        tokenTransfer.value = sp.as_nat(SwapTokenPool.value - Invariant.value)

        sp.verify(tokenTransfer.value >= params.MinimumTokenOut, ErrorMessages.InsufficientTokenOut)

        sp.verify(systemfee.value > 0 , ErrorMessages.InvalidFee)

        sp.if (params.requiredTokenAddress == self.data.token1Address) & (params.requiredTokenId == self.data.token1Id): 

            self.data.token1_pool = Invariant.value

            self.data.token2_pool += sp.as_nat(params.tokenAmountIn - systemfee.value)

            self.data.token2_Fee += systemfee.value

            # Transfer tokens to Exchange
            ContractLibrary.TransferToken(sp.sender, sp.self_address, params.tokenAmountIn, self.data.token2Address, self.data.token2Id, self.data.token2Check)

            # Transfer tokens to the recipient 
            ContractLibrary.TransferToken(sp.self_address, params.recipient, tokenTransfer.value, self.data.token1Address, self.data.token1Id, self.data.token1Check)

        sp.else: 

            self.data.token2_pool = Invariant.value

            self.data.token1_pool += sp.as_nat(params.tokenAmountIn - systemfee.value)

            self.data.token1_Fee += systemfee.value

            # Transfer Tokens to Exchange
            ContractLibrary.TransferToken(sp.sender, sp.self_address, params.tokenAmountIn, self.data.token1Address, self.data.token1Id, self.data.token1Check)

            # Transfer Tokens to the recipient
            ContractLibrary.TransferToken(sp.self_address, params.recipient, tokenTransfer.value, self.data.token2Address, self.data.token2Id, self.data.token2Check)

    @sp.entry_point 
    def AddLiquidity(self,params): 
        """Allows users to add liquidity to the pool and gain LP tokens
        
        Args:
            token1_max: max amount of token 1 that the user wants to supply to the pool 
            token2_max: max amount of token 2 that the user wants to supply to the pool 
            recipient: account address that will be credited with the LP tokens
        """

        sp.set_type(params, sp.TRecord(token1_max = sp.TNat, token2_max = sp.TNat, recipient = sp.TAddress))
        
        token1Amount = sp.local('token1Amount', sp.nat(0))

        token2Amount = sp.local('token2Amount', sp.nat(0))

        liquidity = sp.local('liquidity', sp.nat(0))

        sp.if self.data.totalSupply != sp.nat(0): 

            sp.if (params.token1_max * self.data.token2_pool) / self.data.token1_pool <= params.token2_max: 

                token1Amount.value = params.token1_max

                token2Amount.value = (params.token1_max * self.data.token2_pool ) / self.data.token1_pool

                
            sp.if (params.token2_max * self.data.token1_pool) / self.data.token2_pool <= params.token1_max: 

                token2Amount.value = params.token2_max

                token1Amount.value = (params.token2_max * self.data.token1_pool) / self.data.token2_pool


            sp.verify(token1Amount.value > 0, ErrorMessages.InvalidRatio )

            sp.verify(token2Amount.value > 0, ErrorMessages.InvalidRatio )
            
            sp.if ( token1Amount.value * self.data.totalSupply ) / self.data.token1_pool < ( token2Amount.value * self.data.totalSupply) / self.data.token2_pool: 

                liquidity.value = ( token1Amount.value * self.data.totalSupply ) / self.data.token1_pool

            sp.else: 

                liquidity.value = ( token2Amount.value * self.data.totalSupply) / self.data.token2_pool
            
        sp.else: 

            liquidity.value = sp.as_nat( self.square_root( params.token1_max * params.token2_max ) - INITIAL_LIQUIDITY )
            
            self.data.totalSupply += INITIAL_LIQUIDITY

            token1Amount.value = params.token1_max

            token2Amount.value = params.token2_max
            

        sp.verify(liquidity.value > 0 )

        sp.verify(token1Amount.value <= params.token1_max )

        sp.verify(token2Amount.value <= params.token2_max )
        
        # Transfer Funds to Exchange 
        
        ContractLibrary.TransferToken(sp.sender, sp.self_address, token1Amount.value, self.data.token1Address, self.data.token1Id, self.data.token1Check)

        ContractLibrary.TransferToken(sp.sender, sp.self_address, token2Amount.value, self.data.token2Address, self.data.token2Id, self.data.token2Check)

        self.data.token1_pool += token1Amount.value

        self.data.token2_pool += token2Amount.value

        # Mint LP Tokens
        self.data.totalSupply += liquidity.value

        mintParam = sp.record(
            address = params.recipient, 
            value = liquidity.value
        )

        mintHandle = sp.contract(
            sp.TRecord(address = sp.TAddress, value = sp.TNat),
            self.data.lpTokenAddress,
            "mint"
            ).open_some()

        sp.transfer(mintParam, sp.mutez(0), mintHandle)

    @sp.entry_point 
    def RemoveLiquidity(self,params): 
        """Allows users to remove their liquidity from the pool by burning their LP tokens
        
        Args:
            lpAmount: amount of LP tokens to be burned
            token1_min: minimum amount of token 1 expected by the user upon burning given LP tokens
            token2_min: minimum amount of token 2 expected by the user upon burning given LP tokens 
            recipient: account address that will be credited with the tokens removed from the pool
        """  

        sp.set_type(params, sp.TRecord(lpAmount = sp.TNat ,token1_min = sp.TNat, token2_min = sp.TNat, recipient = sp.TAddress))
        
        sp.verify(self.data.totalSupply != sp.nat(0), message = ErrorMessages.NotInitialized)

        sp.verify(params.lpAmount <= self.data.totalSupply, message = ErrorMessages.Insufficient)
        
        token1Amount = sp.local('token1Amount', sp.nat(0))

        token2Amount = sp.local('token2Amount', sp.nat(0))

        # Computing the Tokens and Plenty Provided for removing Liquidity

        token1Amount.value = (params.lpAmount * self.data.token1_pool) / self.data.totalSupply

        token2Amount.value = (params.lpAmount * self.data.token2_pool) / self.data.totalSupply

        # Values should be greater than  Minimum threshold  

        sp.verify(token1Amount.value >= params.token1_min)

        sp.verify(token2Amount.value >= params.token2_min)

        # Subtracting Values  

        self.data.token1_pool = sp.as_nat( self.data.token1_pool - token1Amount.value )

        self.data.token2_pool = sp.as_nat( self.data.token2_pool - token2Amount.value )

        self.data.totalSupply = sp.as_nat( self.data.totalSupply - params.lpAmount )
        
        # Burning LP Tokens  
        
        burnParam = sp.record(
            address = sp.sender, 
            value = params.lpAmount
        )

        burnHandle = sp.contract(
            sp.TRecord(address = sp.TAddress, value = sp.TNat),
            self.data.lpTokenAddress,
            "burn"
            ).open_some()

        sp.transfer(burnParam, sp.mutez(0), burnHandle)

        # Sending Plenty and Tokens 

        ContractLibrary.TransferToken(sp.self_address, params.recipient, token1Amount.value, self.data.token1Address, self.data.token1Id, self.data.token1Check)

        ContractLibrary.TransferToken(sp.self_address, params.recipient, token2Amount.value, self.data.token2Address, self.data.token2Id, self.data.token2Check)

    @sp.entry_point 
    def ModifyFee(self,params):

        """Admin function to modify the LP and System Fees
        
        Max Fee can be 2% Hardcoded for each of the parameter
        Args:
            lpFee: new % fee for the liquidity providers  
            systemFee: new % fee for the amm system
        """ 

        sp.set_type(params, sp.TRecord(lpFee = sp.TNat, systemFee = sp.TNat))

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        sp.verify( (params.lpFee > 50) & (params.systemFee > 50))

        self.data.lpFee = params.lpFee 

        self.data.systemFee = params.systemFee

    @sp.entry_point 
    def ChangeState(self):
        """Admin function to toggle contract state
        
        UsesCases
        - In case of Rug Pull by a certain Token 
        - Potential Exploit Detected  
        - Depreciating the Contract
        """ 

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        self.data.paused = ~ self.data.paused

    @sp.entry_point
    def ChangeAdmin(self,adminAddress): 
        """Admin function to Update Admin Address
        
        Args:
            adminAddress: Upgrades adminAddress to new MultiSig or DAO 
        """ 

        sp.set_type(adminAddress, sp.TAddress)

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        self.data.admin = adminAddress

    @sp.entry_point 
    def ModifyMaxSwapAmount(self,amount): 
        """Admin function to modify the max swap limit
        
        Args:
            amount: new max % of total liquidity that can be swapped
        """ 
        sp.set_type(amount,sp.TNat)

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        self.data.maxSwapLimit = amount

    @sp.entry_point 
    def WithdrawSystemFee(self,address): 
        """Admin function to withdraw system fee
        
        Args:
            address: account address where the systems fees will be transfered to
        """       
        sp.set_type(address, sp.TAddress)

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        sp.if self.data.token1_Fee != sp.nat(0): 

            ContractLibrary.TransferToken(sp.self_address, address, self.data.token1_Fee, self.data.token1Address, self.data.token1Id, self.data.token1Check )
            
        sp.if self.data.token2_Fee != sp.nat(0): 

            ContractLibrary.TransferToken(sp.self_address, address, self.data.token2_Fee, self.data.token2Address, self.data.token2Id, self.data.token2Check )
        
        self.data.token1_Fee = sp.nat(0)

        self.data.token2_Fee = sp.nat(0)
    

    @sp.utils.view(sp.TRecord(token1_pool = sp.TNat, token2_pool = sp.TNat))
    def getReserveBalance(self,params): 

        """View function to get the current AMM Liquidity reserve
        
        Args:
            token1Address: contract address for first token used in the amm
            token1Id: token id for first token used in the amm
            token2Address: contract address for second token used in the amm
            token2Id: token id for second token used in the amm
        Returns:
            sp.TRecord(token1_pool=sp.TNat, token2_pool=sp.TNat): total liquidity for token 1 and token 2 present in the pool
        """

        sp.set_type(params, sp.TRecord(token1Address = sp.TAddress, token1Id = sp.TNat,token2Address = sp.TAddress, token2Id = sp.TNat))

        sp.verify( ( (params.token1Address == self.data.token1Address) & (params.token1Id == self.data.token1Id)) &
        ( (params.token2Address == self.data.token2Address)  & (params.token2Id == self.data.token2Id)), ErrorMessages.InvalidPair)
        
        reserve = sp.record(    
            token1_pool = self.data.token1_pool, 
            token2_pool = self.data.token2_pool
        )

        sp.result(reserve)

    @sp.utils.view(sp.TRecord(systemFee = sp.TNat, lpFee = sp.TNat))
    def getExchangeFee(self,params): 

        """
            View function to get the Fee Percentage for Liquidity Providers and System Fee
            
            In order to get Percentage, 1/feeValue * 100 = feeValue Percentage
        Args:
            token1Address: contract address for first token used in the amm
            token1Id: token id for first token used in the amm
            token2Address: contract address for second token used in the amm
            token2Id: token id for second token used in the amm
        Returns:
            sp.TRecord(systemFee = sp.TNat, lpFee = sp.TNat): current system fee and lp fee for the amm
        """

        sp.set_type(params, sp.TRecord(token1Address = sp.TAddress, token1Id = sp.TNat,token2Address = sp.TAddress, token2Id = sp.TNat))

        sp.verify( ( (params.token1Address == self.data.token1Address) & (params.token1Id == self.data.token1Id)) &
        ( (params.token2Address == self.data.token2Address)  & (params.token2Id == self.data.token2Id)), ErrorMessages.InvalidPair)

        exchangeFee = sp.record(
            systemFee = self.data.systemFee, 
            lpFee = self.data.lpFee
        )

        sp.result(exchangeFee)


if "templates" not in __name__:
    @sp.add_test(name = "Plenty Swap Contract")
    def test():

        scenario = sp.test_scenario()
        scenario.h1("PlentySwap Contract")

        scenario.table_of_contents()

        # Deployment Accounts 
        adminAddress = sp.address("KT19eGoVGhXHkTSQT9Dfrm4z4QHUa4RttabH")
        lpTokenAddress = sp.address("KT1LRboPna9yQY9BrjtQYDS1DVxhKESK4VVd")
        liquidityProviderFee = 500
        systemFee = 1000

        # Token1 Details  
        token1Address = sp.address("KT1GRSvLoikDsXujKgZPsGLX8k8VvR2Tq95b")
        token1Id = 0 
        token1Check = False 

        # Token2 Details 
        token2Address = sp.address("KT1LRboPna9yQY9BrjtQYDS1DVxhKESK4VVd")
        token2Id = 0 
        token2Check = True 

        Exchange = AMM(adminAddress,token1Address,token1Id,token1Check,token2Address,token2Id,token2Check,liquidityProviderFee,systemFee,lpTokenAddress)
        scenario += Exchange

        # Adding Compilation Target 
        sp.add_compilation_target(
            "Exchange",
            AMM(
            adminAddress,
            token1Address,
            token1Id,
            token1Check,
            token2Address,
            token2Id,
            token2Check,
            liquidityProviderFee,
            systemFee,
            lpTokenAddress
            ))