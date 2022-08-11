# Smart-Contracts


# Project structure

```
.
├──  StableSwap/ # Similar Asset Swap Automated Market Maker
├──  Staking/ # Token Distribution Contract
├──  VolatileSwap/ # Volatile Asset Swap Automated Market Maker
├──  xPlenty/ # Flash loan resistant Governance Token
├──  README.md # current file
├──  LICENSE
```

# Prerequisites
  
  - Installed NodeJS
  
  - Installed Python3 

  - SmartPy CLI


Either the above can be installed or online smartpy ide can be utilised for compilation, testing or deployment.

## Staking Contract

Staking Contract is reward token distribution contract inspired from Synthetix dapp which takes in consideration of amount staked, duration of staking while calcualting the rewards for each user. All the reward calculation can be done in constant time complexity.


## Volatile Swap

Volatile Swap is an automated market maker which facilitates in exchanging of two tokens irrespective of their nature.


## StableSwap

StableSwap is an automated marketm maker which helps in exchanging in similar priced assets in an optimised manner by reducing slippage irrespective of the trade size.

## xPlenty

xPlenty is the governance token utilised for voting on the PIP-3 which facilate additon of new pairs, mint reduction, managing reward distribution.


## Compilation

To compile the contracts run:

```
 ~/smartpy-cli/SmartPy.sh compile <smart-contract-folder>/<smart-contract> <output-directory>

```

The contracts can also be compiled using the online IDE.


## Deployment

For Deployment of the smart contract, either online ide or CLI can be utilised. 

```
  ~/smartpy-cli/SmartPy.sh originate-contract --code code.json --storage storage.json --rpc <rpc> --private-key <private-key>

```

## Testing 

For testing of the smart contracts, either custom testcase can be written and smart contracts be imported into the respective file 
and various scenarios can be evaluted. 

```
~/smartpy-cli/SmartPy.sh test <custom-test-case-file> <output-directory>

```


*NOTE:
This repository is open-sourced, and is under active improvements based on suggestions and bug-reports. Users are requested to double check the transaction details on their wallet's confirmation page. The authors take no responsibility for the loss of digital assets.*
