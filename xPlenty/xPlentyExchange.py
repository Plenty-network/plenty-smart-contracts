import smartpy  as sp 

# Single Sided AMM Contract for Swapping Plenty to get xPlenty Tokens 

class ErrorMessages:
    """
        Specifies the different Error Types in the contracts
    """
    def make(s): 
        """
            Generates standard error messages prepending contract name (PlentySwap_)
            
            Args:
                s: error message string
            
            Returns:
                standardized error message
        """

        return ("xPLenty_" + s)
    
    NotAdmin = make("Not_Admin")

    NotPlenty = make("Not_Plenty_Token")

    LockCheck = make("Invalid_CallBack")

    LessPlentySwapTokens = make("Less_")

    Insufficient = make("Insufficient_Balance")

    Paused = make("Paused_State")


class ContractLibrary(sp.Contract,ErrorMessages):

    """
        Provides utility functions 
    """

    def TransferFATwoTokens(sender,receiver,amount,tokenAddress,id):
        """
            Transfers FA2 tokens
        
            Args:
                sender: sender address
                receiver: reciever address
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
        """
            Transfers FA1.2 tokens
        
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

        """
            Generic function to transfer any type of tokens
        
            Args:
                sender: sender address
                reciever: reciever address
                amount: amount of tokens to be transferred
                tokenAddress: address of the token contract
                id: id of token to be transfered (for FA2 tokens)
                faTwoFlag: boolean describing whether the token contract is FA2 or not
        """

        sp.if faTwoFlag: 

            ContractLibrary.TransferFATwoTokens(sender, receiver, amount , tokenAddress, id )

        sp.else: 

            ContractLibrary.TransferFATokens(sender, receiver, amount, tokenAddress)
    

class SwapContract(ContractLibrary): 

    def __init__(self,_admin,_plentyTokenAddress,_xPlentyTokenAddress):

        """
            Initialize the contract storage
        
            Storage:
                admin: xPlenty admin address
                plentyTokenAddress: contract address for Plenty Token
                xPlentyTokenAddress: contract address for xPlenty Token
                rewardManagerAddress : contract handling rewards for xPlenty
                totalSupply: total xPlenty Tokens Minted
                paused: Boolean Check to Paused Purchasing of xPlenty Tokens 
                senderAddress: Address called the buy or sell entrypoint 
                recipientAddress: Address where plenty or xplenty tokens will be transferred 
                minimumPlentyToken : expected amount of plenty tokens while selling xPlenty Tokens by the sender 
                minimumxPlentyToken : expected amount of xplenty tokens while depositing plenty Tokens 
                Locked : Boolean check for callback functions of buy and sell 
        """

        self.init(
            admin = _admin,
            plentyTokenAddress = _plentyTokenAddress, 
            xPlentyTokenAddress = _xPlentyTokenAddress,
            rewardManagerAddress = _xPlentyTokenAddress,
            totalSupply = sp.nat(0),
            paused = False,
            senderAddress = sp.none,
            senderAmount = sp.none,
            recipientAddress = sp.none,
            minimumPlentyToken = sp.none,
            minimumxPlentyToken = sp.none,
            Locked = False 
        )

    
    @sp.entry_point
    def buy(self,params): 
        """
            Function for Buying xPlenty Token by depositing Plenty Tokens 
            Args: 
                plentyAmount: Amount of plenty to be deposited 
                recipient: Address which would receive plenty Tokens  
                minimumxPlentyToken : Minimum Amount expected to be recieved by providing plenty
        """
        sp.set_type(params, sp.TRecord(plentyAmount = sp.TNat, recipient = sp.TAddress, minimumxPlentyToken = sp.TNat))

        sp.verify(~self.data.paused, ErrorMessages.Paused)

        # Set Amount and recipient 

        self.data.Locked = True 

        self.data.senderAddress = sp.some(sp.sender)

        self.data.recipientAddress = sp.some(params.recipient)

        self.data.senderAmount = sp.some(params.plentyAmount)

        self.data.minimumxPlentyToken = sp.some(params.minimumxPlentyToken)

        # Adding Call the Reward Manager 
        rewardHandle = sp.contract(
            sp.TUnit,
            self.data.rewardManagerAddress,
            "getReward"
        ).open_some()

        sp.transfer(sp.unit, sp.mutez(0), rewardHandle)

        # Callback Function to get user's balance

        param = (sp.self_address, sp.self_entry_point(entry_point = 'buy_callback'))

        contractHandle = sp.contract(
            sp.TPair(sp.TAddress, sp.TContract(sp.TNat)),
            self.data.plentyTokenAddress,
            "getBalance",      
        ).open_some()
        
        sp.transfer(param, sp.mutez(0), contractHandle)

    @sp.entry_point
    def buy_callback(self,PlentyBalance): 
        """
            Callback function from plenty Token Contract for buying xPlenty by depositing plenty tokens 
            PlentyBalance : Total Plenty Balance of the Contract 
        """
        sp.set_type(PlentyBalance, sp.TNat)

        sp.verify(sp.sender == self.data.plentyTokenAddress, ErrorMessages.NotPlenty)

        sp.verify(self.data.Locked, ErrorMessages.LockCheck)

        tokenMinted = sp.local('tokenMinted', sp.nat(0))

        sp.if (PlentyBalance == 0) & (self.data.totalSupply == 0) :

            tokenMinted.value = self.data.senderAmount.open_some()

        sp.else: 
            
            tokenMinted.value = (self.data.senderAmount.open_some() * self.data.totalSupply) / PlentyBalance

        # Verify Check 

        sp.verify(tokenMinted.value >= self.data.minimumxPlentyToken.open_some())

        self.data.totalSupply += tokenMinted.value

        # Transfer Plenty Tokens 

        ContractLibrary.TransferFATokens(self.data.senderAddress.open_some(), sp.self_address, self.data.senderAmount.open_some(), self.data.plentyTokenAddress)

        # Mint xPlenty Tokens 

        mintParam = sp.record(
            address = self.data.recipientAddress.open_some(),
            value = tokenMinted.value
        )

        mintHandle = sp.contract(
            sp.TRecord(address = sp.TAddress, value = sp.TNat),
            self.data.xPlentyTokenAddress,
            "mint"
            ).open_some()

        sp.transfer(mintParam, sp.mutez(0), mintHandle)

        # Reseting the state 

        self.data.Locked = False

        self.data.senderAddress = sp.none 

        self.data.recipientAddress = sp.none 

        self.data.senderAmount = sp.none

        self.data.minimumxPlentyToken = sp.none


    @sp.entry_point
    def sell(self,params): 
        """
            Function for Selling xPlenty Token to get back Plenty Tokens 
            Args: 
                recipient: Address which would recieve plenty Tokens 
                xPlentyAmount : Amount of xPlenty to be sold 
                minimumPlenty : Minimum Amount expected to be received by selling xPlenty
        """
        sp.set_type(params,sp.TRecord(recipient = sp.TAddress, xplentyAmount = sp.TNat, minimumPlenty = sp.TNat))

        # Set Variables 

        self.data.Locked = True 

        self.data.senderAddress = sp.some(sp.sender)

        self.data.recipientAddress = sp.some(params.recipient)

        self.data.senderAmount = sp.some(params.xplentyAmount)

        self.data.minimumPlentyToken = sp.some(params.minimumPlenty)

        # Add Call to the Reward Manager 
        rewardHandle = sp.contract(
            sp.TUnit,
            self.data.rewardManagerAddress,
            "getReward"
        ).open_some()

        sp.transfer(sp.unit, sp.mutez(0), rewardHandle)

        # Call Back Function 

        param = (sp.self_address, sp.self_entry_point(entry_point = 'sell_callback'))

        contractHandle = sp.contract(
            sp.TPair(sp.TAddress, sp.TContract(sp.TNat)),
            self.data.plentyTokenAddress,
            "getBalance",      
        ).open_some()
        
        sp.transfer(param, sp.mutez(0), contractHandle)

    @sp.entry_point
    def sell_callback(self,PlentyBalance): 
        """
            Callback function from plenty Token Contract for selling xPlenty to get back plenty tokens 
            PlentyBalance : Total Plenty Balance of the Contract 
        """
        sp.set_type(PlentyBalance, sp.TNat)

        sp.verify(sp.sender  == self.data.plentyTokenAddress, ErrorMessages.NotPlenty)

        sp.verify(self.data.Locked)

        plentyAccrued = sp.local('plentyAccrued', sp.nat(0))

        plentyAccrued.value = ( self.data.senderAmount.open_some() * PlentyBalance )  / self.data.totalSupply 

        sp.verify(plentyAccrued.value >= self.data.minimumPlentyToken.open_some())

        self.data.totalSupply = sp.as_nat(self.data.totalSupply - self.data.senderAmount.open_some())

        # Burn Tokens 
        burnParam = sp.record(
            address = self.data.senderAddress.open_some(),
            value = self.data.senderAmount.open_some()
        )

        burnHandle = sp.contract(
            sp.TRecord(address = sp.TAddress, value = sp.TNat),
            self.data.xPlentyTokenAddress,
            "burn"
            ).open_some()

        sp.transfer(burnParam, sp.mutez(0), burnHandle)

        # Transfer Plenty 

        ContractLibrary.TransferFATokens(sp.self_address, self.data.recipientAddress.open_some(), plentyAccrued.value, self.data.plentyTokenAddress)

        # Reset Values 

        self.data.senderAddress = sp.none 

        self.data.recipientAddress = sp.none 

        self.data.senderAmount = sp.none 

        self.data.minimumPlentyToken = sp.none 


    @sp.entry_point
    def ChangeState(self): 
        """
            Admin Function to Change the State of the Contract 
            paused == True : Stop Purchasing of xPlenty 
            paused == False : Enable Purchasing of xPlenty 
        """
        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        self.data.paused = ~ self.data.paused
    
    @sp.entry_point
    def changeAdmin(self,adminAddress): 

        """
            Admin Function to udpate admin Address
        """

        sp.set_type(adminAddress, sp.TAddress)

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        self.data.admin = adminAddress

    @sp.entry_point
    def changeRewardManager(self,rewardManagerAddress): 
        """"
            Admin Function to update Reward Manager Address
            rewardManagerAddress : Address handling rewards for xPlenty
        
        """

        sp.set_type(rewardManagerAddress, sp.TAddress)

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        self.data.rewardManagerAddress = rewardManagerAddress


    @sp.entry_point
    def RecoverExcessToken(self,params): 
        """
            Admin function to Recover any other Token received by the Contract
        
            Args:
                tokenAddress : Token Address which would be recovered 
                reciever : Address which would be receiving the funds 
                tokenId : Id used in case of FA1.2 and FA2
                amount : Recover Amount Value
                faTwoCheck : Boolean parameter for Fa1.2 or Fa2
                address: account address where the systems fees will be transfered to
        """       

        sp.set_type(params, sp.TRecord( tokenAddress = sp.TAddress, reciever = sp.TAddress, tokenId = sp.TNat, amount = sp.TNat, faTwoCheck = sp.TBool ))

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        sp.verify(params.tokenAddress != self.data.plentyTokenAddress)

        ContractLibrary.TransferToken(sp.self_address, params.reciever, params.amount, params.tokenAddress, params.tokenId, params.faTwoCheck)



if "templates" not in __name__:
    @sp.add_test(name = "Single Sided AMM for xPlenty")
    def test():

        scenario = sp.test_scenario()
        scenario.h1("xPlenty Swap Contract")

        scenario.table_of_contents()

        # sp.test_account generates ED25519 key-pairs deterministically:
        admin = sp.address("tz1ZnK6zYJrC9PfKCPryg9tPW6LrERisTGtg")
        plentyToken = sp.address("KT1GRSvLoikDsXujKgZPsGLX8k8VvR2Tq95b")
        xplentyToken   = sp.address("KT1Rpviewjg82JgjGfAKFneSupjAR1kUhbza")

        SingleSideAMM = SwapContract(admin,plentyToken,xplentyToken)
        scenario += SingleSideAMM
        
        # Adding Compilation Target 
        sp.add_compilation_target("xPlenty",
        SwapContract(
            admin,
            plentyToken,
            xplentyToken
        ))