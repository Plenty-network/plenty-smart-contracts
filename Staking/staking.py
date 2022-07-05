import smartpy as sp

# Staking Contract for FA1.2 Stake Tokens 
DECIMAL = 1000000000000000000 # 18 DECIMALs 

# Const to Be Multuipled with Staked Amount 
MULTIPLIER = 1000000000000 # 12 DECIMALS

# Specify the Token ID of the FA2 StakedToken 
TOKEN_ID = 0

class Staking(sp.Contract): 

    def __init__(self,_admin,_stakeToken,_rewardToken,_faTwoCheck):

        self.init(
            totalSupply = sp.nat(0),
            rewardRate = sp.nat(0), 
            rewardPerTokenStored = sp.nat(0),
            periodFinish = sp.nat(0),
            lastUpdateTime = sp.nat(0),
            unstakeFee = {1 : 4, 2 : 8, 3 : 10}, 
            stakeToken = _stakeToken, 
            rewardToken = _rewardToken,
            admin = _admin,
            balances = 
                sp.big_map(
                    tvalue = sp.TRecord(balance = sp.TNat, rewards = sp.TNat, userRewardPerTokenPaid = sp.TNat, counter = sp.TNat ,InvestMap = sp.TMap(sp.TNat, sp.TRecord(amount = sp.TNat, level = sp.TNat))),
                    tkey = sp.TAddress
                ),
            paused = False,
            blocksPerCycle = sp.nat(4096),
            defaultUnstakeFee = sp.nat(25),
            totalFee = sp.nat(0),
            faTwoToken = _faTwoCheck
        )

    @sp.sub_entry_point 
    def UpdateReward(self,address): 
        
        LastUpdate = sp.local('LastUpdate',sp.nat(0))

        sp.if sp.level > self.data.periodFinish: 
        
            LastUpdate.value = self.data.periodFinish
        
        sp.else: 

            LastUpdate.value  = sp.level
        
        sp.if self.data.totalSupply != sp.nat(0): 

            Result = sp.local('Result',sp.nat(0))

            Result.value += sp.as_nat(LastUpdate.value - self.data.lastUpdateTime)
            
            Result.value = Result.value * DECIMAL * self.data.rewardRate 

            Result.value = (Result.value) / (self.data.totalSupply)            

            self.data.rewardPerTokenStored += Result.value

        
        self.data.lastUpdateTime =  LastUpdate.value

        sp.if address != sp.self_address: 

            self.data.balances[address].rewards += (self.data.balances[address].balance * sp.as_nat( self.data.rewardPerTokenStored  - self.data.balances[address].userRewardPerTokenPaid) ) / abs(DECIMAL)

            self.data.balances[address].userRewardPerTokenPaid = self.data.rewardPerTokenStored

    
    @sp.entry_point
    def GetReward(self):

        sp.verify(self.data.balances.contains(sp.sender), message = "User has not Staked")

        self.UpdateReward(sp.sender)

        lastTimeReward = sp.local('lastTimeReward',sp.nat(0))

        sp.if sp.level > self.data.periodFinish: 
        
            lastTimeReward.value = self.data.periodFinish
        
        sp.else: 

            lastTimeReward.value = sp.level 
        
        RewardPerToken = sp.local('RewardPerToken', self.data.rewardPerTokenStored)

        sp.if self.data.totalSupply != sp.nat(0):

            Difference = sp.local('Difference', sp.as_nat(lastTimeReward.value - self.data.lastUpdateTime))

            Difference.value = (Difference.value * self.data.rewardRate * DECIMAL ) / abs(DECIMAL) + self.data.rewardPerTokenStored

            RewardPerToken.value = Difference.value 

        getReward = sp.local('getReward',self.data.balances[sp.sender].balance)

        getReward.value *= sp.as_nat(RewardPerToken.value - self.data.balances[sp.sender].userRewardPerTokenPaid)

        getReward.value = getReward.value / abs(DECIMAL) + self.data.balances[sp.sender].rewards

        sp.if getReward.value > sp.nat(0): 

            self.data.balances[sp.sender].rewards = 0 

            self.TransferFATokens(sp.self_address, sp.sender, getReward.value, self.data.rewardToken)


    @sp.entry_point
    def stake(self,params):

        sp.set_type(params, sp.TRecord(amount = sp.TNat))
        
        sp.verify(~self.data.paused, message = "Contract is not accepting New Staking Orders")
        
        sp.verify(sp.level <= self.data.periodFinish, message = "Users can't stake after period finish")

        self.addAddressIfNecessary(sp.sender)
        self.UpdateReward(sp.sender)
        
        sp.verify(params.amount > 0 , message = "Cannot Stake Amount Less than 1")
        
        # Transfer Stake Tokens

        sp.if self.data.faTwoToken: 

            self.TransferFATwoTokens(sp.sender, sp.self_address, params.amount, self.data.stakeToken,TOKEN_ID)

        sp.else: 

            self.TransferFATokens(sp.sender, sp.self_address, params.amount, self.data.stakeToken)


        self.data.totalSupply += params.amount * MULTIPLIER 

        self.data.balances[sp.sender].balance += params.amount * MULTIPLIER 

        Length = sp.local('Length',self.data.balances[sp.sender].counter)

        self.data.balances[sp.sender].InvestMap[Length.value] = sp.record( amount = params.amount, level = sp.level )

        self.data.balances[sp.sender].counter += 1 

    @sp.entry_point
    def unstake(self,params):

        sp.set_type(params, sp.TRecord(MapKey = sp.TNat, Amount = sp.TNat))

        sp.verify(self.data.balances.contains(sp.sender), message = "Sender has not Staked any amount")
        sp.verify(self.data.balances[sp.sender].InvestMap.contains(params.MapKey), message = "Map Key does not Exist for the User")

        sp.verify(self.data.balances[sp.sender].InvestMap[params.MapKey].amount >= params.Amount, message ="Request Amount is greater than Lot Amount")

        # Update Reward Modifer 
        self.UpdateReward(sp.sender)

        Amount = sp.local('Amount',self.data.balances[sp.sender].InvestMap[params.MapKey].amount)
        Level = sp.local('Level',self.data.balances[sp.sender].InvestMap[params.MapKey].level)

        self.data.totalSupply = sp.as_nat(self.data.totalSupply - params.Amount * MULTIPLIER )
        self.data.balances[sp.sender].balance = sp.as_nat(self.data.balances[sp.sender].balance - params.Amount * MULTIPLIER )
        
        sp.if Amount.value == params.Amount: 

            del self.data.balances[sp.sender].InvestMap[params.MapKey]
        
        sp.else: 
        
            self.data.balances[sp.sender].InvestMap[params.MapKey].amount = sp.as_nat( Amount.value - params.Amount )

        # Computing Cycles
        
        Cycles = sp.local('Cycles', sp.nat(0))
        
        Cycles.value = sp.as_nat( sp.level - Level.value )

        Cycles.value = Cycles.value / self.data.blocksPerCycle + sp.nat(1)

        PaymentAmount = sp.local('PaymentAmount',params.Amount)
        Fee = sp.local('Fee', sp.nat(0))

        sp.if self.data.unstakeFee.contains(Cycles.value): 

            Fee.value = params.Amount  / self.data.unstakeFee[Cycles.value]

            PaymentAmount.value = sp.as_nat( params.Amount - Fee.value )

        sp.else: 

            Fee.value = params.Amount / self.data.defaultUnstakeFee 

            PaymentAmount.value = sp.as_nat( params.Amount - Fee.value )

        # Add Fee to Total Fee 
        self.data.totalFee += Fee.value 

        # Transfer Stake Tokens

        sp.if self.data.faTwoToken: 

            self.TransferFATwoTokens(sp.self_address, sp.sender, PaymentAmount.value, self.data.stakeToken,TOKEN_ID)

        sp.else: 

            self.TransferFATokens(sp.self_address, sp.sender, PaymentAmount.value, self.data.stakeToken)


    @sp.entry_point
    def AddReward(self,params):
        
        sp.set_type(params, sp.TRecord(reward = sp.TNat, blocks = sp.TNat))

        sp.verify(sp.sender == self.data.admin, message = "Invalid Account")
        
        self.UpdateReward(sp.self_address)
    
        sp.if sp.level >= self.data.periodFinish: 

            self.data.rewardRate = (params.reward)/(params.blocks)

        sp.else: 

            DurationLeft = sp.local('DurationLeft', sp.as_nat(self.data.periodFinish - sp.level))
            LeftOver = sp.local('LeftOver',DurationLeft.value * self.data.rewardRate)
            
            self.data.rewardRate =  ( LeftOver.value + params.reward ) / ( params.blocks )

        self.data.lastUpdateTime = sp.level

        self.data.periodFinish = sp.level + params.blocks
        

    def addAddressIfNecessary(self, address):
        
        sp.if ~ self.data.balances.contains(address):
            self.data.balances[address] = sp.record(balance = 0, rewards = 0, userRewardPerTokenPaid = 0, counter = 0, InvestMap = sp.map())

    @sp.entry_point
    def RecoverExcessToken(self,params):
        
        sp.set_type(params, sp.TRecord(address = sp.TAddress, value = sp.TNat, token = sp.TAddress, type = sp.TNat, id = sp.TNat))

        # Verification for admin 
        sp.verify(sp.sender == self.data.admin, message = "Invalid Account")

        sp.if params.type == sp.nat(1): 

            sp.verify( (params.address != self.data.stakeToken) | (params.id != TOKEN_ID) , message = "Admin trying to recover the staked tokens")
        
            self.TransferFATwoTokens(sp.self_address, params.address, params.value, params.token, params.id)

        sp.else: 

            sp.verify(params.address != self.data.stakeToken, message= "Admin trying to recover the staked tokens")
        
            self.TransferFATokens(sp.self_address, params.address, params.value, params.token)


    @sp.entry_point
    def changeAdmin(self,address):

        sp.set_type(address, sp.TAddress)
        sp.verify(sp.sender == self.data.admin, message = "Invalid User")

        self.data.admin = address

    @sp.entry_point
    def changeState(self):

        sp.verify(sp.sender == self.data.admin, message = "Invalid User")

        self.data.paused = ~ self.data.paused 

    @sp.entry_point
    def changeUnstakeFee(self,params):

        sp.set_type(params, sp.TRecord(cycles = sp.TNat, fee = sp.TNat, blocksPerCycle = sp.TNat, defaultFee = sp.TNat))

        sp.verify(sp.sender == self.data.admin, message = "Invalid User")

        self.data.unstakeFee[params.cycles] = params.fee

        self.data.blocksPerCycle = params.blocksPerCycle

        self.data.defaultUnstakeFee = params.defaultFee 

    @sp.entry_point
    def WithdrawFee(self):

        sp.verify(self.data.totalFee > 0, message = "Fee Should be Greater than 0")

        sp.verify(sp.sender == self.data.admin ,message= "Invalid User")

        PaymentAmount = sp.local('PaymentAmount', self.data.totalFee)

        self.data.totalFee = 0 

        sp.if self.data.faTwoToken: 

            self.TransferFATwoTokens(sp.self_address, sp.sender, PaymentAmount.value, self.data.stakeToken,TOKEN_ID)

        sp.else: 

            self.TransferFATokens(sp.self_address, sp.sender, PaymentAmount.value, self.data.stakeToken)


    def TransferFATwoTokens(self,sender,reciever,amount,tokenAddress,id):

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


    def TransferFATokens(self,sender,reciever,amount,tokenAddress): 

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


if "templates" not in __name__:
    @sp.add_test(name = "Staking Contract")
    def test():

        scenario = sp.test_scenario()
        scenario.h1("Staking Contract")

        scenario.table_of_contents()

        # Deployment Accounts 
        admin = sp.address("KT1GpTEq4p2XZ8w9p5xM7Wayyw5VR7tb3UaW")
        stakeTokenAddress = sp.address("KT1AFA2mwNUMNd4SsujE1YYp29vd8BZejyKW")
        rewardTokenAddress = sp.address("KT1GRSvLoikDsXujKgZPsGLX8k8VvR2Tq95b")

        stakeTokenFaTwoCheck = True

        # sp.test_account generates ED25519 key-pairs deterministically:
        alice = sp.test_account("Alice")
        bob   = sp.test_account("Robert")
        tezsure = sp.test_account("Tezsure")

        # Let's display the accounts:
        scenario.h1("Accounts")
        scenario.show([alice, bob])

        staking = Staking(admin,stakeTokenAddress,rewardTokenAddress, stakeTokenFaTwoCheck)
        scenario += staking

        # Adding Deposit Fee Values Per Cycle, Testnet has 2048 blocks and Mainnet has 4096 blocks for 1 Cycle , for Simulation we set to 200

        staking.changeUnstakeFee(cycles = 1, fee = 4, blocksPerCycle = 200, defaultFee = 25 ).run(sender = admin)
        staking.changeUnstakeFee(cycles = 2, fee = 6, blocksPerCycle = 200, defaultFee = 25 ).run(sender = admin)
        staking.changeUnstakeFee(cycles = 3, fee = 10, blocksPerCycle = 2000, defaultFee = 25 ).run(sender = admin)

        # Stake Before adding Reward
        staking.stake(amount = 1  * DECIMAL).run(sender = alice , level = 10, valid = False)

        # Admin Contract has Added Reward and Users can Start Staking
        staking.AddReward(reward = 10000 * DECIMAL, blocks = 100).run(sender = admin, level = 100)
        
        # Alice and Bob started Staking 
        staking.stake(amount = 100 * DECIMAL ).run(sender = alice , level = 100)
        staking.stake(amount = 100 * DECIMAL ).run(sender = bob , level = 100  )
        staking.stake(amount = 100 * DECIMAL ).run(sender = tezsure, level = 150 )

        # Admin added Reward in between 
        staking.AddReward(reward = 10000 * DECIMAL, blocks = 100).run(sender = admin, level = 300)

        # Alice and Bob Unstaked their amounts 
        staking.unstake(MapKey = 0 , Amount = 50 * DECIMAL).run(sender = alice, level = 400)
    
        staking.unstake(MapKey = 0 , Amount = 100 * DECIMAL).run(sender = bob , level = 400)
        staking.unstake(MapKey = 0 , Amount = 100 * DECIMAL).run(sender = tezsure , level = 400)

        # Alice and Bob Harvested 
        staking.GetReward().run(sender = alice, level = 401 )    

        # Calling GetReward After Rewards were recived 
        staking.GetReward().run(sender = alice, level = 401)
        
        staking.GetReward().run(sender = bob, level = 401 )
        staking.GetReward().run(sender = tezsure, level = 401 )

        # Checking fee structure at different block heights
        staking.unstake(MapKey = 0 , Amount = 50 * DECIMAL).run(sender = alice, level = 1400)

        # Try Admin Change with Admin 
        staking.changeAdmin(admin).run(sender = admin)

        # Try Admin Change with any address
        staking.changeAdmin(admin).run(sender = alice, valid = False)

        # Try Change State 
        staking.changeState().run(sender = alice ,valid = False)

        # Try Change State with Admin
        staking.changeState().run(sender = admin)

        # Calling Withdraw Fee with any address

        staking.WithdrawFee().run(sender = alice, level = 500, valid = False)
        
        # Calling Withdraw Fee with Admin
        staking.WithdrawFee().run(sender = alice, level = 500, valid = False)