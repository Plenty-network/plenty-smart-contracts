import smartpy as sp 

# Reward Mananger for xPLENTY 

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

        return ("xPlenty_" + s)
    
    NotAdmin = make("Not_Admin")

    NotPlenty = make("Not_Plenty_Token")

    NotxPlenty = make("Not_xPlenty_Curve")

    NotMultiSig = make("Not_MultiSig")

    LockCheck = make("Invalid_CallBack")

    LessPlentySwapTokens = make("Less_")

    Insufficient = make("Insufficient_Balance")

    Paused = make("Paused_State")

    ZeroRewardRate = make("Zero_Reward_Rate")

    LowBalance = make("Low_Plenty_Balance")

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


class RewardManager(ContractLibrary): 


    def __init__(self,_admin,_plentyTokenAddress,_xPlentyExchangeAddress,_multiSigAddress):

        self.init(
            admin = _admin,
            plentyTokenAddress = _plentyTokenAddress, 
            xPlentyExchangeAddress = _xPlentyExchangeAddress,
            multiSigAddress = _multiSigAddress,
            balance = sp.nat(0),
            lastUpdate = sp.nat(0),
            periodFinish = sp.nat(0),
            rewardRate = sp.nat(0),
            paused = False, 
            Locked = False, 
        )
    
    """
        xPlenty Contract calls this function to obtain rewards before a user stakes or unstakes 
    
    """
    @sp.entry_point
    def getReward(self,params): 

        sp.set_type(params, sp.TUnit)

        sp.verify(sp.sender == self.data.xPlentyExchangeAddress, ErrorMessages.NotxPlenty)        

        self.sendReward()

    """
        Any user call this function to update the balance variable of the Reward Manager Contract
    """
    @sp.entry_point
    def updatePlentyBalance(self): 

        sp.verify(~self.data.Locked, ErrorMessages.LockCheck)

        self.data.Locked = True 

        # Call get Balance on PlentyTokenAddress
        param = (sp.self_address, sp.self_entry_point(entry_point = 'balanceUpdate'))

        contractHandle = sp.contract(
            sp.TPair(sp.TAddress, sp.TContract(sp.TNat)),
            self.data.plentyTokenAddress,
            "getBalance",      
        ).open_some()
        
        sp.transfer(param, sp.mutez(0), contractHandle)

    """
        callback function to update the balance variable of the contract
    """
    @sp.entry_point
    def balanceUpdate(self,plentyBalance): 

        sp.set_type(plentyBalance, sp.TNat)

        sp.verify(sp.sender == self.data.plentyTokenAddress, ErrorMessages.NotPlenty)

        sp.verify(self.data.Locked, ErrorMessages.LockCheck)

        self.data.balance = plentyBalance

        self.data.Locked = False

    """
        In case of multiSig Address needs to add additional amount of rewards for distribution
    """
    @sp.entry_point
    def AddReward(self,params):

        sp.set_type(params, sp.TRecord(blocks = sp.TNat, reward = sp.TNat))

        sp.verify(sp.sender == self.data.multiSigAddress, ErrorMessages.NotAdmin)

        self.data.balance += params.blocks * params.reward

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

    @sp.entry_point
    def RecoverExcessToken(self,params):

        sp.set_type(params, sp.TRecord( tokenAddress = sp.TAddress, reciever = sp.TAddress, tokenId = sp.TNat, amount = sp.TNat, faTwoCheck = sp.TBool ))

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        sp.if params.tokenAddress == self.data.plentyTokenAddress: 

            sp.verify(sp.as_nat(self.data.balance - params.amount) >= self.data.rewardRate * sp.as_nat(self.data.periodFinish - self.data.lastUpdate), ErrorMessages.LowBalance)

        ContractLibrary.TransferToken(sp.self_address, params.reciever, params.amount, params.tokenAddress, params.tokenId, params.faTwoCheck)

    @sp.entry_point
    def changeAdmin(self, adminAddress): 

        sp.set_type(adminAddress, sp.TAddress)

        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)
        
        self.data.admin = adminAddress

    @sp.entry_point
    def changeParameters(self,params): 

        sp.set_type(params, sp.TRecord(rewardRate = sp.TNat, blocks = sp.TNat))
        
        sp.verify(sp.sender == self.data.admin, ErrorMessages.NotAdmin)

        sp.verify(params.rewardRate > 0, ErrorMessages.ZeroRewardRate)

        sp.verify(self.data.balance >= params.rewardRate * params.blocks, ErrorMessages.LowBalance)

        self.sendReward()

        self.data.rewardRate = params.rewardRate 

        self.data.periodFinish = sp.level + params.blocks

    """
        Internal Function to compute rewards which need to be distributed to the xPlenty Contract
    """
    def sendReward(self):

        sp.if sp.level <= self.data.periodFinish: 

            blocksDifference = sp.local('blocksDifference', sp.as_nat(sp.level - self.data.lastUpdate))

            sp.if blocksDifference.value > 0 : 

                reward = sp.local('reward', self.data.rewardRate * blocksDifference.value)
                
                ContractLibrary.TransferFATokens(sp.self_address, self.data.xPlentyExchangeAddress, reward.value, self.data.plentyTokenAddress)

        self.data.lastUpdate = sp.level 


if "templates" not in __name__:
    @sp.add_test(name = "Single Sided AMM for xPlenty")
    def test():

        scenario = sp.test_scenario()
        scenario.h1("xPlenty Reward Manager Contract")

        scenario.table_of_contents()

        # sp.test_account generates ED25519 key-pairs deterministically:
        admin = sp.address("tz1ZnK6zYJrC9PfKCPryg9tPW6LrERisTGtg")
        plentyToken = sp.address("KT1GRSvLoikDsXujKgZPsGLX8k8VvR2Tq95b")
        xplentyToken   = sp.address("KT1PxkrCckgh5fA5v2cZEE2bX5q2RV1rv8dj")
        multiSigAddress = sp.address("KT1GpTEq4p2XZ8w9p5xM7Wayyw5VR7tb3UaW")

        manager = RewardManager(admin, plentyToken, xplentyToken, multiSigAddress)
        scenario += manager

        manager.changeParameters(rewardRate = 10, blocks = 100).run(sender = admin, level = 100)

        manager.changeParameters(rewardRate = 5, blocks = 100).run(sender = admin, level = 150)

        manager.getReward().run(sender = xplentyToken, level = 151)