"""Fail-closed configuration checks for the stage-2 runner."""
PUBLIC_URL = 'https://data-api.binance.vision/api/v3'


def validate_config(config, environ):
    if any(k.startswith('FREQTRADE__') for k in environ):
        raise ValueError('FREQTRADE__ environment overrides are forbidden')
    if config.get('dry_run') is not True or config.get('trading_mode') != 'spot':
        raise ValueError('Only dry_run=true spot research is allowed')
    if config.get('max_open_trades') != 1 or config.get('force_entry_enable') is not False:
        raise ValueError('Unsafe position or forced-entry settings')
    if config.get('api_server', {}).get('enabled', False) is not False or config.get('telegram', {}).get('enabled', False) is not False:
        raise ValueError('Remote control must remain disabled')
    if config.get('add_config_files') or config.get('freqai', {}).get('enabled'):
        raise ValueError('Nested configs/FreqAI are not supported in stage 2')
    exchange = config['exchange']
    if exchange.get('name') != 'binance' or exchange.get('pair_whitelist') != ['BTC/USDT']:
        raise ValueError('Only Binance BTC/USDT is allowed')
    if any(exchange.get(k) for k in ('key','secret','password','uid','apiKey','privateKey','walletAddress')):
        raise ValueError('Account credentials are forbidden in the research runtime')
    if exchange.get('enable_ws') is not False:
        raise ValueError('Use verified public REST data only in this phase')
    for key in ('ccxt_config','ccxt_async_config'):
        ccxt = exchange.get(key, {})
        if ccxt.get('urls') != {'api': {'public': PUBLIC_URL}}:
            raise ValueError('Unexpected market data endpoint override')
        if ccxt.get('options', {}).get('fetchMarkets') != {'types':['spot']}:
            raise ValueError('Only spot markets may be loaded')
        if any(ccxt.get(k) for k in ('apiKey','secret','password','headers','proxy','httpProxy','httpsProxy')):
            raise ValueError('CCXT credentials/proxies/custom headers are forbidden')
    if not 0 < config.get('dry_run_wallet', 0) <= 30:
        raise ValueError('Unexpected simulated capital')
    return config
