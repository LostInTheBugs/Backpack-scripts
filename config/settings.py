# config/settings.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Dict, List, Optional
import yaml
import os
from pathlib import Path

class TradingConfig(BaseSettings):
    """Trading configuration settings"""
    position_amount_usdc: float = Field(50.0, description="Position size in USDC")
    leverage: int = Field(2, description="Trading leverage")
    trailing_stop_trigger: float = Field(0.5, description="Trailing stop trigger in %")
    max_positions: int = Field(5, description="Maximum simultaneous positions")
    min_pnl_for_trailing: float = Field(0.3, description="Minimum PnL % before activating trailing stop")

class DatabaseConfig(BaseSettings):
    """Database configuration settings"""
    retention_days: int = Field(90, description="Data retention in days")
    pool_min_size: int = Field(5, description="Minimum pool connections")
    pool_max_size: int = Field(20, description="Maximum pool connections")
    max_age_seconds: int = Field(600, description="Max age for fresh data in seconds")

class ThreeOutOfFourConfig(BaseSettings):
    stop_loss_pct: float = Field(1.0, description="Stop loss percent for ThreeOutOfFour")
    take_profit_pct: float = Field(2.0, description="Take profit percent for ThreeOutOfFour")

class TwoOutOfFourScalpConfig(BaseSettings):
    stop_loss_pct: float = Field(0.5, description="Stop loss percent for TwoOutOfFourScalp")
    take_profit_pct: float = Field(1.0, description="Take profit percent for TwoOutOfFourScalp")

class StrategyConfig(BaseSettings):
    """Strategy configuration settings"""
    default_strategy: str = Field("Default", description="Default trading strategy")
    auto_select_update_interval: int = Field(300, description="Auto symbol update interval in seconds")
    auto_select_top_n: int = Field(10, description="Number of top symbols to select")
    
    # Strategy-specific parameters
    rsi_period: int = Field(14, description="RSI calculation period")
    macd_fast: int = Field(12, description="MACD fast period")
    macd_slow: int = Field(26, description="MACD slow period")
    macd_signal: int = Field(9, description="MACD signal period")
    trix_period: int = Field(15, description="TRIX calculation period")
    ema_periods: Dict[str, int] = Field(
        {"short": 20, "medium": 50, "long": 200}, 
        description="EMA periods"
    )
    three_out_of_four: ThreeOutOfFourConfig = ThreeOutOfFourConfig()
    two_out_of_four_scalp: TwoOutOfFourScalpConfig = TwoOutOfFourScalpConfig()

class RiskConfig(BaseSettings):
    """Risk management configuration"""
    max_daily_loss_pct: float = Field(10.0, description="Maximum daily loss percentage")
    max_correlation: float = Field(0.7, description="Maximum correlation between positions")
    position_sizing_method: str = Field("fixed", description="Position sizing method: fixed, percentage, kelly")
    risk_per_trade_pct: float = Field(2.0, description="Risk per trade as percentage of capital")

class LoggingConfig(BaseSettings):
    """Logging configuration"""
    log_level: str = Field("INFO", description="Logging level")
    log_file_path: str = Field("logs/trading.log", description="Log file path")
    max_log_file_size_mb: int = Field(50, description="Maximum log file size in MB")
    log_backup_count: int = Field(5, description="Number of log backup files")
    timezone: str = Field("Europe/Paris", description="Logging timezone")

class Config(BaseSettings):
    """Main configuration class"""
    trading: TradingConfig = TradingConfig()
    database: DatabaseConfig = DatabaseConfig()
    strategy: StrategyConfig = StrategyConfig()
    risk: RiskConfig = RiskConfig()
    logging: LoggingConfig = LoggingConfig()
    
    # Environment variables
    bpx_bot_public_key: Optional[str] = Field(None, env="bpx_bot_public_key")
    bpx_bot_secret_key: Optional[str] = Field(None, env="bpx_bot_secret_key")
    pg_dsn: Optional[str] = Field(None, env="PG_DSN")
    
    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"  # Allows TRADING__POSITION_AMOUNT_USDC=100

# Global config instance
_config = None

def load_config(config_path: str = "config/settings.yaml") -> Config:
    """Load configuration from YAML file and environment variables"""
    global _config
    
    if _config is None:
        config_file = Path(config_path)
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                yaml_config = yaml.safe_load(f)
            
            # Create config with YAML overrides
            _config = Config(**yaml_config)
        else:
            # Create default config
            _config = Config()
            
            # Create default YAML file
            save_default_config(config_path)
    
    return _config

def save_default_config(config_path: str = "config/settings.yaml"):
    """Save default configuration to YAML file"""
    config_file = Path(config_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    default_config = {
        'trading': {
            'position_amount_usdc': 20.0,
            'leverage': 1,
            'trailing_stop_trigger': 0.5,
            'max_positions': 5,
            'min_pnl_for_trailing': 0.3
        },
        'database': {
            'retention_days': 90,
            'pool_min_size': 5,
            'pool_max_size': 20,
            'max_age_seconds': 600
        },
        'strategy': {
            'default_strategy': 'Default',
            'auto_select_update_interval': 300,
            'auto_select_top_n': 10,
            'rsi_period': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'trix_period': 15,
            'ema_periods': {
                'short': 20,
                'medium': 50,
                'long': 200
            }
        },
        'risk': {
            'max_daily_loss_pct': 10.0,
            'max_correlation': 0.7,
            'position_sizing_method': 'fixed',
            'risk_per_trade_pct': 2.0
        },
        'logging': {
            'log_level': 'INFO',
            'log_file_path': 'logs/trading.log',
            'max_log_file_size_mb': 50,
            'log_backup_count': 5,
            'timezone': 'Europe/Paris'
        }
    }
    
    with open(config_file, 'w') as f:
        yaml.dump(default_config, f, default_flow_style=False, indent=2)
    
    print(f"✅ Default configuration saved to {config_path}")

def get_config() -> Config:
    """Get the current configuration instance"""
    global _config
    if _config is None:
        _config = load_config()
    return _config

# Convenience functions for easy access
def get_trading_config() -> TradingConfig:
    return get_config().trading

def get_database_config() -> DatabaseConfig:
    return get_config().database

def get_strategy_config() -> StrategyConfig:
    return get_config().strategy

def get_risk_config() -> RiskConfig:
    return get_config().risk

def get_logging_config() -> LoggingConfig:
    return get_config().logging