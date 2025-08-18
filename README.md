# Backpack-scripts

This is my first (unprofitable) bot on the Backpack exchange. The project is currently under development: the strategies are still experimental.  

The script is based on the Python API client available at: https://support.backpack.exchange/exchange/api-and-developer-docs/api-clients  
The documentation for Backpack Exchange APIs is available here: https://docs.backpack.exchange/  


# Prerequisites
*  python 3 (tested with Python 3.10.12 on Ubuntu 22.04)  
*  *pip install -r requirements.txt* (To be tested)  
*  postgresql (tested with postgresql 14.18 on Ubuntu 22.04)
*  Creation of a dedicated sub-account on Backpack Exchange and API access for the bot
*  Be sure to define your environment variables before launching (DSN and API Access)
  
  
# Scripts  
## Database  
This script is designed to insert 1-second candles into a PostgreSQL database.  
Database connection information is provided via environment variables.  
export PG_DSN="postgresql://$username:$password@$postgresqlserver:$port/$database  

    python3 ScriptDatabase/pgsql_ohlcv.py   

## Robot
*   There are three operating modes:  
          --real-run : Enable real execution  
          --dry-run : Simulation mode without executing trades  
          --backtest : Backtest duration (ex: 10m, 2h, 3d, 1w, or just a number = minutes)  
*   Token selection can be done in two ways:  
          By simply specifying the tokens to be traded : BTC_USDC_PERP,SOL_USDC_PERP...  
          Or let the bot choose the most volatile tokens with the option: --auto-select. Later, it will be possible to specify that there is no limit on the number of cryptos selected via --no-limit.  
*   There are a few strategies in the bot, but none of them are profitable at the moment.This is managed with the --strategy option :  
          Default, Trix, Combo, Auto, Range, RangeSoft, ThreeOutOfFour, TwoOutOfFourScalp and DynamicThreeTwo  
*   Par defaut, les parametres sont à mettre dans le fichier de configuration dont l'option est --config.  
          --config config/settings.yaml  

'python3 main.py --real-run --auto-select --config config/settings.yaml'  

# To Do  
* Restore positions after restarting
* Manage opened position when the top 10 change
* Stop trading after a daily loss limit
* Trailing stops
* Dynamic position sizing
* Risk metrics : Sharpe ratio, max drawdown
* Review output text (too much information, not well organized)
* Monitoring database updates
* Consider pausing on the symbol when a position in that symbol has been liquidated
* Change the default size of (new) positions without having to restart
* Setup simultaneous open position
* Portfolio management
* Unit tests
